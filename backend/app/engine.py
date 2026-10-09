"""Replay a frozen ledger into daily values, allocation and explained risk evidence."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import localcontext
from .ledger import Ledger, dec, text, ZERO
from .risk import metrics, detect

ENGINE_VERSION = "1.0.0"


def evaluate(inputs):
    if inputs["as_of"] > inputs["coverage_end"]:
        raise ValueError("Analysis date exceeds dataset coverage.")
    selected = [x for x in inputs["transactions"] if x["date"] <= inputs["as_of"]]
    if not selected:
        raise ValueError("No transactions on or before analysis date.")
    prices = {(x["date"], x["asset_id"]): x["close"] for x in inputs["prices"]}
    by_day = defaultdict(list)
    for x in selected:
        by_day[x["date"]].append(x)
    first = date.fromisoformat(selected[0]["date"])
    last = date.fromisoformat(inputs["as_of"])
    ledger = Ledger()
    history = []
    trades = []
    previous = ZERO
    snapshot = None
    with localcontext() as context:
        context.prec = 60
        for offset in range((last - first).days + 1):
            day = str(first + timedelta(days=offset))
            flow = ZERO
            notional = ZERO
            for tx in by_day[day]:
                trade_notional = ledger.apply(tx)
                if tx["kind"] == "deposit":
                    flow += dec(tx["amount"])
                elif tx["kind"] == "withdrawal":
                    flow -= dec(tx["amount"])
                else:
                    notional += trade_notional
                    trades.append(dict(**tx, notional=text(trade_notional)))
            snapshot = ledger.value(day, prices)
            equity = dec(snapshot["equity"])
            capital = previous + flow
            if capital < 0:
                raise ValueError("Beginning-of-day cash-flow capital cannot be negative.")
            ret = float(equity / capital - 1) if capital > 0 else None
            holdings = snapshot["holdings"]
            largest = max(holdings, key=lambda x: x["allocation"]) if holdings else None
            history.append(
                dict(
                    date=day,
                    **{k: v for k, v in snapshot.items() if k != "holdings"},
                    external_flow=text(flow),
                    trade_notional=text(notional),
                    daily_return=ret,
                    turnover=float(notional / capital) if capital > 0 else None,
                    max_crypto_allocation=largest["allocation"] if largest else 0.0,
                    largest_asset=largest["asset_id"] if largest else None,
                    return_index=None,
                    drawdown=None,
                )
            )
            previous = equity
    risk = metrics(history)
    alerts, ml = detect(history, inputs)
    warnings = [
        "Daily prices are supplied snapshots; valuation fails on missing held-asset prices instead of filling gaps.",
        "Returns assume external cash flows occur at the beginning of the UTC day. Intraday timing requires a richer ledger.",
        "Tail risk is historical one-day loss estimation; volatility uses 365-day annualization. These are descriptive statistics, not guaranteed bounds.",
        "AI alerts are unsupervised novelty flags with observed evidence. They do not establish fraud, causation or future price direction.",
    ]
    if risk["status"] == "unavailable_zero_capital_gap":
        warnings.append(
            "A zero-capital day breaks the full-period return chain; return and drawdown risk metrics are unavailable."
        )
    if risk["observations"] < 30:
        warnings.append(
            "Fewer than 30 post-initial daily returns; historical VaR and expected shortfall are unavailable."
        )
    if risk["status"] == "unavailable_numeric_range":
        warnings.append(
            "Extreme numeric return range; risk statistics are unavailable while decimal accounting remains intact."
        )
    closed = [
        dict(asset_id=a, realized_pnl=text(p["realized"]), trade_fees=text(p["fees"]))
        for a, p in sorted(ledger.positions.items())
        if p["quantity"] == 0
    ]
    return dict(
        summary={k: v for k, v in snapshot.items() if k != "holdings"},
        holdings=snapshot["holdings"],
        closed_positions=closed,
        history=history,
        trades=trades,
        risk=risk,
        alerts=alerts,
        ml=ml,
        warnings=warnings,
    )
