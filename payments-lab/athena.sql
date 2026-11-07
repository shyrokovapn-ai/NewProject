-- Replace YOUR_BUCKET before running. Athena workgroup output must be configured separately.
CREATE DATABASE IF NOT EXISTS payments_lab;

CREATE EXTERNAL TABLE IF NOT EXISTS payments_lab.payment_events (
  invoiceId string,
  status string,
  failureReason string,
  amount string,
  finalAmount string,
  ccy string,
  reference string,
  createdDate string,
  modifiedDate string,
  receivedAt string,
  merchantId string,
  merchantName string,
  mcc string,
  customerId string,
  paymentMethod string,
  device string
)
PARTITIONED BY (dt string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json'='false')
STORED AS TEXTFILE
LOCATION 's3://YOUR_BUCKET/payments/'
TBLPROPERTIES ('projection.enabled'='false');

MSCK REPAIR TABLE payments_lab.payment_events;

-- Initial scale and quality checks.
SELECT count(*) AS total_events,
       count(DISTINCT invoiceId) AS unique_invoices,
       count(*) - count(DISTINCT invoiceId) AS events_beyond_one_per_invoice
FROM payments_lab.payment_events;

-- Exact duplicate rows. Compare this with count(*) to quantify repeated webhook payloads.
WITH distinct_events AS (
  SELECT DISTINCT invoiceId, status, failureReason, amount, finalAmount, ccy,
         reference, createdDate, modifiedDate, receivedAt, merchantId, merchantName,
         mcc, customerId, paymentMethod, device, dt
  FROM payments_lab.payment_events
)
SELECT (SELECT count(*) FROM payments_lab.payment_events) AS raw_rows,
       count(*) AS exact_distinct_rows,
       (SELECT count(*) FROM payments_lab.payment_events) - count(*) AS exact_duplicate_rows
FROM distinct_events;

-- Events late by more than 60 seconds, including late events over one hour.
WITH lagged AS (
  SELECT date_diff('second', from_iso8601_timestamp(modifiedDate),
                              from_iso8601_timestamp(receivedAt)) AS lag_seconds
  FROM payments_lab.payment_events
)
SELECT count(*) AS total_events,
       count_if(lag_seconds > 60) AS over_60_seconds,
       count_if(lag_seconds > 3600) AS over_one_hour,
       round(100.0 * count_if(lag_seconds > 3600) / nullif(count(*), 0), 4) AS over_one_hour_pct
FROM lagged;

-- Create a logical latest-payment view. Exact copies are eliminated before row_number.
CREATE OR REPLACE VIEW payments_lab.payments AS
WITH exact_events AS (
  SELECT DISTINCT invoiceId, status, failureReason, amount, finalAmount, ccy,
         reference, createdDate, modifiedDate, receivedAt, merchantId, merchantName,
         mcc, customerId, paymentMethod, device, dt
  FROM payments_lab.payment_events
), ranked AS (
  SELECT *, row_number() OVER (
    PARTITION BY invoiceId
    ORDER BY from_iso8601_timestamp(modifiedDate) DESC,
             from_iso8601_timestamp(receivedAt) DESC,
             dt DESC
  ) AS rn
  FROM exact_events
)
SELECT invoiceId, status, failureReason, try_cast(amount AS bigint) AS amount_minor,
       try_cast(finalAmount AS bigint) AS final_amount_minor,
       try_cast(ccy AS integer) AS ccy, reference, createdDate, modifiedDate,
       receivedAt, merchantId, merchantName, try_cast(mcc AS integer) AS mcc,
       customerId, paymentMethod, device, dt
FROM ranked
WHERE rn = 1;

-- Query 2: successful turnover by merchant and ISO 4217 currency, converted from minor units.
SELECT merchantId, merchantName, ccy,
       sum(final_amount_minor) / 100.0 AS turnover_major_units,
       count(*) AS successful_payments
FROM payments_lab.payments
WHERE lower(status) = 'success'
GROUP BY merchantId, merchantName, ccy
ORDER BY turnover_major_units DESC;

-- Query 3: latest payment failure rate by payment method and device.
SELECT paymentMethod, device,
       count(*) AS payments,
       count_if(lower(status) = 'failure') AS failures,
       round(100.0 * count_if(lower(status) = 'failure') / nullif(count(*), 0), 2) AS failure_pct
FROM payments_lab.payments
GROUP BY paymentMethod, device
ORDER BY failure_pct DESC, payments DESC;

-- Query 4: unique latest payments by hour of creation (UTC).
SELECT hour(from_iso8601_timestamp(createdDate)) AS hour_utc,
       count(*) AS payments
FROM payments_lab.payments
GROUP BY 1
ORDER BY 1;

-- Query 5: latency as requested by the brief, evaluated on every raw webhook event.
SELECT count(*) AS total_events,
       count_if(date_diff('second', from_iso8601_timestamp(modifiedDate),
                                    from_iso8601_timestamp(receivedAt)) > 60) AS over_60_seconds,
       round(100.0 * count_if(date_diff('second', from_iso8601_timestamp(modifiedDate),
                                               from_iso8601_timestamp(receivedAt)) > 60)
                   / nullif(count(*), 0), 2) AS over_60_seconds_pct
FROM payments_lab.payment_events;

-- Query 6: write the deduplicated, latest-per-invoice relation to Parquet partitioned by dt.
-- Athena CTAS cannot create an already-existing non-empty location; use a fresh curated prefix
-- (or remove only the prior curated output before rerunning).
CREATE TABLE payments_lab.payments_parquet
WITH (
  format = 'PARQUET',
  external_location = 's3://YOUR_BUCKET/curated/payments_parquet/',
  partitioned_by = ARRAY['dt']
) AS
SELECT invoiceId, status, failureReason, amount_minor, final_amount_minor, ccy,
       reference, createdDate, modifiedDate, receivedAt, merchantId, merchantName,
       mcc, customerId, paymentMethod, device, dt
FROM payments_lab.payments;

-- For JSON-vs-Parquet scan comparisons, rerun the turnover, failure-rate, and peak-hour
-- queries above with payments_lab.payments_parquet in place of payments_lab.payments.
-- The late-event diagnostic is event-level and belongs on raw payment_events; the curated
-- table has one row per invoice, so it cannot reproduce the raw-event lateness total.
-- Add `AND dt BETWEEN '2026-10-01' AND '2026-10-31'` when the question is date-bounded.

-- Part 4: after Firehose has delivered records to stream/raw/, create a table over that prefix.
CREATE EXTERNAL TABLE IF NOT EXISTS payments_lab.stream_events (
  invoiceId string,
  status string,
  failureReason string,
  amount string,
  finalAmount string,
  ccy string,
  reference string,
  createdDate string,
  modifiedDate string,
  receivedAt string,
  merchantId string,
  merchantName string,
  mcc string,
  customerId string,
  paymentMethod string,
  device string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://YOUR_BUCKET/stream/raw/';

SELECT status, paymentMethod, count(*) AS events
FROM payments_lab.stream_events
GROUP BY status, paymentMethod
ORDER BY events DESC;
