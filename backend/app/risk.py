"""Historical descriptive risk on a cash-flow-adjusted daily series."""

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn import __version__ as sklearn_version


def metrics(history):
    returns = [x["daily_return"] for x in history]
    # An unfunded/fully withdrawn day breaks a full-period return chain.
    if any(x is None for x in returns):
        return dict(
            status="unavailable_zero_capital_gap",
            observations=sum(x is not None for x in returns),
            cumulative_return=None,
            max_drawdown=None,
            annualized_volatility=None,
            historical_var_95=None,
            historical_es_95=None,
        )
    r = np.asarray(returns, dtype=float)
    if np.any(np.abs(r) > 1e6):
        return dict(
            status="unavailable_numeric_range",
            observations=len(r) - 1,
            cumulative_return=None,
            max_drawdown=None,
            annualized_volatility=None,
            historical_var_95=None,
            historical_es_95=None,
        )
    with np.errstate(over="ignore", invalid="ignore"):
        indices = np.cumprod(1 + r)
    if not np.all(np.isfinite(indices)):
        return dict(
            status="unavailable_numeric_range",
            observations=len(r) - 1,
            cumulative_return=None,
            max_drawdown=None,
            annualized_volatility=None,
            historical_var_95=None,
            historical_es_95=None,
        )
    peaks = np.maximum.accumulate(np.r_[1.0, indices])[1:]
    drawdowns = indices / peaks - 1
    for row, idx, dd in zip(history, indices, drawdowns, strict=True):
        row["return_index"] = float(idx)
        row["drawdown"] = float(dd)
    tail = r[1:]  # Initial funding-day execution fees remain in NAV, but not in market-risk statistics.
    enough = len(tail) >= 30
    q = float(np.quantile(tail, 0.05, method="linear")) if enough else None
    losses = tail[tail <= q] if enough else []
    return dict(
        status="ok" if enough else "insufficient_history_for_tail_risk",
        observations=len(tail),
        cumulative_return=float(indices[-1] - 1),
        max_drawdown=float(-np.min(drawdowns)),
        annualized_volatility=float(np.std(tail, ddof=1) * np.sqrt(365)) if len(tail) >= 2 else None,
        historical_var_95=max(0.0, -q) if enough else None,
        historical_es_95=max(0.0, -float(np.mean(losses))) if enough else None,
    )


def detect(history, inputs):
    alerts = []
    for row in history:
        day = row["date"]
        r = row["daily_return"]
        c = row["max_crypto_allocation"]
        turn = row["turnover"]
        if c > inputs["concentration_limit"]:
            alerts.append(
                dict(
                    date=day,
                    code="CONCENTRATION",
                    severity="review",
                    message=f"Largest crypto position is {c:.1%} of equity; review threshold {inputs['concentration_limit']:.1%}.",
                    evidence=dict(asset_id=row["largest_asset"], allocation=c),
                )
            )
        if r is not None and abs(r) > inputs["daily_change_limit"]:
            alerts.append(
                dict(
                    date=day,
                    code="DAILY_CHANGE",
                    severity="review",
                    message=f"Cash-flow-adjusted daily change is {r:.1%}; absolute threshold {inputs['daily_change_limit']:.1%}.",
                    evidence=dict(daily_return=r),
                )
            )
        if turn is not None and turn > inputs["turnover_limit"]:
            alerts.append(
                dict(
                    date=day,
                    code="TURNOVER",
                    severity="review",
                    message=f"Trade notional is {turn:.1%} of beginning capital; review threshold {inputs['turnover_limit']:.1%}.",
                    evidence=dict(turnover=turn),
                )
            )
    samples = [x for x in history[1:] if x["daily_return"] is not None and x["turnover"] is not None]
    meta = dict(
        enabled=inputs["enable_ml"],
        status="disabled",
        training_days=0,
        scoring_days=0,
        model="IsolationForest",
        scikit_learn_version=sklearn_version,
        numpy_version=np.__version__,
        random_state=42,
        contamination=0.05,
        scores=[],
        note="Scores indicate statistical novelty, not fraud probability or a price forecast.",
    )
    if not inputs["enable_ml"]:
        return alerts, meta
    if len(samples) < 40:
        meta["status"] = "insufficient_history"
        return alerts, meta
    features = np.asarray(
        [[x["daily_return"], x["turnover"], x["max_crypto_allocation"]] for x in samples], dtype=float
    )
    if np.any(np.abs(features) > 1e6):
        meta["status"] = "unavailable_numeric_range"
        return alerts, meta
    # Training uses only the earliest 30 observations; future scoring rows never enter fit.
    train = features[:30]
    test = features[30:]
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42, n_jobs=1).fit(train)
    scores = model.decision_function(test)
    median = np.median(train, axis=0)
    q = np.quantile(train, [0.25, 0.75], axis=0)
    scale = np.maximum(q[1] - q[0], 1e-6)
    labels = ["daily return", "trade turnover", "crypto concentration"]
    for row, f, score in zip(samples[30:], test, scores, strict=True):
        meta["scores"].append(dict(date=row["date"], decision_score=float(score), is_unusual=bool(score < 0)))
        if score < 0:
            j = int(np.argmax(np.abs(f - median) / scale))
            alerts.append(
                dict(
                    date=row["date"],
                    code="ML_NOVELTY",
                    severity="review",
                    message=f"Unusual relative to the first 30 observed days. Largest observed baseline deviation: {labels[j]} ({f[j]:.1%}; baseline median {median[j]:.1%}).",
                    evidence=dict(
                        decision_score=float(score),
                        observed_feature=labels[j],
                        value=float(f[j]),
                        baseline_median=float(median[j]),
                    ),
                    explanation_method="observed baseline deviation; not a causal model explanation",
                )
            )
    meta.update(
        status="scored",
        training_days=30,
        scoring_days=len(test),
        training_start=samples[0]["date"],
        training_end=samples[29]["date"],
    )
    return alerts, meta
