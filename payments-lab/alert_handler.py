"""Kinesis-triggered alert handler: one concise SNS notification per failure batch."""

import base64
import json
import os

import boto3

sns = boto3.client("sns")


def handler(event, _context):
    failed = []
    for record in event.get("Records", []):
        raw = base64.b64decode(record["kinesis"]["data"])
        try:
            payment = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if str(payment.get("status", "")).lower() == "failure":
            failed.append(payment)
    if failed:
        examples = ", ".join(str(item.get("invoiceId", "unknown")) for item in failed[:5])
        sns.publish(
            TopicArn=os.environ["ALERT_TOPIC_ARN"],
            Subject=f"Payment failure events detected: {len(failed)}",
            Message=(f"Kinesis batch contained {len(failed)} failure event(s). "
                     f"Example invoice IDs: {examples}"),
        )
    return {"failure_events": len(failed)}

