"""Request validation for the checkout payload."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
MAX_AMOUNT = Decimal("100000")


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Checkout:
    order_id: str
    customer_id: str
    email: str
    amount: Decimal
    currency: str
    ip_address: str
    billing_country: str
    shipping_country: str
    card_bin: str
    card_last4: str
    account_age_days: int
    item_count: int
    device_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def email_domain(self) -> str:
        return self.email.rsplit("@", 1)[-1].lower()

    @property
    def card_fingerprint(self) -> str:
        # Never store a full card number. BIN + last 4 is enough for velocity checks.
        return f"{self.card_bin}-{self.card_last4}"


def _req(body: dict[str, Any], key: str, errors: list[str]) -> Any:
    value = body.get(key)
    if value is None or value == "":
        errors.append(f"{key} is required")
    return value


def parse_checkout(body: Any) -> Checkout:
    if not isinstance(body, dict):
        raise ValidationError(["body must be a JSON object"])
    errors: list[str] = []

    order_id = _req(body, "order_id", errors)
    customer_id = _req(body, "customer_id", errors)
    for key, value in (("order_id", order_id), ("customer_id", customer_id)):
        if value is not None and not ID_RE.match(str(value)):
            errors.append(f"{key} must be 1-64 letters, digits, '-' or '_'")

    email = str(_req(body, "email", errors) or "")
    if email and not EMAIL_RE.match(email):
        errors.append("email is not valid")

    amount = Decimal("0")
    try:
        amount = Decimal(str(_req(body, "amount", errors)))
        if amount <= 0 or amount > MAX_AMOUNT:
            errors.append(f"amount must be more than 0 and at most {MAX_AMOUNT}")
    except (InvalidOperation, TypeError):
        errors.append("amount must be a number")

    currency = str(body.get("currency", "GBP")).upper()
    if not CURRENCY_RE.match(currency):
        errors.append("currency must be a 3-letter ISO code")

    ip = str(_req(body, "ip_address", errors) or "")
    try:
        if ip:
            ipaddress.ip_address(ip)
    except ValueError:
        errors.append("ip_address is not valid")

    countries = {}
    for key in ("billing_country", "shipping_country"):
        value = str(_req(body, key, errors) or "").upper()
        if value and not COUNTRY_RE.match(value):
            errors.append(f"{key} must be a 2-letter ISO code")
        countries[key] = value

    card_bin = str(_req(body, "card_bin", errors) or "")
    card_last4 = str(_req(body, "card_last4", errors) or "")
    if card_bin and not re.fullmatch(r"\d{6,8}", card_bin):
        errors.append("card_bin must be 6 to 8 digits")
    if card_last4 and not re.fullmatch(r"\d{4}", card_last4):
        errors.append("card_last4 must be 4 digits")

    def _int(key: str, default: int) -> int:
        try:
            value = int(body.get(key, default))
        except (TypeError, ValueError):
            errors.append(f"{key} must be an integer")
            return default
        if value < 0:
            errors.append(f"{key} must not be negative")
        return value

    account_age_days = _int("account_age_days", 0)
    item_count = _int("item_count", 1)

    if errors:
        raise ValidationError(errors)

    return Checkout(
        order_id=str(order_id),
        customer_id=str(customer_id),
        email=email,
        amount=amount,
        currency=currency,
        ip_address=ip,
        billing_country=countries["billing_country"],
        shipping_country=countries["shipping_country"],
        card_bin=card_bin,
        card_last4=card_last4,
        account_age_days=account_age_days,
        item_count=item_count,
        device_id=str(body.get("device_id", ""))[:128],
    )
