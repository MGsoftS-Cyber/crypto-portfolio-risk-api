"""Owner-scoped portfolio workflows and immutable analysis evidence."""

import csv
import io
import json
import hashlib
import math
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from .database import get_db
from .security import current_user
from .models import Portfolio, Dataset, Analysis
from .schemas import PortfolioInput, DatasetInput, CsvInput, AnalysisInput, QuotesInput
from .services import mutation
from .imports import preview, normalize
from .engine import evaluate, ENGINE_VERSION
from .market import quotes

router = APIRouter(prefix="/api/v1")
Key = Header(min_length=1, max_length=100)


def owned_portfolio(db, identifier, user):
    obj = db.scalar(select(Portfolio).where(Portfolio.id == identifier, Portfolio.user_id == user.id))
    if not obj:
        raise HTTPException(404, "Portfolio not found in your account.")
    return obj


def owned_analysis(db, identifier, user):
    obj = db.scalar(select(Analysis).join(Portfolio).where(Analysis.id == identifier, Portfolio.user_id == user.id))
    if not obj:
        raise HTTPException(404, "Analysis not found in your account.")
    return obj


def portfolio_view(x):
    return dict(id=x.id, name=x.name, base_currency=x.base_currency)


def dataset_view(x):
    return dict(
        id=x.id,
        portfolio_id=x.portfolio_id,
        source=x.source,
        coverage_end=x.coverage_end,
        transactions=x.transactions,
        prices=x.prices,
        quality=x.quality,
        created_at=x.created_at,
    )


def analysis_view(x):
    return dict(
        id=x.id,
        portfolio_id=x.portfolio_id,
        dataset_id=x.dataset_id,
        inputs=x.inputs,
        results=x.results,
        engine_version=x.engine_version,
        created_at=x.created_at,
    )


@router.get("/portfolios")
def portfolios(user=Depends(current_user), db=Depends(get_db)):
    return [portfolio_view(x) for x in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id))]


@router.post("/portfolios", status_code=201)
def create_portfolio(data: PortfolioInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)):
    def work():
        x = Portfolio(user_id=user.id, **data.model_dump())
        db.add(x)
        db.flush()
        return portfolio_view(x)

    return mutation(db, user, "portfolio", idempotency_key, data.model_dump(mode="json"), work)


@router.post("/imports/preview")
def preview_import(data: CsvInput, user=Depends(current_user)):
    return preview(data.transactions_csv, data.prices_csv)


@router.get("/portfolios/{identifier}/datasets")
def datasets(identifier: str, user=Depends(current_user), db=Depends(get_db)):
    owned_portfolio(db, identifier, user)
    return [
        dataset_view(x)
        for x in db.scalars(
            select(Dataset).where(Dataset.portfolio_id == identifier).order_by(Dataset.created_at.desc())
        )
    ]


@router.post("/portfolios/{identifier}/datasets", status_code=201)
def create_dataset(
    identifier: str, data: DatasetInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)
):
    owned_portfolio(db, identifier, user)
    try:
        tx, px, quality = normalize(data.transactions, data.prices, data.coverage_end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    fingerprint = hashlib.sha256(
        json.dumps(
            dict(transactions=tx, prices=px, source=data.source, coverage_end=str(data.coverage_end)), sort_keys=True
        ).encode()
    ).hexdigest()

    def work():
        prior = db.scalar(select(Dataset).where(Dataset.portfolio_id == identifier, Dataset.fingerprint == fingerprint))
        if prior:
            return dataset_view(prior)
        x = Dataset(
            portfolio_id=identifier,
            source=data.source,
            coverage_end=str(data.coverage_end),
            transactions=tx,
            prices=px,
            quality=quality,
            fingerprint=fingerprint,
        )
        db.add(x)
        db.flush()
        return dataset_view(x)

    return mutation(db, user, "dataset:" + identifier, idempotency_key, data.model_dump(mode="json"), work)


@router.post("/portfolios/{identifier}/analyses", status_code=201)
def analyze(
    identifier: str, data: AnalysisInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)
):
    p = owned_portfolio(db, identifier, user)
    d = db.scalar(select(Dataset).where(Dataset.id == data.dataset_id, Dataset.portfolio_id == identifier))
    if not d:
        raise HTTPException(404, "Dataset not found in this portfolio.")
    inputs = dict(
        **data.model_dump(mode="json"),
        portfolio=portfolio_view(p),
        source=d.source,
        coverage_end=d.coverage_end,
        transactions=d.transactions,
        prices=d.prices,
        quality=d.quality,
    )
    try:
        results = evaluate(inputs)
        json.dumps(results, allow_nan=False)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    def work():
        x = Analysis(
            portfolio_id=identifier, dataset_id=d.id, inputs=inputs, results=results, engine_version=ENGINE_VERSION
        )
        db.add(x)
        db.flush()
        return analysis_view(x)

    return mutation(db, user, "analysis:" + identifier, idempotency_key, data.model_dump(mode="json"), work)


