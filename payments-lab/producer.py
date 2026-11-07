#!/usr/bin/env python3
"""Replay a JSONL payment partition to local Redpanda in receivedAt order."""

import argparse
import json
import random
import time
from datetime import datetime
from pathlib import Path

from confluent_kafka import Producer


def iso_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value}")
    return parsed


def load_events(path: Path) -> list[dict]:
    events = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                for field in ("invoiceId", "status", "modifiedDate", "receivedAt"):
                    if not event.get(field):
                        raise ValueError(f"missing {field}")
                iso_time(event["receivedAt"])
                iso_time(event["modifiedDate"])
                events.append(event)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid record on line {line_number}: {exc}") from exc
    events.sort(key=lambda event: iso_time(event["receivedAt"]))
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--broker", default="localhost:19092")
    parser.add_argument("--topic", default="payments")
    parser.add_argument("--rate", type=float, default=20.0, help="target payments per second")
    parser.add_argument("--failure-rate", type=float, default=0.0, help="fraction of invoices forced to failure")
    parser.add_argument("--seed", type=int, default=7, help="repeatable failure injection")
    args = parser.parse_args()
    if args.rate <= 0 or not 0 <= args.failure_rate <= 1:
        parser.error("--rate must be positive and --failure-rate must be from 0 to 1")

    events = load_events(args.input)
    if not events:
        parser.error("input file contains no events")
    producer = Producer({"bootstrap.servers": args.broker, "enable.idempotence": True})
    rng = random.Random(args.seed)
    payment_ids = sorted({str(event["invoiceId"]) for event in events})
    forced_failure_count = round(len(payment_ids) * args.failure_rate)
    forced_failures = set(rng.sample(payment_ids, forced_failure_count))
    delivery_errors: list[str] = []
    delivered = 0
    payments = len(payment_ids)
    interval = payments / args.rate / len(events)
    next_send = time.monotonic()

    def delivery_report(error, message) -> None:
        nonlocal delivered
        if error is not None:
            delivery_errors.append(str(error))
        else:
            delivered += 1

    try:
        for event in events:
            invoice_id = str(event["invoiceId"])
            outgoing = event.copy()
            if invoice_id in forced_failures and outgoing["status"] in {"success", "failure"}:
                outgoing["status"] = "failure"
                outgoing["finalAmount"] = 0
                outgoing["failureReason"] = outgoing.get("failureReason") or "Injected experiment failure"
            producer.produce(
                args.topic,
                key=invoice_id.encode("utf-8"),
                value=json.dumps(outgoing, separators=(",", ":")).encode("utf-8"),
                on_delivery=delivery_report,
            )
            producer.poll(0)
            next_send += interval
            delay = next_send - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        remaining = producer.flush(30)
        if remaining:
            raise RuntimeError(f"{remaining} messages were not delivered before timeout")
        if delivery_errors:
            raise RuntimeError(f"{len(delivery_errors)} message(s) failed delivery; first error: {delivery_errors[0]}")
        if delivered != len(events):
            raise RuntimeError(f"delivery acknowledgements: {delivered}/{len(events)}")
    finally:
        producer.flush(5)
    print(f"Sent {len(events)} events ({payments} payments) to {args.topic} at about {args.rate:g} payments/s")
    if args.failure_rate:
        print(f"Injected failures for {len(forced_failures)}/{payments} payments ({len(forced_failures) / payments:.2%})")


if __name__ == "__main__":
    main()

