"""Strict reviewed ledgers; exact daily prices are never forward-filled."""

import csv
import io
import re
from datetime import date
from .schemas import TransactionInput, PriceInput
from .ledger import Ledger

TRANSACTION_HEADER = [
    "transaction_id",
    "date",
    "sequence",
    "kind",
    "asset_id",
    "quantity",
    "unit_price",
    "amount",
    "fee",
]
PRICE_HEADER = ["date", "asset_id", "close"]


def normalize(transactions, prices, coverage_end):
    tx = [x.model_dump(mode="json") for x in transactions]
    px = [x.model_dump(mode="json") for x in prices]
    tx.sort(key=lambda x: (x["date"], x["sequence"], x["transaction_id"]))
    px.sort(key=lambda x: (x["date"], x["asset_id"]))
    if len({x["transaction_id"] for x in tx}) != len(tx):
        raise ValueError("Duplicate transaction ID.")
    if len({(x["date"], x["sequence"]) for x in tx}) != len(tx):
        raise ValueError("Sequence must be unique within each day.")
    if len({(x["date"], x["asset_id"]) for x in px}) != len(px):
        raise ValueError("Duplicate daily asset price.")
    assets = {x["asset_id"] for x in tx if x["asset_id"]}
    if len(assets) > 20:
        raise ValueError("Maximum 20 traded assets per dataset.")
    first = date.fromisoformat(tx[0]["date"])
    if first > coverage_end or (coverage_end - first).days > 730:
        raise ValueError("Coverage must contain first transaction within a maximum 731 calendar-day window.")
    ledger = Ledger()
    traded = set()
    for t in tx:
        if date.fromisoformat(t["date"]) > coverage_end:
            raise ValueError("Transaction exceeds coverage end.")
        if t["kind"] in {"deposit", "withdrawal"} and t["date"] in traded:
            raise ValueError("Cash flows must precede trades within each day.")
        if t["kind"] in {"buy", "sell"}:
            traded.add(t["date"])
        ledger.apply(t)
    for p in px:
        if date.fromisoformat(p["date"]) > coverage_end or p["date"] < str(first):
            raise ValueError("Price date is outside dataset coverage.")
        if p["asset_id"] not in assets:
            raise ValueError("Price references an asset not traded in this dataset.")
    return (
        tx,
        px,
        dict(
            transactions=len(tx),
            prices=len(px),
            assets=len(assets),
            first_date=str(first),
            warnings=[
                "USD only; fees are cash USD. Weighted-average cost is descriptive accounting, not a jurisdiction-specific tax return.",
                "Daily cash flows precede trading and are modeled at start of day. Exact prices are required for every end-of-day holding.",
                "Native-token fees, staking, swaps, derivatives, short sales and wallet transfers require upstream conversion or a future ledger extension.",
            ],
        ),
    )


def read_csv(text, header, model, limit, label):
    rows = []
    errors = []
    if not text.strip() and label == "prices":
        return rows, errors
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        if reader.fieldnames != header:
            return [], [dict(file=label, row=1, message="Use exact header: " + ",".join(header))]
        for n, raw in enumerate(reader, 2):
            if n > limit + 1:
                errors.append(dict(file=label, row=n, message=f"Maximum {limit} rows."))
                break
            try:
                if None in raw or any(v is None for v in raw.values()):
                    raise ValueError("Incorrect number of columns.")
                if label == "transactions":
                    if not re.fullmatch(r"\d{1,7}", raw["sequence"]):
                        raise ValueError("Sequence must be a whole number.")
                    raw["sequence"] = int(raw["sequence"])
                    raw["asset_id"] = raw["asset_id"] or None
                rows.append(model(**raw))
            except (ValueError, TypeError) as exc:
                errors.append(dict(file=label, row=n, message=str(exc).split("\n")[0]))
    except csv.Error as exc:
        errors.append(dict(file=label, row=0, message=str(exc)))
    return rows, errors


def preview(transactions_csv, prices_csv):
    tx, errors = read_csv(transactions_csv, TRANSACTION_HEADER, TransactionInput, 10000, "transactions")
    px, more = read_csv(prices_csv, PRICE_HEADER, PriceInput, 40000, "prices")
    errors += more
    quality = None
    if not tx:
        errors.append(dict(file="transactions", row=0, message="At least one transaction required."))
    if not errors:
        try:
            _, _, quality = normalize(tx, px, date.fromisoformat(max(x.date.isoformat() for x in tx + px)))
        except ValueError as exc:
            errors.append(dict(file="dataset", row=0, message=str(exc)))
    return dict(
        valid=not errors,
        transactions=[x.model_dump(mode="json") for x in tx],
        prices=[x.model_dump(mode="json") for x in px],
        quality=quality,
        errors=errors,
    )
