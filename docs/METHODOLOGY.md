# Accounting and risk methodology

## Cost basis and fees

Each asset has quantity, cost pool, realized P/L and trade fees. Buy q at p with USD fee f: cash -= q*p+f; quantity +=q; cost +=q*p+f. Weighted average cost is cost/quantity. Sell q at p with fee f: release cost*q/quantity before the sale; cash +=q*p-f; realized +=q*p-f-released cost. A full sale releases the entire remaining pool to prevent residual rounding dust. Partial pools use Decimal arithmetic at 60-digit precision. This is descriptive weighted-average accounting, not jurisdiction-specific tax cost basis.

Deposit amount A and cash fee f: cash +=A-f, net_contributions +=A, nontrade_fees +=f. Withdrawal A with f: cash -=A+f, net_contributions -=A, nontrade_fees +=f. Negative cash is rejected on each event. All fees are paid in USD; native-token fees require a richer upstream conversion model, not simple relabeling.

At an exact daily close: market value=quantity*price; unrealized=value-cost; equity=cash+sum values. Total P/L=equity-net contributions. Reconcile to realized+unrealized-nontrade_fees within 10^-12 USD. Purchase fees are already in cost, and sale fees in proceeds; do not subtract all fees again. Allocation is value/equity, including cash as a separate weight. Closed assets retain realized P/L and trade fee records.

Worked fixture: deposit1000 fee2; buy2 at100 fee4; sell1 at150 fee3; final close140. Cash941, remaining cost102, market value140, equity1081, realized45, unrealized38, nontrade fees2, total P/L81, total fees9. 45+38-2=81.

## Return convention

The ledger uses dates and sequences, not intraday timestamps. External flows precede all trades on a day and are assumed at the UTC day's start. Day capital = previous closing equity + deposit amounts - withdrawal amounts. Daily return = today's closing equity/day capital -1. Flow fees are expenses and do not reduce the external-flow amount. This is an explicit daily approximation for this contract; true intraday returns require event-time valuations. It is not a claim of GIPS compliance.

Return index starts at1 and chains (1+r). Daily drawdown =index/running peak-1, with initial reference1; maximum drawdown is the positive magnitude of the minimum. Raw equity is never used for risk drawdown because deposits distort it. First funding-day execution expenses enter the index but the initial day is excluded from volatility and tail statistics. Zero day capital gives an undefined return. Any such gap disables full-period return/drawdown statistics rather than joining unlike funding periods silently.

Annualized historical volatility uses sample daily standard deviation (ddof=1)*sqrt365, available with at least two post-initial daily returns. One-day historical95% VaR uses the negative5th percentile of returns (NumPy linear quantile), floored at0. Expected shortfall uses the negative mean of returns at/below that quantile, also floored at0. VaR/ES require at least30 post-initial observations. These are historical statistics, not loss guarantees, forecasts or stop-loss advice. Extreme absolute daily returns above10^6 or nonfinite compounded indices disable risk statistics; decimal accounting remains available.

## Rules and machine learning

CONCENTRATION: maximum crypto position weight >configured limit (default60%). DAILY_CHANGE: absolute cash-flow-adjusted return >limit (default10%). TURNOVER: gross buy+sell notional/day capital >limit (default50%). Thresholds are user choices and flags request review. No severity code implies a personalized recommendation.

Optional IsolationForest uses [daily return, turnover, largest crypto allocation]. Skip the initial funding day and undefined rows. At least40 usable observations are required. Train only the earliest30; score later observations. Fixed random_state42,100 estimators,contamination0.05,n_jobs1. Negative decision_function means unusual relative to the fitted baseline. The score is not fraud probability. Explain the largest observed feature deviation from the training median, scaled by training IQR (floor10^-6); this is supporting observation, not a causal attribution to the forest. Disable ML with enable_ml=false. No paid LLM or GPU is needed. Identical pinned environments/inputs produce deterministic results; engine/model versions are preserved with reports.

References: scikit-learn IsolationForest https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html ; cash-flow methodology background https://www.gipsstandards.org/wp-content/uploads/2021/03/calculation_methodology_gs_2011.pdf . The accounting method, minimum samples, thresholds, precision and daily timing convention are explicit project choices.
