"""Price units and currencies. Every conversion for display goes through convert_price.

Prices are stored and analysed in EUR/MWh. Only the chart payload converts, so the brief's facts
stay in the unit the guards check against.
"""

from dataclasses import dataclass

UNITS = ("MWh", "kWh")
CURRENCIES = ("EUR", "DKK")
KWH_PER_MWH = 1000


def convert_price(eur_per_mwh: float, unit: str = "MWh", rate: float = 1.0) -> float:
    """EUR/MWh to <currency>/<unit>. `rate` is currency units per EUR (1.0 for EUR)."""
    value = eur_per_mwh * rate
    if unit == "kWh":
        value /= KWH_PER_MWH
    return round(value, 6)


@dataclass(frozen=True)
class Display:
    """How prices are shown. `fallback` means DKK was asked for but no rate was available."""

    unit: str = "MWh"
    currency: str = "EUR"
    rate: float = 1.0
    rate_date: str | None = None
    fallback: bool = False

    @property
    def label(self) -> str:
        return f"{self.currency}/{self.unit}"

    def convert(self, eur_per_mwh: float) -> float:
        return convert_price(eur_per_mwh, self.unit, self.rate)


EUR_PER_MWH = Display()
