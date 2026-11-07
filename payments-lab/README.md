# Payments data engineering lab

This folder contains the code, measured results, and discussion for Parts 1–4 of the payments lab. Parts 2 and 3 were run and their evidence is included. The Part 4 template and producer are prepared, but this account returned `SubscriptionRequiredException` for Kinesis, so its deployment and Athena screenshot are still outstanding; see `submission-notes.md`. No AWS results are fabricated.

## Requirements

- Docker with Compose v2
- Python 3.11+
- AWS CLI v2 configured for an account in `us-east-1` for Parts 2 and 4
- AWS SAM CLI for deploying the Part 4 template
- An S3 bucket you own, in `us-east-1`, with Athena query results configured

The source dataset is public. Copy it to your bucket before querying:

```sh
aws s3 sync s3://ucu-ooad-lab8-payments/payments/ s3://YOUR_BUCKET/payments/ --region us-east-1 --copy-props none
```

Do not put a trailing `*` on the source: `sync` copies the full prefix, including all day partitions.

## Part 2: Athena

1. In Athena, set the workgroup output location to `s3://YOUR_BUCKET/athena-results/`.
2. Replace `YOUR_BUCKET` in `athena.sql` with your bucket name and execute the setup section through `MSCK REPAIR TABLE`.
3. Record `COUNT(*)`, unique invoice count, exact duplicate count and the late-event counts from the diagnostic queries.
4. Run the deduplicated view and the turnover, failure-rate, peak-hour, and late-event queries. Record each query's **Data scanned** and runtime from query details.
5. Create and run the CTAS statement to write `curated/` Parquet; then rerun the turnover, failure-rate, and peak-hour queries against the Parquet table. The late-event query is an event-level diagnostic on raw webhook rows; Parquet contains only the latest row per invoice, so its late-event count would answer a different question. Partition filter (`dt`) predicates are included when useful. Athena scan cost depends on region and the current price per TB, so calculate it from the measured bytes and quote the price you actually observe/use. The CTAS target must be empty on first creation; to repeat the full runner, drop `payments_lab.payments_parquet` and remove only its prior `curated/payments_parquet/` objects first. Use `--export-existing` to re-export the last run without rerunning queries.
6. The included `glue-crawler-template.yaml` creates a least-scope S3 read policy and Glue crawler targeting `s3://YOUR_BUCKET/payments/`. Deploy it with `aws cloudformation deploy --region us-east-1 --stack-name payments-lab-glue-crawler --template-file glue-crawler-template.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BucketName=YOUR_BUCKET`, then start it with `aws glue start-crawler --region us-east-1 --name payments-lab-crawler`. Wait until the crawler state is `READY`. Record the inferred types for `amount`, `ccy`, and the dates, whether it recognized `dt`, and how nullable `failureReason` appeared.

Athena DDL and queries are in `athena.sql`. After replacing `YOUR_BUCKET`, you can run the full batch sequence and save CSV results plus measured scan/runtime data with:

```sh
python run_athena.py --bucket YOUR_BUCKET
```

The runner skips only the Part 4 query over `stream/raw/`, which does not exist until the cloud stream is deployed. It saves outputs under `evidence/athena/`.

## Part 3: Redpanda on your laptop

Start the broker and Console:

```sh
cd payments-lab
docker compose up -d
docker compose exec redpanda rpk topic create payments --partitions 3 --replicas 1
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python producer.py --input /path/to/events.jsonl --rate 20
```

Create the topic only once; if it already exists, skip that command. This workspace's topic currently contains the replayed October 1 sample. For another clean experiment, stop all consumers, delete the topic, and create it again before replaying.

The input should be one extracted partition, such as `events.jsonl` from one `dt=2026-10-01` folder. The producer validates and orders by `receivedAt`, uses the invoice as the message key, and paces all webhook events to approximately 20 payments per second (roughly 60 events/s for this dataset). Open Redpanda Console at <http://localhost:8080>.

In another terminal:

```sh
python consumer.py --group payments-lab --grace-seconds 120
```

