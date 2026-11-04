"""Price units and currencies. Every conversion for display goes through convert_price.

Prices are stored and analysed in EUR/MWh. Only the chart payload converts, so the brief's facts
stay in the unit the guards check against.
"""

from dataclasses import dataclass

UNITS = ("MWh", "kWh")
CURRENCIES = ("EUR", "DKK")
KWH_PER_MWH = 1000

# The krone is pegged to the euro (ERM II) with a central rate of 7.46038 DKK per EUR. It may drift
# a little inside its band, but the rate is set by treaty, not the market: no live rate is fetched.
DKK_PER_EUR = 7.46038


def convert_price(eur_per_mwh: float, unit: str = "MWh", rate: float = 1.0) -> float:
    """EUR/MWh to <currency>/<unit>. `rate` is currency units per EUR (1.0 for EUR)."""
    value = eur_per_mwh * rate
    if unit == "kWh":
        value /= KWH_PER_MWH
    return round(value, 6)


@dataclass(frozen=True)
class Display:
    """How prices are shown: a unit, a currency, and currency units per EUR."""

    unit: str = "MWh"
    currency: str = "EUR"
    rate: float = 1.0

    @property
    def label(self) -> str:
        return f"{self.currency}/{self.unit}"

    def convert(self, eur_per_mwh: float) -> float:
        return convert_price(eur_per_mwh, self.unit, self.rate)


EUR_PER_MWH = Display()


def make_display(unit: str, currency: str) -> Display:
    return Display(unit=unit, currency=currency, rate=DKK_PER_EUR if currency == "DKK" else 1.0)
