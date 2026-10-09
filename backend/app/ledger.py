"""Decimal ledger: no borrowed coins, no negative cash, no tax-jurisdiction claim."""

from collections import defaultdict
from decimal import Decimal, localcontext

ZERO = Decimal("0")


def dec(value):
    return Decimal(str(value))


def text(value):
    return format(value, "f")


class Ledger:
    def __init__(self):
        self.cash = ZERO
        self.net_contributions = ZERO
        self.fees = ZERO
        self.cash_fees = ZERO
        self.realized = ZERO
        self.positions = defaultdict(lambda: dict(quantity=ZERO, cost=ZERO, realized=ZERO, fees=ZERO))

    def apply(self, t):
        """Mutate only this evaluation's in-memory ledger, under a high precision context."""
        with localcontext() as context:
            context.prec = 60
            fee = dec(t["fee"])
            quantity = dec(t["quantity"])
            price = dec(t["unit_price"])
            amount = dec(t["amount"])
            notional = quantity * price
            if t["kind"] == "deposit":
                if fee > amount:
                    raise ValueError("Deposit fee exceeds amount: " + t["transaction_id"])
                self.cash += amount - fee
                self.net_contributions += amount
                self.cash_fees += fee
            elif t["kind"] == "withdrawal":
                if amount + fee > self.cash:
                    raise ValueError("Insufficient cash for withdrawal: " + t["transaction_id"])
                self.cash -= amount + fee
                self.net_contributions -= amount
                self.cash_fees += fee
            elif t["kind"] == "buy":
                if notional + fee > self.cash:
                    raise ValueError("Insufficient cash for purchase: " + t["transaction_id"])
                p = self.positions[t["asset_id"]]
                p["quantity"] += quantity
                p["cost"] += notional + fee
                p["fees"] += fee
                self.cash -= notional + fee
            else:
                p = self.positions[t["asset_id"]]
                if quantity > p["quantity"]:
                    raise ValueError("Sell exceeds holdings: " + t["transaction_id"])
                if fee > notional:
                    raise ValueError("Sell fee exceeds proceeds: " + t["transaction_id"])
                cost = p["cost"] if quantity == p["quantity"] else p["cost"] * quantity / p["quantity"]
                gain = notional - fee - cost
                p["quantity"] -= quantity
                p["cost"] -= cost
                p["realized"] += gain
                p["fees"] += fee
                self.realized += gain
                self.cash += notional - fee
            self.fees += fee
            return notional

    def value(self, day, prices):
        with localcontext() as context:
            context.prec = 60
            holdings = []
            equity = self.cash
            unrealized = ZERO
            for aid, p in sorted(self.positions.items()):
                if p["quantity"] == 0:
                    continue
                price = prices.get((day, aid))
                if price is None:
                    raise ValueError(f"Missing exact daily price for held asset {aid} on {day}.")
                price = dec(price)
                value = p["quantity"] * price
                gain = value - p["cost"]
                equity += value
                unrealized += gain
                holdings.append(
                    dict(
                        asset_id=aid,
                        quantity=text(p["quantity"]),
                        cost_basis=text(p["cost"]),
                        average_cost=text(p["cost"] / p["quantity"]),
                        price=text(price),
                        market_value=text(value),
                        unrealized_pnl=text(gain),
                        realized_pnl=text(p["realized"]),
                        trade_fees=text(p["fees"]),
                    )
                )
            for h in holdings:
                h["allocation"] = float(dec(h["market_value"]) / equity) if equity else 0.0
            total = equity - self.net_contributions
            if abs(total - (self.realized + unrealized - self.cash_fees)) > Decimal("0.000000000001"):
                raise ValueError("Ledger reconciliation failed.")
            return dict(
                cash=text(self.cash),
                equity=text(equity),
                net_contributions=text(self.net_contributions),
                total_fees=text(self.fees),
                nontrade_fees=text(self.cash_fees),
                realized_pnl=text(self.realized),
                unrealized_pnl=text(unrealized),
                total_pnl=text(total),
                holdings=holdings,
                cash_allocation=float(self.cash / equity) if equity else None,
            )
