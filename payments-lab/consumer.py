#!/usr/bin/env python3
"""Count event-time terminal payment failure shares with exact-record dedup."""

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError


def event_timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event time must include a timezone")
    return parsed.astimezone(timezone.utc).timestamp()


def canonical_id(event: dict) -> str:
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", default="localhost:19092")
    parser.add_argument("--topic", default="payments")
    parser.add_argument("--group", default="payments-lab")
    parser.add_argument("--grace-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.grace_seconds < 0:
        parser.error("--grace-seconds cannot be negative")

    consumer = Consumer({
        "bootstrap.servers": args.broker,
        "group.id": args.group,
        "enable.auto.commit": True,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([args.topic])
    seen_events: set[str] = set()
    windows: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0])
    max_event_time_by_partition: dict[int, float] = {}
    late_rejected = 0
    duplicates = 0

    def close_ready(watermark: float) -> None:
        ready = sorted(key for key in windows if (key[0] + 60 + args.grace_seconds) <= watermark)
        for start, method in ready:
            total, failures = windows.pop((start, method))
            share = failures / total if total else 0.0
            label = datetime.fromtimestamp(start, timezone.utc).isoformat()
            print(f"WINDOW start={label} method={method} events={total} failures={failures} failure_share={share:.2%}", flush=True)
            if share > 0.10:
                print(f"ALERT method={method} window={label} failure_share={share:.2%} threshold=10%", flush=True)

    def current_watermark() -> float:
        assigned = consumer.assignment()
        partition_ids = [item.partition for item in assigned]
        for partition_id in partition_ids:
            max_event_time_by_partition.setdefault(partition_id, float("-inf"))
        if not partition_ids:
            return float("-inf")
        return min(max_event_time_by_partition[partition_id] for partition_id in partition_ids)

    print(f"Consuming {args.topic} as group {args.group}; Ctrl-C to stop", flush=True)
    try:
        while True:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(message.error())
            try:
                event = json.loads(message.value())
                identity = canonical_id(event)
                if identity in seen_events:
                    duplicates += 1
                    continue
                seen_events.add(identity)
                event_time = event_timestamp(event["modifiedDate"])
                start = int(event_time // 60) * 60
                window_key = (start, str(event.get("paymentMethod") or "unknown"))
                if start + 60 + args.grace_seconds <= current_watermark():
                    late_rejected += 1
                    print(f"LATE_REJECTED invoice={event.get('invoiceId')} modifiedDate={event['modifiedDate']} total={late_rejected}", flush=True)
                    continue
                partition_id = message.partition()
                max_event_time_by_partition[partition_id] = max(
                    max_event_time_by_partition.get(partition_id, float("-inf")), event_time
                )
                status = str(event.get("status", "")).lower()
                if status in {"success", "failure"}:
                    windows[window_key][0] += 1
                    if status == "failure":
                        windows[window_key][1] += 1
                close_ready(current_watermark())
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                print(f"INVALID_RECORD partition={message.partition()} offset={message.offset()} reason={exc}", flush=True)
    except KeyboardInterrupt:
        close_ready(float("inf"))
        print(f"Stopped. exact_duplicates={duplicates} late_rejected={late_rejected}", flush=True)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()

