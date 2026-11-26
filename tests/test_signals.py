from decimal import Decimal

from fraud.models import parse_checkout
from fraud.signals import Velocity, evaluate, rule_score


def codes(order, velocity=None):
    return {s.code for s in evaluate(parse_checkout(order), velocity or Velocity(customer_avg_amount=Decimal("50")))}


def test_normal_order_has_no_signals(order):
    assert codes(order) == set()


def test_risky_order_collects_signals(order):
    order.update(email="x@mailinator.com", shipping_country="NG", account_age_days=0, amount="900", item_count=12)
    found = codes(order, Velocity(card_1h=3, ip_1h=6, customer_1h=4, customer_avg_amount=Decimal("40")))
    assert found == {
        "COUNTRY_MISMATCH",
        "DISPOSABLE_EMAIL",
        "NEW_ACCOUNT",
        "CARD_VELOCITY",
        "IP_VELOCITY",
        "CUSTOMER_VELOCITY",
        "AMOUNT_SPIKE",
        "BULK_ITEMS",
    }


def test_high_first_order(order):
    order["amount"] = "1500"
    assert "HIGH_FIRST_ORDER" in codes(order, Velocity())


def test_score_is_capped_at_100(order):
    order.update(email="x@mailinator.com", shipping_country="NG", account_age_days=0, item_count=12)
    signals = evaluate(parse_checkout(order), Velocity(card_1h=9, ip_1h=9, customer_1h=9))
    assert rule_score(signals) == 100
