import boto3
import pytest
from moto import mock_aws

from fraud import llm, store


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("TABLE_NAME", "fraud")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="fraud",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        )
        store.reset()
        monkeypatch.setattr(llm, "_client", None)
        yield
        store.reset()


@pytest.fixture
def order():
    return {
        "order_id": "ord-1001",
        "customer_id": "cus-42",
        "email": "jane@example.com",
        "amount": "59.99",
        "currency": "GBP",
        "ip_address": "203.0.113.10",
        "billing_country": "GB",
        "shipping_country": "GB",
        "card_bin": "424242",
        "card_last4": "4242",
        "account_age_days": 400,
        "item_count": 2,
    }


class FakeBedrock:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


@pytest.fixture
def bedrock(monkeypatch):
    def install(text=None, error=None):
        fake = FakeBedrock(text, error)
        monkeypatch.setattr(llm, "_client", fake)
        return fake

    return install
