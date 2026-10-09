from decimal import Decimal
import json
import pytest
from app.schemas import DatasetInput, TransactionInput
from app.imports import normalize, preview
from app.engine import evaluate
from app.risk import metrics, detect


def tx(kind="deposit", **kw):
    base = dict(transaction_id="D1", date="2026-01-01", sequence=1, kind=kind, amount="1000")
    if kind in {"buy", "sell"}:
        base.update(asset_id="bitcoin", quantity="1", unit_price="100", amount="0")
    return {**base, **kw}


def inputs(transactions=None, prices=None, **kw):
    data = DatasetInput(
        source="Test",
        coverage_end="2026-01-02",
        transactions=transactions or [tx(), tx("buy", transaction_id="B1", sequence=2)],
        prices=prices
        if prices is not None
        else [
            dict(date="2026-01-01", asset_id="bitcoin", close="100"),
            dict(date="2026-01-02", asset_id="bitcoin", close="140"),
        ],
    )
    t, p, q = normalize(data.transactions, data.prices, data.coverage_end)
    return dict(
        transactions=t,
        prices=p,
        coverage_end="2026-01-02",
        as_of="2026-01-02",
        enable_ml=False,
        concentration_limit=0.6,
        daily_change_limit=0.1,
        turnover_limit=0.5,
        quality=q,
        **kw,
    )


def test_fee_aware_worked_example():
    r = evaluate(
        inputs(
            [
                tx(fee="2"),
                tx("buy", transaction_id="B1", sequence=2, quantity="2", fee="4"),
                tx("sell", transaction_id="S1", date="2026-01-02", quantity="1", unit_price="150", fee="3"),
            ]
        )
    )
    s = r["summary"]
    h = r["holdings"][0]
    assert Decimal(s["cash"]) == 941 and Decimal(s["equity"]) == 1081
    assert Decimal(h["cost_basis"]) == 102 and Decimal(h["unrealized_pnl"]) == 38
    assert Decimal(s["realized_pnl"]) == 45 and Decimal(s["total_pnl"]) == 81
    assert Decimal(s["total_fees"]) == 9


def test_full_sale_removes_cost_and_retains_realized():
    r = evaluate(
        inputs(
            [
                tx(),
                tx("buy", transaction_id="B", sequence=2, quantity="3", unit_price="0.1"),
                tx("sell", transaction_id="S", date="2026-01-02", quantity="3", unit_price="0.2"),
            ],
            prices=[dict(date="2026-01-01", asset_id="bitcoin", close="0.1")],
        )
    )
    assert r["holdings"] == [] and Decimal(r["summary"]["realized_pnl"]) == Decimal(".3")
    assert r["closed_positions"][0]["asset_id"] == "bitcoin"


def test_cash_flows_do_not_create_returns_or_drawdown():
    t = [
        tx(),
        tx("buy", transaction_id="B", sequence=2, unit_price="1000"),
        tx(date="2026-01-02", transaction_id="D2", amount="500"),
    ]
    prices = [dict(date=d, asset_id="bitcoin", close="1000") for d in ["2026-01-01", "2026-01-02"]]
    r = evaluate(inputs(t, prices))
    assert r["risk"]["cumulative_return"] == 0 and r["risk"]["max_drawdown"] == 0
    assert Decimal(r["summary"]["net_contributions"]) == 1500


def test_exact_missing_price_fails_no_forward_fill():
    with pytest.raises(ValueError, match="Missing exact daily price"):
        evaluate(inputs(prices=[dict(date="2026-01-01", asset_id="bitcoin", close="100")]))


def test_zero_capital_gap_risk_unavailable():
    r = evaluate(inputs([tx(), tx("withdrawal", transaction_id="W", date="2026-01-02", amount="1000")], prices=[]))
    assert r["risk"]["status"] == "unavailable_zero_capital_gap" and r["risk"]["max_drawdown"] is None


@pytest.mark.parametrize(
    "rows,message",
    [
        ([tx("buy")], "Insufficient cash"),
        ([tx(), tx("sell", transaction_id="S", sequence=2)], "Sell exceeds"),
        ([tx(), tx("withdrawal", transaction_id="W", sequence=2, amount="2000")], "Insufficient cash"),
        ([tx(fee="1001")], "Deposit fee exceeds"),
        (
            [
                tx(),
                tx("buy", transaction_id="B", sequence=2),
                tx("sell", transaction_id="S", date="2026-01-02", fee="101"),
            ],
            "Sell fee exceeds",
        ),
        (
            [tx(), tx("buy", transaction_id="B", sequence=2), tx(transaction_id="D2", sequence=3)],
            "Cash flows must precede",
        ),
        ([tx(), tx(transaction_id="D2")], "Sequence"),
        ([tx(), tx(sequence=2)], "Duplicate transaction"),
    ],
)
def test_invalid_ledger(rows, message):
    with pytest.raises(ValueError, match=message):
        inputs(rows, prices=[])


