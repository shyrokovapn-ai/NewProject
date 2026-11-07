#!/usr/bin/env python3
"""Send JSONL payment records to an AWS Kinesis Data Stream."""

import argparse
import json
import time
from pathlib import Path

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--stream", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--rate", type=float, default=20.0, help="target payments per second")
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")

    client = boto3.client("kinesis", region_name=args.region)
    records = []
    with args.input.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                key = str(event["invoiceId"])
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid record on line {line_number}: {exc}") from exc
            records.append((key, json.dumps(event, separators=(",", ":"))))

    if not records:
        parser.error("input file contains no events")
    payment_count = len({key for key, _ in records})
    delay = payment_count / args.rate / len(records)
    for index, (key, value) in enumerate(records, 1):
        response = client.put_record(StreamName=args.stream, PartitionKey=key, Data=value.encode("utf-8"))
        if response.get("ShardId") is None:
            raise RuntimeError(f"Kinesis did not acknowledge record {index}")
        if index < len(records):
            time.sleep(delay)
    print(f"Sent {len(records)} events ({payment_count} payments) to {args.stream} at about {args.rate:g} payments/s")


if __name__ == "__main__":
    main()