The consumer counts unique terminal payment outcomes (`success` or `failure`) in event-time minute windows, closes a window after its end plus the grace period, and warns when the failure share is strictly above 10%. It tracks event-time progress per assigned Kafka partition and closes windows only when the slowest assigned partition has passed the grace period, so one fast partition cannot prematurely close another's windows. Its event identity is a SHA-256 hash of the canonical JSON record, so an identical webhook replay is counted once while a later status change is retained. Start a second consumer with the same group ID to see partition assignment. Stop and restart the consumer with the same group ID to resume from committed offsets.

To replay an experiment with 30% failed payments, use a copy of the day file and `producer.py --failure-rate 0.30`. This changes terminal success/failure statuses in the copy as it is sent; it does not edit the original data. For zero grace, restart the consumer with `--grace-seconds 0`. Late records whose event-time window has already closed are counted and logged as rejected. For controlled repeatable runs, use a fresh topic/group (`--topic ...`, `--group ...`) or delete the topic only after stopping all clients.

## Part 4: Kinesis → Firehose → S3 → Athena, with SNS alerts

The SAM template `cloud-template.yaml` provisions a Kinesis stream, a Firehose delivery stream reading it, a raw S3 prefix, an SNS topic, and a small Kinesis-triggered Lambda that sends an SNS alert when it sees a failure event. The producer `cloud_producer.py` reads one local daily JSONL file and sends each record to Kinesis. Athena table DDL for the delivered JSON is in `athena.sql`.

Deploy from this folder:

```sh
sam build -t cloud-template.yaml
sam deploy --guided --region us-east-1
```

Set `BucketName` to a bucket you control and optionally set `AlertEmail` to your address. Confirm the SNS subscription email. Then read the `StreamName` output and run:

```sh
python cloud_producer.py --input /path/to/events.jsonl --stream STREAM_NAME --region us-east-1 --rate 20
```

Firehose buffers before delivery, so wait for its configured buffer interval before querying Athena. Use the `AthenaCreateStreamTable` output (or its equivalent in `athena.sql`) and point it at the `stream/raw/` prefix. For evidence, capture the query text/results and query details in Athena. When finished, remove the SAM stack with `sam delete --stack-name STACK_NAME --region us-east-1`; verify that the stack's Kinesis stream and Firehose delivery stream are gone. The bucket is retained because it may contain your input copy and results; delete only objects you no longer need.

## Architecture answers

- A ten-minute real-time lag makes matching positions, surge prices, and alerts stale; the system needs lag alarms, backpressure handling, and a recovery plan. A one-day batch delay makes dashboards and training data stale, but usually does not interrupt an active ride; rerun/recovery capacity and freshness expectations matter.
- GPS uses a long-lived MQTT connection to IoT Core because a message every few seconds from many devices is better handled by a purpose-built connection/broker service than invoking Lambda per ping. Lambda can still process downstream events asynchronously.
- A small startup can begin with one application, a relational database, object storage, and scheduled SQL. It gives up independent scaling, managed streaming state, low-latency analytics, and dedicated ML operations until those needs justify the cost and operational complexity.
- Event time is `modifiedDate`; processing time is `receivedAt`/arrival. Grace lets out-of-order events contribute before a window closes. After closure, the simple consumer drops the event and increments a late counter; production systems may emit corrections or side outputs.
- JSON preserves the source and supports replay/audit; Parquet is columnar and compressed, so queries that select a few columns scan less data. A hand-written schema controls types, names, and partitioning; crawler inference is convenient but can infer weak types or inconsistent nullable fields.
- Batch is suitable for reports with hour/day freshness. Matching, safety signals, and surge pricing need seconds. Managed services reduce broker/cluster operations and integrate with AWS, at the price of service charges, quotas, and more account-specific configuration.

## Submission

Use `submission-notes.md` for the short online response and measured evidence. Keep screenshots or exported CSVs from your actual Athena and consumer runs; the repository cannot supply authentic account-specific query timings or cost before you run it.

For a Ukrainian explanation of the code and likely class questions, see `EXPLAIN-CODE-uk.md`.