@pytest.mark.parametrize(
    "change",
    [dict(amount=100), dict(amount="NaN"), dict(amount="-1"), dict(fee=True), dict(sequence=1.5), dict(unknown="x")],
)
def test_strict_decimal_contract(change):
    with pytest.raises(ValueError):
        TransactionInput(**tx(**change))


def test_price_duplicates_future_coverage_untraded():
    p = [dict(date="2026-01-01", asset_id="bitcoin", close="100")] * 2
    with pytest.raises(ValueError, match="Duplicate daily"):
        inputs(prices=p)
    with pytest.raises(ValueError, match="not traded"):
        inputs(prices=[dict(date="2026-01-01", asset_id="unknown", close="1")])
    i = inputs()
    i["as_of"] = "2026-01-03"
    with pytest.raises(ValueError, match="coverage"):
        evaluate(i)


def test_drawdown_and_volatility_tail_sign():
    r = [0] + [0.01, -0.02, 0.005] * 10
    rows = [dict(daily_return=x) for x in r]
    out = metrics(rows)
    assert out["observations"] == 30 and out["historical_var_95"] == pytest.approx(0.02)
    assert out["historical_es_95"] == pytest.approx(0.02) and out["max_drawdown"] > 0
    assert out["annualized_volatility"] > 0


def test_short_history_and_numeric_range():
    assert metrics([dict(daily_return=0), dict(daily_return=0.01)])["historical_var_95"] is None
    assert metrics([dict(daily_return=0), dict(daily_return=1e20)])["status"] == "unavailable_numeric_range"


def test_rules_explain_evidence():
    row = dict(date="2026-01-01", daily_return=-0.2, turnover=0.8, max_crypto_allocation=0.9, largest_asset="bitcoin")
    alerts, ml = detect(
        [row], dict(enable_ml=False, concentration_limit=0.6, daily_change_limit=0.1, turnover_limit=0.5)
    )
    assert {x["code"] for x in alerts} == {"CONCENTRATION", "DAILY_CHANGE", "TURNOVER"}
    assert ml["status"] == "disabled" and all(x["evidence"] for x in alerts)


def test_ml_temporal_holdout_determinism_no_leakage():
    rows = [
        dict(
            date=f"{i:03d}",
            daily_return=((i % 7) - 3) * 0.002,
            turnover=(i % 5) * 0.01,
            max_crypto_allocation=0.4 + (i % 3) * 0.01,
            largest_asset="bitcoin",
        )
        for i in range(51)
    ]
    options = dict(enable_ml=True, concentration_limit=0.6, daily_change_limit=0.1, turnover_limit=0.5)
    a, m = detect(rows, options)
    assert m["training_days"] == 30 and m["scoring_days"] == 20
    assert detect(rows, options) == (a, m)
    assert m["training_end"] == "030" and m["scores"][0]["date"] == "031"
    changed = [dict(x) for x in rows]
    changed[-1]["daily_return"] = -0.6
    _, new = detect(changed, options)
    assert m["scores"][:-1] == new["scores"][:-1]
    assert detect(rows[:15], options)[1]["status"] == "insufficient_history"
    json.dumps(new, allow_nan=False)


def test_csv_preview_preserves_decimals_and_detects_errors():
    from pathlib import Path

    r = Path(__file__).resolve().parents[2] / "examples"
    txtext = (r / "transactions.csv").read_text()
    px = (r / "prices.csv").read_text()
    out = preview(txtext, px)
    assert out["valid"] and out["transactions"][1]["quantity"] == "2"
    assert not preview(txtext.replace(",2,buy", ",2.5,buy"), px)["valid"]
    assert not preview(txtext.replace("B1", "D1"), px)["valid"]
    assert not preview(txtext.replace(",2,100,", ",2000,100,"), px)["valid"]


def test_second_purchase_changes_weighted_pool():
    transactions = [
        tx(),
        tx("buy", transaction_id="B1", sequence=2, quantity="1", unit_price="100", fee="2"),
        tx("buy", transaction_id="B2", date="2026-01-02", sequence=1, quantity="1", unit_price="200", fee="4"),
    ]
    result = evaluate(inputs(transactions))
    holding = result["holdings"][0]
    assert Decimal(holding["cost_basis"]) == 306
    assert Decimal(holding["average_cost"]) == 153
    assert Decimal(result["summary"]["total_pnl"]) == -26


def test_withdrawal_fee_is_expense_not_double_counted():
    result = evaluate(
        inputs([tx(), tx("withdrawal", transaction_id="W", date="2026-01-02", amount="100", fee="3")], prices=[])
    )
    assert Decimal(result["summary"]["net_contributions"]) == 900
    assert Decimal(result["summary"]["cash"]) == 897
    assert Decimal(result["summary"]["total_pnl"]) == -3
