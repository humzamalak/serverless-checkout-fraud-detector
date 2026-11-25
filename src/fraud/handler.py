"""Lambda entry point for API Gateway (HTTP API, payload format 2.0).

Routes
  POST /checkouts              score a checkout, return APPROVE | REVIEW | DECLINE
  GET  /checkouts/{order_id}   return the stored decision

Environment variables
  TABLE_NAME          DynamoDB table (required)
  BEDROCK_MODEL_ID    Bedrock model or inference profile ID
  BEDROCK_ENABLED     "false" to skip Bedrock (rules only)
  APPROVE_BELOW       rule score below this is approved without Bedrock (default 20)
  DECLINE_AT          rule score at or above this is declined without Bedrock (default 80)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from decimal import Decimal
from typing import Any

from fraud import llm, store
from fraud.models import Checkout, ValidationError, parse_checkout
from fraud.signals import Signal, Velocity, evaluate, rule_score

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

REVIEW_AT = 40
FINAL_DECLINE_AT = 70


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _features(c: Checkout, v: Velocity, signals: list[Signal], score: int) -> dict[str, Any]:
    """What the model sees. No customer ID, no e-mail local part, no card digits."""
    return {
        "amount": str(c.amount),
        "currency": c.currency,
        "item_count": c.item_count,
        "account_age_days": c.account_age_days,
        "email_domain": c.email_domain,
        "billing_country": c.billing_country,
        "shipping_country": c.shipping_country,
        "orders_last_hour": {"customer": v.customer_1h, "card": v.card_1h, "ip": v.ip_1h},
        "customer_average_amount": str(v.customer_avg_amount) if v.customer_avg_amount else None,
        "rule_signals": [{"code": s.code, "detail": s.detail} for s in signals],
        "rule_score": score,
    }


def decide(score: int, llm_score: int | None) -> tuple[str, int]:
    """Combine the rule score and the model score into a decision."""
    if llm_score is None:
        final = score
    else:
        final = round((score + llm_score) / 2)
    if final >= FINAL_DECLINE_AT:
        return "DECLINE", final
    # Guardrail: the model can lower the score, but an order the rules flag for
    # review is never approved on the model's word alone.
    if final >= REVIEW_AT or score >= REVIEW_AT:
        return "REVIEW", final
    return "APPROVE", final


def score_checkout(c: Checkout) -> dict[str, Any]:
    approve_below = int(os.environ.get("APPROVE_BELOW", "20"))
    decline_at = int(os.environ.get("DECLINE_AT", "80"))
    bedrock_on = os.environ.get("BEDROCK_ENABLED", "true").lower() == "true"

    v = store.velocity(c)
    signals = evaluate(c, v)
    score = rule_score(signals)
    reasons = [s.detail for s in signals]
    result: dict[str, Any] = {"order_id": c.order_id, "rule_score": score, "signals": [s.code for s in signals]}

    if score < approve_below:
        decision, final, source = "APPROVE", score, "rules"
    elif score >= decline_at:
        decision, final, source = "DECLINE", score, "rules"
    elif not bedrock_on:
        decision, final = decide(score, None)
        source = "rules"
    else:
        try:
            answer = llm.assess(_features(c, v, signals, score))
            decision, final = decide(score, answer.risk_score)
            result["llm_score"] = answer.risk_score
            reasons += answer.reasons
            source = "rules+bedrock"
        except llm.LlmError as exc:
            # Never approve blind: if the model is down, a person reviews the order.
            logger.warning("bedrock unavailable, sending to review: %s", exc)
            decision, final, source = "REVIEW", score, "rules (bedrock unavailable)"

    result.update({"decision": decision, "risk_score": final, "reasons": reasons, "source": source})
    return result


def _post(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw)
    except ValueError:
        return _response(400, {"error": "body must be valid JSON"})
    try:
        checkout = parse_checkout(body)
    except ValidationError as exc:
        return _response(400, {"error": "invalid checkout", "details": exc.errors})

    existing = store.get_decision(checkout.order_id)
    if existing:
        return _response(200, {**_public(existing), "idempotent_replay": True})

    started = time.perf_counter()
    result = score_checkout(checkout)
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    if not store.save(checkout, result):
        return _response(200, {**_public(store.get_decision(checkout.order_id) or result), "idempotent_replay": True})

    logger.info(json.dumps({"scored": result}, default=str))
    return _response(200, result)


def _plain(value: Any) -> Any:
    """DynamoDB returns numbers as Decimal. Convert them back for JSON."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _plain(v) for k, v in item.items() if k not in ("PK", "SK")}


def _get(event: dict[str, Any]) -> dict[str, Any]:
    order_id = (event.get("pathParameters") or {}).get("order_id", "")
    item = store.get_decision(order_id)
    if not item:
        return _response(404, {"error": "order not found"})
    return _response(200, _public(item))


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    route = event.get("routeKey", "")
    if route == "POST /checkouts":
        return _post(event)
    if route == "GET /checkouts/{order_id}":
        return _get(event)
    return _response(404, {"error": f"unknown route {route}"})
