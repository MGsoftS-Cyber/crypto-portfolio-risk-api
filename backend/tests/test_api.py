from uuid import uuid4
from pathlib import Path
from decimal import Decimal
import pytest
from fastapi import HTTPException
from app import market

ORIGIN = {"Origin": "http://localhost:8008"}


def register(client, email="engineer@example.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "Crypto-Password-2026"}, headers=ORIGIN)
    assert r.status_code == 201
    return {**ORIGIN, "X-CSRF-Token": r.json()["csrf_token"]}


def write(client, path, body=None, h=None, key=None):
    return client.post("/api/v1" + path, json=body, headers={**(h or {}), "Idempotency-Key": key or str(uuid4())})


def setup(client):
    h = register(client)
    d = write(client, "/demo", h=h).json()
    r = write(
        client, f"/portfolios/{d['portfolio_id']}/analyses", {"dataset_id": d["dataset_id"], "as_of": d["as_of"]}, h
    )
    assert r.status_code == 201, r.text
    return h, d, r.json()


def test_demo_analysis_exports_and_model(client):
    h, d, a = setup(client)
    assert len(a["results"]["holdings"]) == 2
    assert a["results"]["ml"]["status"] == "scored" and a["results"]["risk"]["max_drawdown"] > 0
    assert any(x["code"] == "DAILY_CHANGE" for x in a["results"]["alerts"])
    for fmt in ["json", "holdings", "history", "trades", "alerts"]:
        r = client.get(f"/api/v1/analyses/{a['id']}/report?format={fmt}")
        assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert client.get(f"/api/v1/analyses/{a['id']}").json() == a
    assert write(client, "/demo", h=h).status_code == 409


def test_auth_owner_csrf_session_and_logout(client):
    assert client.get("/api/v1/portfolios").status_code == 401
    h, d, a = setup(client)
    assert write(client, "/portfolios", {"name": "Other"}, h=ORIGIN).status_code == 403
    assert write(client, "/portfolios", {"name": "Other"}, h={**h, "Origin": "https://bad.example"}).status_code == 403
    assert client.get("/api/auth/session").json()["csrf_token"] == h["X-CSRF-Token"]
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/auth/session").status_code == 401
    h2 = register(client, "other@example.com")
    assert client.get(f"/api/v1/portfolios/{d['portfolio_id']}/datasets").status_code == 404
    assert client.get(f"/api/v1/analyses/{a['id']}/report").status_code == 404
    assert client.get("/api/v1/analyses").json() == []
    assert (
        write(
            client,
            f"/portfolios/{d['portfolio_id']}/analyses",
            {"dataset_id": d["dataset_id"], "as_of": d["as_of"]},
            h2,
        ).status_code
        == 404
    )


def test_idempotency_conflict_and_dataset_dedup(client):
    h = register(client)
    s = write(client, "/portfolios", {"name": "P"}, h, "same")
    assert write(client, "/portfolios", {"name": "P"}, h, "same").json() == s.json()
    assert write(client, "/portfolios", {"name": "Q"}, h, "same").status_code == 409
    assert client.post("/api/v1/portfolios", json={"name": "R"}, headers=h).status_code == 422
    root = Path(__file__).resolve().parents[2] / "examples"
    preview = write(
        client,
        "/imports/preview",
        {"transactions_csv": (root / "transactions.csv").read_text(), "prices_csv": (root / "prices.csv").read_text()},
        h,
    ).json()
    assert preview["valid"]
    body = dict(
        source="Fixture", coverage_end="2026-01-02", transactions=preview["transactions"], prices=preview["prices"]
    )
    d = write(client, f"/portfolios/{s.json()['id']}/datasets", body, h)
    assert d.status_code == 201
    assert write(client, f"/portfolios/{s.json()['id']}/datasets", body, h).json() == d.json()
    a = write(
        client,
        f"/portfolios/{s.json()['id']}/analyses",
        dict(dataset_id=d.json()["id"], as_of="2026-01-02", enable_ml=False),
        h,
    ).json()
    assert Decimal(a["results"]["summary"]["total_pnl"]) == 81


def test_missing_daily_price_and_bad_dataset_no_partial_write(client):
    h = register(client)
    p = write(client, "/portfolios", {"name": "P"}, h).json()["id"]
    rows = [
        dict(transaction_id="D", date="2026-01-01", sequence=1, kind="deposit", amount="100"),
        dict(
            transaction_id="B",
            date="2026-01-01",
            sequence=2,
            kind="buy",
            asset_id="bitcoin",
            quantity="1",
            unit_price="100",
        ),
    ]
    body = dict(source="No prices", coverage_end="2026-01-02", transactions=rows, prices=[])
    d = write(client, f"/portfolios/{p}/datasets", body, h)
    assert d.status_code == 201
    r = write(client, f"/portfolios/{p}/analyses", dict(dataset_id=d.json()["id"], as_of="2026-01-02"), h)
    assert r.status_code == 422 and "Missing exact" in r.text and client.get("/api/v1/analyses").json() == []
    body["transactions"][1]["quantity"] = "2"
    assert write(client, f"/portfolios/{p}/datasets", body, h).status_code == 422
    assert len(client.get(f"/api/v1/portfolios/{p}/datasets").json()) == 1


def test_market_disabled_and_invalid_inputs(client, monkeypatch):
    monkeypatch.delenv("COINGECKO_DEMO_API_KEY", raising=False)
    h = register(client)
    assert write(client, "/market/quotes", {"asset_ids": ["bitcoin"]}, h).status_code == 503
    assert write(client, "/market/quotes", {"asset_ids": ["bitcoin", "bitcoin"]}, h).status_code == 422
    assert write(client, "/portfolios", {"name": "P", "base_currency": "EUR"}, h).status_code == 422


@pytest.mark.parametrize("case", ["valid", "missing", "rate", "stale"])
def test_market_mock_contract(monkeypatch, case):
    import time

    monkeypatch.setenv("COINGECKO_DEMO_API_KEY", "test-not-a-real-secret")

    class Fake:
        def __init__(self, **kw):
            assert kw["timeout"] == 10 and not kw["follow_redirects"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, params, headers):
            assert url == "https://api.coingecko.com/api/v3/simple/price"
            assert params["ids"] == "bitcoin"
            self.status_code = 429 if case == "rate" else 200
            return self

        def raise_for_status(self):
            pass

        def json(self):
            return (
                {}
                if case == "missing"
                else {"bitcoin": {"usd": 123, "last_updated_at": int(time.time()) - (1000 if case == "stale" else 5)}}
            )

    monkeypatch.setattr(market.httpx, "Client", Fake)
    if case in {"missing", "rate"}:
        with pytest.raises(HTTPException) as error:
            market.quotes(["bitcoin"])
        assert error.value.status_code == (503 if case == "rate" else 502)
    else:
        result = market.quotes(["bitcoin"])
        assert result["quotes"][0]["price"] == "123" and result["quotes"][0]["stale"] == (case == "stale")
