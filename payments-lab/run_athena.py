#!/usr/bin/env python3
"""Run the batch lab SQL in Athena and export query results plus scan metrics."""

import argparse
import csv
import json
import re
import time
from pathlib import Path

import boto3


def statements_from(path: Path, bucket: str) -> list[str]:
    source = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    ).replace("YOUR_BUCKET", bucket)
    return [part.strip() for part in source.split(";") if part.strip()]


def slug(value: str, index: int) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return f"{index:02d}_{clean[:48] or 'query'}"


def wait_for_query(client, query_id: str, timeout: int) -> dict:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        execution = client.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            if state != "SUCCEEDED":
                reason = execution["Status"].get("StateChangeReason", "unknown Athena error")
                raise RuntimeError(f"Athena query {query_id} {state}: {reason}")
            return execution
        time.sleep(2)
    client.stop_query_execution(QueryExecutionId=query_id)
    raise TimeoutError(f"Athena query {query_id} exceeded {timeout}s")


def export_query_results(client, query_id: str, destination: Path) -> int:
    response = client.get_query_results(QueryExecutionId=query_id, MaxResults=1000)
    columns = [column.get("Label") or column.get("Name") for column in response["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
    rows = response["ResultSet"]["Rows"]
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(columns)
        if rows:
            rows = rows[1:]  # Athena includes the column names as the first row.
        count = 0
        while True:
            for row in rows:
                values = [datum.get("VarCharValue", "") for datum in row.get("Data", [])]
                writer.writerow(values)
                count += 1
            token = response.get("NextToken")
            if not token:
                break
            response = client.get_query_results(QueryExecutionId=query_id, NextToken=token, MaxResults=1000)
            rows = response["ResultSet"]["Rows"]
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True, help="us-east-1 bucket containing payments/")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--sql", type=Path, default=Path(__file__).with_name("athena.sql"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("evidence") / "athena")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--export-existing", action="store_true", help="export missing CSVs from the saved manifest without rerunning SQL")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    client = boto3.client("athena", region_name=args.region)
    manifest_path = args.output / "manifest.json"
    if args.export_existing:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in manifest:
            if not record.get("query_id") or record.get("name", "").startswith("parquet_"):
                continue
            sql_result = client.get_query_execution(QueryExecutionId=record["query_id"])["QueryExecution"]
            if sql_result["StatementType"] not in {"DML"}:
                continue
            destination = args.output / f"{record['name']}.csv"
            if not destination.exists():
                record["csv_rows"] = export_query_results(client, record["query_id"], destination)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Exported saved query results to {args.output}")
        return

    base = statements_from(args.sql, args.bucket)
    # The Part 4 table has no data until Kinesis and Firehose are deployed, so leave it for then.
    base = [sql for sql in base if "payments_lab.stream_events" not in sql]
    parquet = [
        """SELECT merchantId, merchantName, ccy, sum(final_amount_minor) / 100.0 AS turnover_major_units,
                  count(*) AS successful_payments
           FROM payments_lab.payments_parquet WHERE lower(status) = 'success'
           GROUP BY merchantId, merchantName, ccy ORDER BY turnover_major_units DESC""",
        """SELECT paymentMethod, device, count(*) AS payments,
                  count_if(lower(status) = 'failure') AS failures,
                  round(100.0 * count_if(lower(status) = 'failure') / nullif(count(*), 0), 2) AS failure_pct
           FROM payments_lab.payments_parquet GROUP BY paymentMethod, device
           ORDER BY failure_pct DESC, payments DESC""",
        """SELECT hour(from_iso8601_timestamp(createdDate)) AS hour_utc, count(*) AS payments
           FROM payments_lab.payments_parquet GROUP BY 1 ORDER BY 1""",
    ]
    definitions = [(sql, None) for sql in base]
    definitions.extend((sql, name) for sql, name in zip(parquet, ("parquet_turnover", "parquet_failure_rate", "parquet_peak_hour")))
    manifest = []

    for index, (sql, fixed_name) in enumerate(definitions, 1):
        name = fixed_name or slug(sql, index)
        print(f"[{index}/{len(definitions)}] {name}", flush=True)
        result = client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": "payments_lab"},
            ResultConfiguration={"OutputLocation": f"s3://{args.bucket}/athena-results/"},
        )
        query_id = result["QueryExecutionId"]
        execution = wait_for_query(client, query_id, args.timeout)
        stats = execution.get("Statistics", {})
        record = {
            "name": name,
            "query_id": query_id,
            "state": execution["Status"]["State"],
            "data_scanned_bytes": stats.get("DataScannedInBytes", 0),
            "engine_execution_ms": stats.get("EngineExecutionTimeInMillis", 0),
            "output_location": execution.get("ResultConfiguration", {}).get("OutputLocation"),
        }
        if sql.lstrip().upper().startswith(("SELECT", "WITH")):
            record["csv_rows"] = export_query_results(client, query_id, args.output / f"{name}.csv")
        manifest.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved query results and scan metrics to {args.output}")


if __name__ == "__main__":
    main()
