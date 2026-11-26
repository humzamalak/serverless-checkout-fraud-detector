import json

from fraud import handler


def post(order):
    return handler.lambda_handler({"routeKey": "POST /checkouts", "body": json.dumps(order)})


def body(resp):
    return json.loads(resp["body"])


def test_clean_order_is_approved_without_bedrock(table, order, bedrock):
    fake = bedrock(text='{"risk_score": 99}')
    resp = post(order)
    assert resp["statusCode"] == 200
    data = body(resp)
    assert data["decision"] == "APPROVE"
    assert data["source"] == "rules"
    assert fake.calls == []


def test_grey_zone_order_uses_bedrock(table, order, bedrock):
    fake = bedrock(text='{"risk_score": 90, "reasons": ["reshipping pattern"]}')
    order.update(shipping_country="NG", account_age_days=0)  # 15 + 10 = 25 -> grey zone
    data = body(post(order))
    assert data["rule_score"] == 25
    assert data["llm_score"] == 90
    assert data["risk_score"] == 58  # round((25 + 90) / 2)
    assert data["decision"] == "REVIEW"
    assert "reshipping pattern" in data["reasons"]
    sent = fake.calls[0]["messages"][0]["content"][0]["text"]
    assert "jane" not in sent and "4242" not in sent and "cus-42" not in sent


def test_bedrock_failure_sends_order_to_review(table, order, bedrock):
    bedrock(error=RuntimeError("throttled"))
    order.update(shipping_country="NG", account_age_days=0)
    data = body(post(order))
    assert data["decision"] == "REVIEW"
    assert "unavailable" in data["source"]


def test_high_rule_score_is_declined_without_bedrock(table, order, bedrock, monkeypatch):
    monkeypatch.setenv("DECLINE_AT", "70")
    fake = bedrock(text='{"risk_score": 0}')
    order.update(email="x@mailinator.com", shipping_country="NG", account_age_days=0, amount="2500", item_count=15)
    data = body(post(order))
    assert data["decision"] == "DECLINE"
    assert fake.calls == []


def test_rules_only_mode(table, order, monkeypatch):
    monkeypatch.setenv("BEDROCK_ENABLED", "false")
    order.update(shipping_country="NG", account_age_days=0, email="x@mailinator.com")  # 45
    data = body(post(order))
    assert data["decision"] == "REVIEW"
    assert data["source"] == "rules"


def test_card_velocity_raises_score(table, order, monkeypatch):
    monkeypatch.setenv("BEDROCK_ENABLED", "false")
    for i in range(3):
        post({**order, "order_id": f"ord-{i}", "customer_id": f"cus-{i}", "ip_address": f"198.51.100.{i}"})
    data = body(post({**order, "order_id": "ord-next"}))
    assert "CARD_VELOCITY" in data["signals"]


def test_same_order_id_is_idempotent(table, order, bedrock):
    bedrock(text='{"risk_score": 10}')
    first = body(post(order))
    second = body(post({**order, "amount": "9999"}))
    assert second["idempotent_replay"] is True
    assert second["decision"] == first["decision"]
    assert second["rule_score"] == first["rule_score"]


def test_get_returns_stored_decision(table, order, bedrock):
    post(order)
    resp = handler.lambda_handler({"routeKey": "GET /checkouts/{order_id}", "pathParameters": {"order_id": "ord-1001"}})
    assert resp["statusCode"] == 200
    assert body(resp)["decision"] == "APPROVE"
    assert "PK" not in body(resp)


def test_get_unknown_order_is_404(table):
    resp = handler.lambda_handler({"routeKey": "GET /checkouts/{order_id}", "pathParameters": {"order_id": "nope"}})
    assert resp["statusCode"] == 404


def test_invalid_json_is_400(table):
    assert handler.lambda_handler({"routeKey": "POST /checkouts", "body": "{"})["statusCode"] == 400


def test_invalid_order_is_400(table, order):
    order["amount"] = "-5"
    resp = post(order)
    assert resp["statusCode"] == 400
    assert body(resp)["details"]


def test_unknown_route_is_404(table):
    assert handler.lambda_handler({"routeKey": "DELETE /x"})["statusCode"] == 404


def test_decide_thresholds():
    assert handler.decide(30, 10) == ("APPROVE", 20)
    assert handler.decide(50, 50) == ("REVIEW", 50)
    assert handler.decide(60, 90) == ("DECLINE", 75)
    assert handler.decide(45, None) == ("REVIEW", 45)
    assert handler.decide(45, 0) == ("REVIEW", 22)


def test_model_cannot_approve_an_order_the_rules_flag(table, order, bedrock):
    bedrock(text='{"risk_score": 0, "reasons": ["looks fine"]}')
    order.update(email="x@mailinator.com", shipping_country="NG", account_age_days=0, amount="2500", item_count=15)
    data = body(post(order))
    assert data["rule_score"] == 70
    assert data["risk_score"] == 35
    assert data["decision"] == "REVIEW"