@router.get("/analyses")
def analyses(user=Depends(current_user), db=Depends(get_db)):
    return [
        analysis_view(x)
        for x in db.scalars(
            select(Analysis)
            .join(Portfolio)
            .where(Portfolio.user_id == user.id)
            .order_by(Analysis.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/analyses/{identifier}")
def get_analysis(identifier: str, user=Depends(current_user), db=Depends(get_db)):
    return analysis_view(owned_analysis(db, identifier, user))


@router.get("/analyses/{identifier}/report")
def report(identifier: str, format: str = "json", user=Depends(current_user), db=Depends(get_db)):
    x = owned_analysis(db, identifier, user)
    if format == "json":
        text, media = json.dumps(analysis_view(x), indent=2), "application/json"
    elif format in {"holdings", "history", "trades", "alerts"}:
        keys = {
            "holdings": [
                "asset_id",
                "quantity",
                "cost_basis",
                "average_cost",
                "price",
                "market_value",
                "allocation",
                "realized_pnl",
                "unrealized_pnl",
                "trade_fees",
            ],
            "history": [
                "date",
                "cash",
                "equity",
                "net_contributions",
                "external_flow",
                "total_fees",
                "realized_pnl",
                "unrealized_pnl",
                "total_pnl",
                "daily_return",
                "return_index",
                "drawdown",
                "turnover",
            ],
            "trades": [
                "transaction_id",
                "date",
                "sequence",
                "kind",
                "asset_id",
                "quantity",
                "unit_price",
                "fee",
                "notional",
            ],
            "alerts": ["date", "code", "severity", "message"],
        }[format]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(keys)
        for row in x.results[format]:
            values = []
            for k in keys:
                v = row[k]
                if (
                    isinstance(v, str)
                    and k
                    not in {
                        "quantity",
                        "cost_basis",
                        "average_cost",
                        "price",
                        "market_value",
                        "realized_pnl",
                        "unrealized_pnl",
                        "trade_fees",
                        "cash",
                        "equity",
                        "net_contributions",
                        "external_flow",
                        "total_fees",
                        "total_pnl",
                        "unit_price",
                        "fee",
                        "notional",
                    }
                    and v.lstrip().startswith(("=", "+", "-", "@"))
                ):
                    v = "'" + v
                values.append(v)
            writer.writerow(values)
        text, media = output.getvalue(), "text/csv"
    else:
        raise HTTPException(422, "Use json, holdings, history, trades or alerts format.")
    ext = "json" if format == "json" else "csv"
    return Response(
        text, media_type=media, headers={"Content-Disposition": f'attachment; filename="crypto-{format}-{x.id}.{ext}"'}
    )


@router.post("/market/quotes")
def current_quotes(data: QuotesInput, user=Depends(current_user)):
    return quotes(data.asset_ids)


@router.post("/demo", status_code=201)
def demo(idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)):
    def work():
        if db.scalar(select(Portfolio).where(Portfolio.user_id == user.id)):
            raise HTTPException(409, "Demo requires an empty portfolio catalog.")
        p = Portfolio(user_id=user.id, name="Demo Crypto Portfolio", base_currency="USD")
        db.add(p)
        db.flush()
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=59)
        tx = [
            dict(transaction_id="D1", date=str(start), sequence=1, kind="deposit", amount="15000", fee="5"),
            dict(
                transaction_id="B1",
                date=str(start),
                sequence=2,
                kind="buy",
                asset_id="bitcoin",
                quantity="0.1",
                unit_price="50000",
                fee="10",
            ),
            dict(
                transaction_id="B2",
                date=str(start),
                sequence=3,
                kind="buy",
                asset_id="ethereum",
                quantity="2",
                unit_price="2500",
                fee="8",
            ),
            dict(
                transaction_id="S1",
                date=str(start + timedelta(days=20)),
                sequence=1,
                kind="sell",
                asset_id="ethereum",
                quantity="0.5",
                unit_price="2600",
                fee="3",
            ),
        ]
        prices = []
        for i in range(60):
            day = str(start + timedelta(days=i))
            shock = 0.65 if i >= 48 else 1
            prices.extend(
                [
                    dict(
                        date=day,
                        asset_id="bitcoin",
                        close=f"{(50000 * (1 + 0.001 * i + 0.025 * math.sin(i * 0.6)) * shock):.8f}",
                    ),
                    dict(
                        date=day,
                        asset_id="ethereum",
                        close=f"{(2500 * (1 + 0.0015 * i + 0.035 * math.cos(i * 0.4)) * shock):.8f}",
                    ),
                ]
            )
        data = DatasetInput(source="Synthetic daily demonstration", coverage_end=end, transactions=tx, prices=prices)
        transactions, px, q = normalize(data.transactions, data.prices, end)
        d = Dataset(
            portfolio_id=p.id,
            source=data.source,
            coverage_end=str(end),
            transactions=transactions,
            prices=px,
            quality=q,
            fingerprint=hashlib.sha256(json.dumps(dict(transactions=transactions, prices=px)).encode()).hexdigest(),
        )
        db.add(d)
        db.flush()
        return dict(
            portfolio_id=p.id,
            dataset_id=d.id,
            as_of=str(end),
            message="Synthetic prices and transactions; no exchange or wallet connected.",
        )

    return mutation(db, user, "demo", idempotency_key, {}, work)
