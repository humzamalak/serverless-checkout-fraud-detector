"""DynamoDB access. One table, single-table design.

Items
  PK=ORDER#<order_id>   SK=DECISION          the stored decision (idempotency)
  PK=CARD#<bin-last4>   SK=TS#<epoch>#<id>   velocity marker, TTL 24 h
  PK=IP#<ip>            SK=TS#<epoch>#<id>   velocity marker, TTL 24 h
  PK=CUST#<id>          SK=TS#<epoch>#<id>   velocity marker, TTL 24 h
  PK=CUST#<id>          SK=STATS             order_count, total_amount
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from fraud.models import Checkout
from fraud.signals import Velocity

VELOCITY_WINDOW_SECONDS = 3600
MARKER_TTL_SECONDS = 86400

_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def reset() -> None:
    """Drop the cached table (used by tests)."""
    global _table
    _table = None


def _keys(c: Checkout) -> dict[str, str]:
    return {"card": f"CARD#{c.card_fingerprint}", "ip": f"IP#{c.ip_address}", "customer": f"CUST#{c.customer_id}"}


def _count_since(pk: str, since: int) -> int:
    resp = table().query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").between(f"TS#{since:010d}", "TS#9999999999"),
        Select="COUNT",
    )
    return int(resp["Count"])


def velocity(c: Checkout, now: int | None = None) -> Velocity:
    now = now or int(time.time())
    since = now - VELOCITY_WINDOW_SECONDS
    keys = _keys(c)
    stats = table().get_item(Key={"PK": keys["customer"], "SK": "STATS"}).get("Item")
    avg = None
    if stats and int(stats.get("order_count", 0)) > 0:
        avg = Decimal(stats["total_amount"]) / Decimal(stats["order_count"])
    return Velocity(
        customer_1h=_count_since(keys["customer"], since),
        card_1h=_count_since(keys["card"], since),
        ip_1h=_count_since(keys["ip"], since),
        customer_avg_amount=avg,
    )


def get_decision(order_id: str) -> dict[str, Any] | None:
    return table().get_item(Key={"PK": f"ORDER#{order_id}", "SK": "DECISION"}).get("Item")


def save(c: Checkout, decision: dict[str, Any], now: int | None = None) -> bool:
    """Store the decision once. Return False if the order was already scored."""
    now = now or int(time.time())
    item = {"PK": f"ORDER#{c.order_id}", "SK": "DECISION", "created_at": now, **decision}
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise

    with table().batch_writer() as batch:
        for pk in _keys(c).values():
            batch.put_item(Item={"PK": pk, "SK": f"TS#{now:010d}#{c.order_id}", "ttl": now + MARKER_TTL_SECONDS})

    # Only orders that are not declined count towards the customer's normal spend.
    if decision["decision"] != "DECLINE":
        table().update_item(
            Key={"PK": f"CUST#{c.customer_id}", "SK": "STATS"},
            UpdateExpression="ADD order_count :one, total_amount :amt",
            ExpressionAttributeValues={":one": 1, ":amt": c.amount},
        )
    return True
