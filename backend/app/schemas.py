"""Bounded decimal-string contracts; JSON floats never enter financial accounting."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import ConfigDict, Field, field_validator, model_validator
from .auth_schemas import Credentials, StrictModel  # noqa: F401

Amount = Annotated[
    Decimal, Field(ge=0, le=Decimal("1000000000000000"), max_digits=28, decimal_places=12, allow_inf_nan=False)
]
Asset = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class DecimalModel(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)

    @field_validator("*", mode="before")
    @classmethod
    def decimal_strings(cls, value, info):
        if info.field_name in {"quantity", "unit_price", "amount", "fee", "close"} and not isinstance(value, str):
            raise ValueError("Send money, prices and quantities as decimal strings, not JSON numbers.")
        return value


class PortfolioInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    base_currency: Literal["USD"] = "USD"


class TransactionInput(DecimalModel):
    transaction_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    date: date
    sequence: int = Field(ge=1, le=1000000, strict=True)
    kind: Literal["deposit", "withdrawal", "buy", "sell"]
    asset_id: Asset | None = None
    quantity: Amount = "0"
    unit_price: Amount = "0"
    amount: Amount = "0"
    fee: Amount = "0"

    @model_validator(mode="after")
    def shape(self):
        if self.date > date.today():
            raise ValueError("Future transactions are not allowed.")
        if self.kind in {"buy", "sell"}:
            if not self.asset_id or self.quantity <= 0 or self.unit_price <= 0 or self.amount != 0:
                raise ValueError("Trade requires asset, positive quantity/price and zero amount.")
        elif self.asset_id is not None or self.quantity != 0 or self.unit_price != 0 or self.amount <= 0:
            raise ValueError("Cash flow requires positive amount, null asset and zero quantity/price.")
        return self


class PriceInput(DecimalModel):
    date: date
    asset_id: Asset
    close: Amount

    @model_validator(mode="after")
    def valid(self):
        if self.date > date.today() or self.close <= 0:
            raise ValueError("Closing price must be positive and not future.")
        return self


class DatasetInput(StrictModel):
    source: str = Field(min_length=1, max_length=200)
    coverage_end: date
    transactions: list[TransactionInput] = Field(min_length=1, max_length=10000)
    prices: list[PriceInput] = Field(default_factory=list, max_length=40000)

    @field_validator("coverage_end")
    @classmethod
    def past(cls, v):
        if v > date.today():
            raise ValueError("Coverage end cannot be future.")
        return v


class CsvInput(StrictModel):
    transactions_csv: str = Field(min_length=1, max_length=2000000)
    prices_csv: str = Field(default="", max_length=4000000)


class AnalysisInput(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=36)
    as_of: date
    name: str = Field(default="Portfolio review", min_length=1, max_length=120)
    enable_ml: bool = True
    concentration_limit: float = Field(default=0.6, gt=0, le=1, allow_inf_nan=False)
    daily_change_limit: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    turnover_limit: float = Field(default=0.5, gt=0, le=100, allow_inf_nan=False)


class QuotesInput(StrictModel):
    asset_ids: list[Asset] = Field(min_length=1, max_length=20)

    @field_validator("asset_ids")
    @classmethod
    def unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Use distinct asset IDs.")
        return v
