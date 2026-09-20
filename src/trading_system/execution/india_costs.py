"""Itemized India transaction-cost model
(Docs/India_Implementation_Spec.md S1.4):

    C_trade = C_brokerage + C_exchange + C_regulatory + C_STT/CTT + C_stamp
              + C_GST + C_spread + C_impact + C_roll

Regulatory/tax rates below are transcribed directly from the research
document, versioned with effective_from/effective_to so a future rate
change doesn't require touching strategy code. Two things are explicitly
NOT precisely sourced (flagged, not silently guessed):

- Brokerage, exchange transaction charges, and spread/impact are
  placeholder bps estimates -- the research explicitly says these "must be
  loaded from the actual broker/exchange configuration applicable to the
  test date," which this system does not have. Never report these as real
  broker figures.
- A commodities-transaction-tax (CTT) rate for MCX futures is NOT given
  anywhere in the source research document (only equity/option STT figures
  are listed) -- defaults to 0.0 here, which understates true MCX cost.
  This must be corrected with a real CTT figure before any MCX result is
  taken seriously (see Docs/India_Implementation_Spec.md S5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

CostScenario = str  # "base" | "stress_2x" | "stress_3x"


@dataclass(frozen=True)
class IndiaCostRates:
    effective_from: date
    effective_to: date | None
    # -- Regulatory / tax, transcribed from the research doc (S1.4) --
    delivery_equity_stt_buy_bps: float = 10.0  # 0.1%
    delivery_equity_stt_sell_bps: float = 10.0  # 0.1%
    equity_futures_stt_sell_bps: float = 5.0  # 0.05%, seller only
    sebi_turnover_fee_bps: float = 0.001  # 0.0001%, both sides
    equity_futures_stamp_duty_buy_bps: float = 0.2  # 0.002%, buyer only
    commodity_futures_stamp_duty_buy_bps: float = 0.2  # 0.002%, buyer only
    gst_rate_on_brokerage: float = 0.18  # 18%
    # NOT given in the source document -- see module docstring.
    commodity_ctt_bps: float = 0.0
    # -- Estimated, NOT sourced from a real broker (see module docstring) --
    brokerage_bps_estimate: float = 1.0
    exchange_spread_impact_bps_estimate: float = 1.0


CURRENT_INDIA_COST_RATES = IndiaCostRates(effective_from=date(2026, 4, 1), effective_to=None)


@dataclass(frozen=True)
class IndiaCostConfig:
    rates: IndiaCostRates = field(default_factory=lambda: CURRENT_INDIA_COST_RATES)
    scenario: CostScenario = "base"

    def scenario_multiplier(self) -> float:
        # Matches the research's framing of "2x/3x VARIABLE execution
        # costs" as a stress test -- applied only to the estimated
        # brokerage/spread/impact components, not to statutory tax rates
        # (which don't change under a cost-stress scenario).
        return {"base": 1.0, "stress_2x": 2.0, "stress_3x": 3.0}[self.scenario]


def india_trade_cost(
    notional_traded: float,
    asset_class: str,
    is_buy: bool,
    config: IndiaCostConfig,
) -> float:
    """asset_class: "nse_equity" (cash delivery) or "mcx_commodity" (futures)."""
    r = config.rates
    notional = abs(notional_traded)
    scenario_mult = config.scenario_multiplier()

    regulatory_bps = 0.0
    stamp_bps = 0.0

    if asset_class == "nse_equity":
        regulatory_bps += (
            r.delivery_equity_stt_buy_bps if is_buy else r.delivery_equity_stt_sell_bps
        )
        regulatory_bps += r.sebi_turnover_fee_bps
        if is_buy:
            stamp_bps += r.equity_futures_stamp_duty_buy_bps
    elif asset_class == "mcx_commodity":
        regulatory_bps += r.sebi_turnover_fee_bps + r.commodity_ctt_bps
        if is_buy:
            stamp_bps += r.commodity_futures_stamp_duty_buy_bps
    else:
        raise ValueError(f"india_trade_cost: unsupported asset_class {asset_class!r}")

    brokerage_bps = r.brokerage_bps_estimate * scenario_mult
    spread_impact_bps = r.exchange_spread_impact_bps_estimate * scenario_mult
    gst_bps = brokerage_bps * r.gst_rate_on_brokerage

    total_bps = regulatory_bps + stamp_bps + brokerage_bps + spread_impact_bps + gst_bps
    return notional * total_bps / 10_000.0
