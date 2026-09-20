"""Mock-broker paper-trading demo -- NO real API, NO real credentials, NO
real money, NO TradingView. This exists to show the full pipeline running
end to end (broker adapter -> PointInTimeStore -> strategy -> paper
trading) when you don't have real broker credentials yet, as a companion
to scripts/vendor_smoke_test.py (which does the same shape of check but
against a REAL authenticated account).

What's real here: the ZerodhaKiteDataSource adapter code, PointInTimeStore,
TrendStrategy, and PaperTrader are the EXACT SAME production classes used
everywhere else in this system -- nothing is special-cased for this demo.

What's fake here: MockKiteClient. It implements the same
``historical_data(instrument_token, from_date, to_date, interval)``
signature kiteconnect.KiteConnect exposes, but returns fabricated,
deterministic OHLCV data instead of calling a real Zerodha server. No
network call, no API key, no account. The "paper money" is
SystemConfig.backtest.initial_capital -- a plain number the PaperTrader
tracks in memory; nothing is transferred anywhere, ever.

Do not read the printed portfolio values as a claim about real NSE stocks
or real Zerodha execution -- see Docs/Implementation_Spec.md S6.1's
running theme: synthetic/mock data is for proving the CODE works, never
for concluding anything about real markets.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from trading_system.brokers.base import InstrumentMapping
from trading_system.brokers.zerodha_kite import ZerodhaKiteDataSource
from trading_system.config.schema import SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.live.paper.paper_trader import PaperTrader
from trading_system.strategies.trend import TrendStrategy
from trading_system.util import stable_hash

_TRADING_DAYS_PER_YEAR = 252


class MockKiteClient:
    """Fabricates OHLCV data instead of calling Zerodha's servers.

    Matches the KiteConnectLike protocol in brokers/zerodha_kite.py exactly,
    so ZerodhaKiteDataSource cannot tell the difference between this and a
    real, authenticated kiteconnect.KiteConnect instance -- which is the
    whole point: it proves the ADAPTER's own logic (chunking date ranges,
    parsing the response shape, caching) is correct, independent of whether
    a real account is available.
    """

    def __init__(self, universe_start: date = date(2020, 1, 1), universe_end: date = date(2023, 12, 31)):
        self._start = universe_start
        self._end = universe_end
        self._cache: dict[int, pd.DataFrame] = {}
        self.call_count = 0  # exposed so the demo can show chunking happened

    def _full_series(self, instrument_token: int) -> pd.DataFrame:
        if instrument_token in self._cache:
            return self._cache[instrument_token]
        dates = pd.bdate_range(self._start, self._end)
        n = len(dates)
        rng = np.random.default_rng(stable_hash(str(instrument_token)) % (2**32))

        daily_vol = 0.18 / np.sqrt(_TRADING_DAYS_PER_YEAR)
        regime_length = rng.integers(150, 350)
        drift = np.zeros(n)
        pos = 0
        while pos < n:
            length = min(regime_length, n - pos)
            magnitude = rng.uniform(0.0, 0.08) / _TRADING_DAYS_PER_YEAR
            sign = rng.choice([-1.0, 1.0])
            drift[pos : pos + length] = sign * magnitude
            pos += length
            regime_length = rng.integers(150, 350)
        noise = rng.normal(0.0, daily_vol, n)
        close = 100.0 * np.exp(np.cumsum(drift + noise))

        intraday = np.abs(rng.normal(0.0, daily_vol * 0.3, n))
        high = close * (1 + intraday)
        low = close * (1 - intraday)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        volume = rng.uniform(1e5, 1e6, n)

        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )
        self._cache[instrument_token] = df
        return df

    def historical_data(self, instrument_token, from_date, to_date, interval, continuous=False, oi=False):
        self.call_count += 1
        full = self._full_series(instrument_token)
        from_ts = pd.Timestamp(str(from_date).split(" ")[0])
        to_ts = pd.Timestamp(str(to_date).split(" ")[0])
        sliced = full.loc[(full.index >= from_ts) & (full.index <= to_ts)]
        return [
            {
                "date": idx.strftime("%Y-%m-%dT00:00:00+0530"),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for idx, row in sliced.iterrows()
        ]


# Illustrative, NOT real Kite instrument_tokens -- picking arbitrary
# distinct integers is all MockKiteClient needs to key its fabricated series.
#
# asset_class is set to "equity_index" (one of the four buckets
# config/schema.py:CostConfig actually has cost rates for) rather than a
# made-up label -- this demo drives TrendStrategy/SystemConfig, the
# GLOBAL-futures system, so it must use that system's own asset-class
# vocabulary. Using an invented label here was a real bug caught by
# actually running this script: PaperTrader raised KeyError from
# CostConfig.cost_bps() the first time it tried to charge a trade, since
# nothing in the cost table knew what "nse_equity_mock" was.
_MOCK_UNIVERSE = [
    InstrumentMapping(symbol="RELIANCE", asset_class="equity_index", vendor_id="1000001"),
    InstrumentMapping(symbol="TCS", asset_class="equity_index", vendor_id="1000002"),
    InstrumentMapping(symbol="INFY", asset_class="equity_index", vendor_id="1000003"),
    InstrumentMapping(symbol="HDFCBANK", asset_class="equity_index", vendor_id="1000004"),
    InstrumentMapping(symbol="ICICIBANK", asset_class="equity_index", vendor_id="1000005"),
]


def main() -> None:
    print("=" * 72)
    print("MOCK BROKER PAPER-TRADING DEMO")
    print("No real API call. No real credentials. No real money. No TradingView.")
    print("=" * 72)

    mock_client = MockKiteClient()
    source = ZerodhaKiteDataSource(
        mock_client,
        _MOCK_UNIVERSE,
        start_date=date(2020, 1, 1),
        end_date=date(2023, 12, 31),
        max_days_per_chunk=365,  # forces multiple chunked calls -- exercises real chunking logic
    )

    print("\n--- Step 1: adapter fetch (mirrors scripts/vendor_smoke_test.py) ---")
    for mapping in _MOCK_UNIVERSE:
        df = source.get_prices(mapping.symbol)
        print(
            f"  {mapping.symbol:10s}  {len(df):4d} rows  "
            f"{df.index.min().date()} -> {df.index.max().date()}  "
            f"last close = {df['close'].iloc[-1]:9.2f}"
        )
    print(f"  (fabricated data server called {mock_client.call_count} times "
          f"across {len(_MOCK_UNIVERSE)} symbols -- confirms date-range chunking ran)")

    print("\n--- Step 2: point-in-time store + leakage-safety check ---")
    store = PointInTimeStore(source)
    calendar = store.trading_calendar()
    print(f"  Trading calendar: {len(calendar)} sessions, "
          f"{calendar[0].date()} -> {calendar[-1].date()}")

    print("\n--- Step 3: paper trading replay (frozen trend strategy, paper money only) ---")
    config = SystemConfig(mode="paper")
    strategy = TrendStrategy(config.trend)
    trader = PaperTrader(config, store, strategy)

    replay_dates = list(calendar[-60:])
    records = trader.run_replay(replay_dates)

    starting_capital = config.backtest.initial_capital
    print(f"  Starting paper capital: {starting_capital:,.2f}")
    print(f"  Replayed {len(records)} sessions\n")

    print(f"  {'date':12s} {'portfolio_value':>18s}  intended_trade")
    for r in records[-10:]:
        trade_str = ", ".join(f"{s}:{d:+.3f}" for s, d in r.intended_trade.items()) or "(no rebalance)"
        print(f"  {str(r.decision_date.date()):12s} {r.portfolio_value:18,.2f}  {trade_str}")

    final_value = records[-1].portfolio_value if records else starting_capital
    pnl = final_value - starting_capital
    print(f"\n  Final paper portfolio value: {final_value:,.2f}  "
          f"(paper P&L: {pnl:+,.2f}, {pnl / starting_capital:+.2%})")

    print("\n" + "=" * 72)
    print("Reminder: MOCK data, MOCK broker, PAPER money only.")
    print("This proves the adapter + paper-trading PIPELINE works end to end --")
    print("it is NOT evidence about real Zerodha execution or real NSE performance.")
    print("For a real (if unverified-live) check, use scripts/vendor_smoke_test.py")
    print("with your own Zerodha/Angel One/INDmoney credentials.")
    print("=" * 72)


if __name__ == "__main__":
    main()
