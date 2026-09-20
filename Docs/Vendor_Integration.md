# Vendor / Broker Integration

## The contract that makes "any vendor" true

Everything downstream of data — features, the trend/carry strategies,
position sizing, the backtest engine, the paper trader — only ever talks to
a `DataSource`:

```python
class DataSource(Protocol):
    def get_universe(self) -> list[ContractMeta]: ...
    def get_prices(self, symbol: str) -> pd.DataFrame:  # OHLCV, DatetimeIndex, sorted, no dupes
        ...
```

(`src/trading_system/data/interfaces.py`.) That's the entire integration
surface. Any object with those two methods can be handed to
`PointInTimeStore(source)` and the rest of the system works unmodified —
this is deliberate, not incidental: it's what makes "any vendor" actually
true rather than a slogan.

## Ready-to-use adapters (`src/trading_system/brokers/`)

| Vendor | Module | Status |
|---|---|---|
| Zerodha (Kite Connect) | `zerodha_kite.py` | Built against a **live-verified** instrument schema (confirmed via this project's connected Kite session on 2026-09-20 — see commit history). `historical_data()` parsing itself is unit-tested against a mock only; the connected session wasn't logged in, so no authenticated historical-data call was actually made. Run `scripts/vendor_smoke_test.py` with your own session before relying on it. |
| Angel One (SmartAPI) | `angel_one.py` | Built against SmartAPI's publicly documented `getCandleData()` contract (`smartapi-python` package). Not execution-tested against a live account — no Angel One session was available in this environment. |
| INDmoney (INDstocks API) | `indmoney.py` | Built against the publicly documented INDstocks REST API (`api-docs.indstocks.com`). **One field is an unconfirmed guess**: the daily-interval string is assumed to be `"1day"` — the docs example only showed `"1minute"`. Fix this in one place (`INDmoneyDataSource`'s `interval` parameter) if your account returns an error. Not execution-tested against a live account. |
| Any vendor with a file export | `local_csv.py` | Generic. Works with literally anything that can export historical OHLCV to CSV or Parquet — Interactive Brokers, Norgate, Databento, TrueData, Global Datafeeds, a broker's own "export" button, etc. No vendor-specific code at all. |

**Important, read before assuming this "just works":** none of the three
broker adapters have been run against a live, authenticated account in this
development environment (Kite's connector here isn't logged in; there was
no Angel One or INDmoney session available at all). They are written
carefully against each vendor's own public documentation and are
unit-tested against mocked clients matching that documented schema, but a
documented API and a live account can still disagree in practice (a renamed
field, an undocumented rate limit, a wrong interval string). **Run
`scripts/vendor_smoke_test.py` with your own credentials before trusting an
adapter for real research or paper trading.**

## Credential policy

No adapter here accepts, stores, or transmits an API key, password, or TOTP
secret. Each adapter's constructor takes an **already-authenticated client
object** — a `kiteconnect.KiteConnect`, a `SmartApi.SmartConnect`, or a
`requests`-like HTTP client with your INDstocks token in hand — that you
build yourself, in your own script, using that vendor's official login
flow. This project never sees your credentials. `scripts/vendor_smoke_test.py`
shows the exact shape of that setup step (commented out) for each vendor.

## Instrument mapping

There is no shared instrument-ID standard across these brokers:

- Kite Connect identifies instruments by a numeric `instrument_token`.
- Angel One SmartAPI needs an `exchange` + a numeric `symboltoken`.
- INDstocks uses an `"EXCHANGE_code"` scrip code (e.g. `"NSE_11536"`).

You build this mapping once per vendor via `InstrumentMapping` (`brokers/base.py`):

```python
from trading_system.brokers.base import InstrumentMapping

mapping = [
    InstrumentMapping(symbol="RELIANCE", asset_class="equity_index", vendor_id="738561"),           # Kite
    InstrumentMapping(symbol="RELIANCE", asset_class="equity_index", vendor_id="2885", exchange="NSE"),  # Angel One
    InstrumentMapping(symbol="RELIANCE", asset_class="equity_index", vendor_id="NSE_2885"),          # INDstocks
]
```

`symbol` is *your* canonical name — the one everything else in this system
(features, strategies, config) uses. Look up each vendor's own instrument
list (Kite: `search_instruments`, confirmed live and working without even
logging in; Angel One: their published scrip master; INDstocks: their
`/market/instruments` endpoint) to fill in `vendor_id`/`exchange` once,
and everything after that is vendor-independent.

## Wiring a real vendor into the system

Nothing in `SystemConfig` holds a live client object (config must stay
serializable/reproducible per Prompt.md S28) — you construct the adapter
explicitly in your own script, exactly the way `cli/run_backtest.py`
constructs `SyntheticFuturesDataSource`:

```python
from trading_system.config.defaults import default_config
from trading_system.data.pit_store import PointInTimeStore
from trading_system.brokers.zerodha_kite import ZerodhaKiteDataSource

config = default_config()
source = ZerodhaKiteDataSource(kite, mapping, config.data.start_date, config.data.end_date, cache_dir="cache/kite")
store = PointInTimeStore(source)
# everything from here (strategy, sizing, BacktestEngine, PaperTrader) is unchanged
```

## Adding a vendor not listed here ("small modifications")

Implement a class with the two `DataSource` methods. That's the whole
requirement:

```python
class MyVendorDataSource:
    def get_universe(self) -> list[ContractMeta]:
        ...  # return your instrument list

    def get_prices(self, symbol: str) -> pd.DataFrame:
        ...  # return a DataFrame: DatetimeIndex, columns open/high/low/close/volume,
             # sorted ascending, no duplicate timestamps
             # (trading_system.brokers.base.normalize_ohlcv does this for you)
```

Use `zerodha_kite.py` or `angel_one.py` as a template for an API-based
vendor (they share `brokers/base.py`'s chunking and caching helpers), or
just use `local_csv.py` directly if your vendor can export to a file —
that requires no new code at all.

## Scope note: this is the India-specific branch, not the global-futures baseline

Zerodha, Angel One, and INDmoney are Indian brokers covering NSE/BSE
(equities, index/stock F&O), MCX (commodities), and CDS (currency
derivatives). `Docs/Implementation_Spec.md` §6.1 picked **global liquid
futures** as the primary research universe, per Research.md's strongest
evidence base. Using one of these three vendors does not silently
substitute for that decision — it concretely activates **Research.md's
"India-specific branch,"** which the research explicitly requires be
treated as *a separate experiment* with its own tax/cost model (NSE STT,
current as of the integration date — never hardcoded, see
`Implementation_Spec.md`'s audit item on this), its own instrument
universe, and its own validation run, not a drop-in replacement for the
global-futures backtest already validated (on synthetic data) in Milestones
1–2.

Concretely, across Zerodha/Angel One/INDmoney you can reasonably fill:

- **Equity index bucket**: NSE index futures (Nifty, Bank Nifty, etc.) — confirmed available via Kite's instrument search (`NFO` segment).
- **Commodities bucket**: MCX futures (gold, crude, silver, etc.) — confirmed available via Kite's instrument search (`MCX` segment).
- **FX bucket**: currency derivatives on NSE's CDS segment — confirmed available via Kite's instrument search.
- **Rates/bonds bucket**: NSE lists GOI bond futures, but retail liquidity there is documented as thin — this bucket is **not reliably fillable** through these retail brokers alone. Report this gap explicitly in any India-branch result rather than silently dropping the bucket or substituting something else without saying so.

Nothing about the strategy, sizing, or backtest engine code changes for the
India branch — only the `DataConfig` universe and the `CostConfig` (STT,
brokerage, F&O-specific fees) differ. Keep the two branches' results and
reports clearly separated when you run this.
