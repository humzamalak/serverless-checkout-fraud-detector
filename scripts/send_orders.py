#!/usr/bin/env python3
"""Send three sample checkouts (clean, grey zone, high risk) to the deployed API.

Usage: python scripts/send_orders.py https://abc123.execute-api.us-east-1.amazonaws.com
Requests are signed with SigV4 using your normal AWS credentials (api_authorization = AWS_IAM).
"""

import json
import sys
import time
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

BASE = {
    "currency": "GBP",
    "ip_address": "203.0.113.10",
    "billing_country": "GB",
    "card_bin": "424242",
    "card_last4": "4242",
}
SAMPLES = {
    "clean": {"email": "jane@example.com", "amount": "42.50", "shipping_country": "GB", "account_age_days": 700},
    "grey zone": {"email": "sam@example.com", "amount": "180.00", "shipping_country": "NG", "account_age_days": 0},
    "high risk": {
        "email": "x@mailinator.com",
        "amount": "2400.00",
        "shipping_country": "NG",
        "account_age_days": 0,
        "item_count": 15,
    },
}


def send(url: str, payload: dict) -> dict:
    session = boto3.Session()
    region = url.split(".")[2]
    data = json.dumps(payload).encode()
    req = AWSRequest(method="POST", url=f"{url}/checkouts", data=data, headers={"Content-Type": "application/json"})
    SigV4Auth(session.get_credentials(), "execute-api", region).add_auth(req)
    http = urllib.request.Request(req.url, data=data, headers=dict(req.headers), method="POST")
    with urllib.request.urlopen(http, timeout=20) as resp:  # noqa: S310 - URL comes from the user
        return json.loads(resp.read())


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    url = sys.argv[1].rstrip("/")
    run = int(time.time())
    for i, (label, fields) in enumerate(SAMPLES.items()):
        order = {**BASE, **fields, "order_id": f"demo-{run}-{i}", "customer_id": f"demo-cus-{run}-{i}"}
        result = send(url, order)
        print(f"{label:>10}: {result['decision']:<8} score={result['risk_score']:<3} source={result['source']}")
        for reason in result.get("reasons", []):
            print(f"{'':>12}- {reason}")


if __name__ == "__main__":
    main()
