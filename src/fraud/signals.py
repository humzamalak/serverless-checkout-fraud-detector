"""Deterministic fraud signals. Each signal adds points to a 0-100 rule score.

The weights are starting values for a demo, not tuned on real data.
Tune them on your own labelled orders before you trust them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fraud.models import Checkout

# Small sample list. In production, use a maintained list or a vendor API.
DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "trashmail.com",
    "yopmail.com",
    "sharklasers.com",
}


@dataclass
class Signal:
    code: str
    points: int
    detail: str


@dataclass
class Velocity:
    """Orders seen in the last hour for the same key (from DynamoDB)."""

    customer_1h: int = 0
    card_1h: int = 0
    ip_1h: int = 0
    customer_avg_amount: Decimal | None = None


def evaluate(c: Checkout, v: Velocity) -> list[Signal]:
    s: list[Signal] = []

    if c.billing_country != c.shipping_country:
        s.append(Signal("COUNTRY_MISMATCH", 15, f"billing {c.billing_country}, shipping {c.shipping_country}"))

    if c.email_domain in DISPOSABLE_EMAIL_DOMAINS:
        s.append(Signal("DISPOSABLE_EMAIL", 20, f"email domain {c.email_domain}"))

    if c.account_age_days < 1:
        s.append(Signal("NEW_ACCOUNT", 10, "account created today"))

    if v.card_1h >= 3:
        s.append(Signal("CARD_VELOCITY", 25, f"{v.card_1h} orders on this card in the last hour"))
    if v.ip_1h >= 5:
        s.append(Signal("IP_VELOCITY", 20, f"{v.ip_1h} orders from this IP in the last hour"))
    if v.customer_1h >= 4:
        s.append(Signal("CUSTOMER_VELOCITY", 15, f"{v.customer_1h} orders by this customer in the last hour"))

    if v.customer_avg_amount and v.customer_avg_amount > 0 and c.amount > v.customer_avg_amount * 5:
        s.append(Signal("AMOUNT_SPIKE", 20, f"amount {c.amount} is over 5x the customer average"))
    elif v.customer_avg_amount is None and c.amount >= Decimal("1000"):
        s.append(Signal("HIGH_FIRST_ORDER", 15, f"first order of {c.amount} {c.currency}"))

    if c.item_count >= 10:
        s.append(Signal("BULK_ITEMS", 10, f"{c.item_count} items"))

    return s


def rule_score(signals: list[Signal]) -> int:
    return min(100, sum(sig.points for sig in signals))
