import pytest

from fraud.models import ValidationError, parse_checkout


def test_valid_order_parses(order):
    c = parse_checkout(order)
    assert c.card_fingerprint == "424242-4242"
    assert c.email_domain == "example.com"


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("amount", "-1", "amount must be more than 0"),
        ("amount", "abc", "amount must be a number"),
        ("email", "not-an-email", "email is not valid"),
        ("ip_address", "999.1.1.1", "ip_address is not valid"),
        ("billing_country", "GBR", "billing_country must be a 2-letter ISO code"),
        ("card_bin", "42", "card_bin must be 6 to 8 digits"),
        ("order_id", "a b", "order_id must be"),
        ("account_age_days", "-3", "account_age_days must not be negative"),
    ],
)
def test_invalid_fields_are_rejected(order, key, value, message):
    order[key] = value
    with pytest.raises(ValidationError) as err:
        parse_checkout(order)
    assert any(message in e for e in err.value.errors)


def test_missing_fields_are_all_reported():
    with pytest.raises(ValidationError) as err:
        parse_checkout({})
    assert len(err.value.errors) >= 8


def test_non_object_body():
    with pytest.raises(ValidationError):
        parse_checkout(["x"])
