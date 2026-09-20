# India NSE + MCX Implementation Specification & Audit

Source: `India NSE + MCX Quantitative Trading Research_ Evidence Review, Candidate Architecture
and Implementation.pdf` (user-supplied, 29 pages, ChatGPT-authored desk research). Original PDF
is not stored in the repo (kept outside git per this project's existing pattern of not
committing the research source documents — see `Docs/Implementation_Spec.md`'s note that
`Prompt.md`/`Research.md` were removed at the user's request); this file retains a full
structured extraction so nothing downstream depends on the PDF still existing on disk.

This document does the same job for the India research that `Implementation_Spec.md` did for
the global-futures research: extract, audit, and reconcile — **plus** a dedicated blending
section, since the user asked for one combined portfolio (NSE+MCX and the existing
global-futures system in a single `PointInTimeStore`/backtest), and the two research documents
specify genuinely different parameters for superficially similar ideas. Per the user's explicit
instruction, this task proceeds autonomously: anything requiring a decision I can't make from
the documents themselves is flagged below and in code comments, not asked about mid-build.

---

## 1. Extracted Specification

### 1.1 Two primary hypotheses (build first, per the research's own final decision)

**`EQ_MOM_01` — NSE cross-sectional equity momentum**

| Field | Value |
|---|---|
| Universe | Point-in-time Nifty 200 (effective-dated membership, never today's constituents projected backward) |
| Frequency | Daily data, **monthly** decision |
| Minimum history | 252 trading days |
| Features | `return_6m = close_t/close_t-126 - 1`; `return_12m = close_t/close_t-252 - 1`; `vol_252 = std(log daily returns, 252) * sqrt(252)`; `mom6_adj = return_6m/vol_252`; `mom12_adj = return_12m/vol_252`; `score = 0.5*zscore_cross_section(mom6_adj) + 0.5*zscore_cross_section(mom12_adj)` |
| Selection | Baseline: top 30 by score. Challenger (test separately, not silently substituted): retain incumbents until rank falls below 45, admit highest-ranked replacements ("hysteresis buffer") |
| Weighting | Inverse volatility among selected names |
| Constraints | Single stock ≤ 5% sleeve NAV; sector ≤ 25% sleeve NAV; `proposed_trade / median(daily_traded_value, 60d) ≤ 5%` (research policy assumption — also test 1% and 2.5%) |
| Execution | Signal timestamp = after official close on rebalance day; execution ≥ next trading session |
| Required ablations (each a separate logged trial) | 6m-only, 12m-only, unadjusted momentum, equal weights, inverse-vol weights, top 20/30/40, monthly vs. quarterly/semi-annual rebalance, with/without rank buffer |
| Mandatory baseline to beat | Nifty 200 cap-weighted benchmark; equal-weight liquid universe; simple 6-month momentum; simple 12-month momentum |

**`MCX_TREND_01` — MCX diversified time-series trend**

| Field | Value |
|---|---|
| Universe | GOLD, SILVER, CRUDEOIL, NATURALGAS, COPPER, ALUMINIUM, ZINC (exact initial list; nickel/agri excluded from generation 1 unless a separate liquidity/data audit approves them) |
| Frequency | Daily (signal **and** decision — no separate monthly/weekly step stated, unlike EQ_MOM_01) |
| Signal price | A return-linked active-contract index (`signal_index`) — **not** the tradable contract; P&L is always from the actual dated contract |
| Lookbacks | **[21, 63, 126, 252]** — four horizons, not three. `signal_L = sign(log(index_t/index_t-L))`; `trend_score = mean(signal_L)` |
| Volatility baseline | **60 trading-day realised volatility** (simple rolling std, annualized) — EWMA is an explicit challenger to test, not a silent substitute |
| Sizing | `raw_risk_weight = trend_score / volatility`; cross-asset normalization: `raw / sum(abs(raw))` (single MCX bucket — no further asset-class split within MCX in generation 1) |
| Required robustness variants | 63/126/252-only, 21/63/126-only, and a simple 200-day-sign rule, as robustness checks — not hundreds of optimization trials |
| Roll rule | Use near-eligible contract; monitor front/next open interest; migrate when next-contract liquidity dominates; **force roll before the exchange-defined delivery/staggered-delivery deadline regardless of the liquidity signal** — deadline comes from the dated contract master, never a global `days_before_expiry = N` constant |
| Mandatory baseline to beat | Zero position; buy-and-hold/long-only where meaningful; single 12-month sign trend; volatility-scaled long exposure |

**`MCX_CARRY_01` — MCX commodity curve carry (first complementary challenger, kept separate)**

| Field | Value |
|---|---|
| Requirement | Two liquid simultaneous expiries per commodity |
| Formula | `curve_slope = 365/(expiry2-expiry1 in days) * ln(F2/F1)`; `carry = -curve_slope` (so backwardation → positive carry score) |
| Cross-sectional standardization | Only when enough commodities have simultaneous data; otherwise each commodity's own rolling historical percentile |
| Baseline use | Standalone ranking/directional signal |
| **Integration rule** | **Prohibited from blending with trend until its own standalone OOS test passes**, and even then only if `ΔU = U(trend+carry) - U(trend)` stays positive after costs/turnover/complexity |

**`RISK_01` — India VIX risk/diagnostic layer**

- India VIX = 30-calendar-day expected Nifty volatility from Nifty option prices. Role: monitoring and risk scaling, **not** a directional signal in generation one.
- `σ̂_p = sqrt(252 * w^T Σ w)` — portfolio ex-ante vol from an **estimated covariance matrix** (not a zero-correlation shortcut — a real methodological upgrade over the global-futures system's documented simplification).
- `k_t = min(1, 0.10 / σ̂_p,t)` — scale **down only**; no leverage-up in generation one.
- Risk budget starts **50:50 between the NSE and MCX sleeves** — a neutral baseline, not presumed optimal. Carry starts at **zero allocation** until independently validated.

### 1.2 Explicitly deferred (research's own prioritization, not this project's shortcut)

Quality challenger (blocked on licensed point-in-time fundamentals), options/PCR/IV-skew features (phase two), ML challengers (only after the three baselines above are frozen; ridge/logistic + one boosting model first, neural nets only if simpler models demonstrably miss nonlinear signal), regime HMM filter (continuous risk scaling only in gen 1; a hard filter must prove OOS marginal benefit before approval), intraday mean reversion, options trading, sentiment, deep learning, reinforcement learning, LLM-directed trading — all explicitly excluded from generation one by the research itself.

### 1.3 Market structure (versioned, dated — never hardcoded as timeless)

| Venue/segment | Current session (as of this research) | Note |
|---|---|---|
| NSE cash equity | 09:15–15:30 (pre-open from 09:00) | |
| NSE equity derivatives | 09:15–15:40 | **Different close time than cash** — cannot share one assumed close timestamp |
| NSE F&O expiry | **Tuesday** (index families and individual securities), previous trading day if Tuesday is a holiday | Was historically Thursday — never encode either as a timeless rule |
| MCX internationally-referenceable non-agri | 09:00–23:30 during US DST; 09:00–23:55 after DST ends | DST-dependent |
| MCX internationally-referenceable agri | 09:00–21:00 | |
| MCX other agri | 09:00–17:00 | |

Required as a **versioned table**, not literals: `exchange, segment, instrument_family, effective_from, effective_to, session_open, session_close, preopen_start, preopen_end, holiday_type, morning_session_open, evening_session_open, special_session, source_document_id, source_date`.

### 1.4 Cost model (current as of the research's citation date; must be versioned, never hardcoded)

`C_trade = C_brokerage + C_exchange + C_regulatory + C_STT/CTT + C_stamp + C_GST + C_spread + C_impact + C_roll`

| Charge | Current rate |
|---|---|
| Equity-futures STT | 0.05% on sale value, seller |
| Option-sale STT | 0.15% of premium, seller |
| Exercised-option STT | 0.15% of intrinsic value, purchaser |
| Delivery-equity STT | 0.1% on qualifying purchase **and** 0.1% on qualifying sale |
| SEBI turnover fee | 0.0001% (₹10/crore), non-debt purchase/sale |
| Equity-futures stamp duty | 0.002%, buyer |
| Equity-options stamp duty | 0.003%, buyer |
| Commodity-futures stamp duty | 0.002%, buyer |
| GST on stock-broker services | 18% |

Report every candidate at zero cost, current-modelled cost, 2×, and 3× variable execution costs. **"Missing costs invalidate rather than silently zero the backtest"** — a fail-loud requirement, not a default-to-zero one.

### 1.5 Validation split (exact dates, not a generic 80/20)

- Discovery/training: earliest reliable history → **2018-12-31**
- Validation/walk-forward model selection: **2019-01-01 → 2022-12-31**
- Untouched final holdout: **2023-01-01 → 2026-08-31**, opened once after design freeze
- An asset lacking sufficient early history gets an explicit `INSUFFICIENT_HISTORY` status and is excluded — the split is never opportunistically reshaped around what data happens to exist.

### 1.6 Statistical/process requirements beyond what the global-futures system already has

- **PBO (Probability of Backtest Overfitting)** diagnostic, alongside DSR — not yet implemented anywhere in this codebase.
- **Block-bootstrap + trade-order-permutation Monte Carlo** (not naive i.i.d. daily-return shuffling, which destroys serial dependence) — not yet implemented.
- Complementarity acceptance quantified as `ΔSR = SR(A+B) - SR(A)`, reported with drawdown/ES/turnover/cost/worst-year/downside-correlation/recovery-time changes.
- An explicit, reusable experiment-ledger schema (`experiment_id, research_family, strategy_version, git_commit, dataset_version, universe_version, exchange_rule_version, feature_version, cost_version, train/validation/test start-end, parameters, random_seed, number_of_prior_trials, gross_metrics, net_metrics, stress_metrics, failure_reason, decision, created_at_ist`) — richer than the existing `ExperimentRecord`.

---

## 2. Audit

| # | Claim | Category | Note |
|---|---|---|---|
| 1 | NSE cross-sectional momentum is India-supported (BSE-panel studies, NSE's own Nifty200 Momentum 30 methodology) | **India-supported (per the doc's own tier system), REQUIRES REPLICATION here** | The doc itself distinguishes "India-supported" from "MCX/NSE-replicated" and states plainly: "No proposed strategy in this document has yet been empirically replicated by this project." We inherit that same status — nothing here is validated until run on real data. |
| 2 | MCX diversified trend "Priority A, conditional on MCX replication" | **REQUIRES REPLICATION**, explicitly self-flagged | The doc explicitly withholds full confidence pending replication — we preserve that caveat rather than treating "Priority A" as "proven." |
| 3 | MCX carry "requires reliable multi-expiry contract histories" and is "Priority B" | **AMBIGUOUS pending data**, **CONFLICTING integration rule is intentional, not a bug**: the doc simultaneously calls carry a promising complement (research-prior matrix, "High diversification candidate") and prohibits blending it until it independently passes OOS — this is deliberate caution, not a contradiction, and we implement it that way (built, disabled). |
| 4 | India low-volatility factor: "one NSE study reports a low-risk effect... another does not... a third reports high-volatility stocks outperforming" | **CONFLICTING, correctly not promoted to alpha** | The doc's own conclusion — "do not treat as established," keep as a risk-construction input only — is followed; no low-vol strategy is built. |
| 5 | 63/126/252 lookback for MCX_TREND_01 (the challenger variant, not baseline) coincides with the *global futures* research's own frozen baseline lookback set | **Coincidence, not a license to merge** | These are two independently frozen baselines from two different documents for two different universes (global diversified futures vs. MCX-only). §3 below keeps them as separate configs; the overlap is noted but not exploited to justify sharing one config object. |
| 6 | India VIX "is a valid forward-volatility measure; directional value unproven" | **VERIFIED as a measure (NSE's own published methodology), UNSUPPORTED as a directional signal** | Implemented strictly as a diagnostic feeding the vol-scaler, never as a trade direction input — matches the doc's own instruction. |
| 7 | Current NSE STT/stamp-duty/GST figures (§1.4) | **VERIFIED as of the doc's citation date, must be re-verified at real-money implementation time** | Same caveat already logged for the global system's India-branch cost note in `Implementation_Spec.md` — today (2026-09-20) is after the 2026-04-01 effective date, so these are presumably current, but this project has not independently queried NSE for a live confirmation. |
| 8 | Exact NSE/MCX session times, F&O expiry weekday, MCX DST-dependent sessions | **VERIFIED as of the doc's citation date, explicitly time-sensitive** | The doc itself warns these "have changed enough to invalidate recycled backtests" — implemented as a versioned table (§4.2) precisely so a future change doesn't require rewriting strategy code. |

---

## 3. Blending Reconciliation (this project's explicit design decision, logged per Prompt.md §3's spirit)

The user chose **one blended universe** (NSE+MCX combined with the existing global-futures system in a single portfolio) over two separate tracked experiments. This section states exactly what "blended" means here and what is deliberately kept separate, so neither research document's frozen parameters are silently altered by the act of combining them.

**Kept separate, per-sleeve (never merged into one shared config):**

| Parameter | Global-futures trend (existing) | MCX_TREND_01 (new) | EQ_MOM_01 (new) |
|---|---|---|---|
| Lookbacks | 63/126/252 | **21/63/126/252** | 6-month/12-month vol-adjusted (not a sign-trend at all — a ranking score) |
| Vol estimator | 60-day EWMA | **60-day realized (rolling std)**, EWMA is a challenger | 252-day realized vol (for the vol-adjustment denominator, per its own formula) |
| Rebalance | Weekly (baseline) | **Daily** | **Monthly** |
| Sizing | Time-series vol-scaled, hierarchical asset-class risk parity | Time-series vol-scaled, single-bucket normalization | Cross-sectional inverse-vol among selected names, sector-capped |
| Cost model | Generic per-asset-class bps | **Itemized India charge schedule** (§1.4) | **Itemized India charge schedule** (§1.4) |

**Actually blended (the new capability this milestone adds):** a portfolio-level aggregator combines whatever sleeves are active — global-futures trend, MCX trend, NSE momentum — under **equal ex-ante risk per sleeve** (generalizing the existing trend+carry aggregator from 2 to N sleeves, and from "asset-class-only" internal sizing to "each sleeve fully sizes itself, then sleeves are combined"). MCX carry is built but **excluded from the blend** per its own integration rule (§1.1) until it independently passes OOS — exactly mirroring how the global-futures carry satellite stays disabled.

**Portfolio-level vol targeting**: the India research specifies a real covariance-based `σ̂_p` rather than the global system's documented zero-correlation simplification. Implemented as a **new, opt-in** rolling-covariance estimator (`portfolio/covariance.py`) used only by the new blended engine — the original global-futures `portfolio/sizing.py` path is **not modified**, so its existing (tested, documented) behavior and all Milestone-1/2 results remain exactly reproducible.

**New engine, not a modification of the existing one**: per-sleeve rebalance frequency (daily/weekly/monthly, each sleeve on its own clock) requires a genuinely different backtest loop than `BacktestEngine` (which assumes one global frequency). Rather than risk destabilizing the tested global-futures path, this is a **new class**, `backtest/blended_engine.py:BlendedPortfolioEngine`, reusing the same cost/execution-timing/metrics primitives. This is an additive architecture change, not a silent modification of frozen research parameters — logged here per Prompt.md §3's format:

1. *Original specification*: `BacktestEngine` assumes one portfolio-wide rebalance frequency and execution delay.
2. *Problem*: EQ_MOM_01 (monthly), MCX_TREND_01 (daily), and the existing global trend sleeve (weekly) each specify their own frequency; blending them requires per-sleeve scheduling.
3. *Modification*: new `BlendedPortfolioEngine` class supporting per-sleeve schedules, alongside (not replacing) `BacktestEngine`.
4. *Reason*: avoid changing tested, working code for the already-validated global-futures path.
5. *Expected effect*: none on existing results; new capability only.
6. *Needs separate validation*: yes — the new engine has its own test suite (see `tests/`), independent of the existing engine's tests.

---

## 3.1 Synthetic-Data Result and a Data-Construction Bias Worth Flagging Loudly

**Numbers below are from the corrected run** after fixing the cross-process
reproducibility bug described in §3.2 (Python's built-in `hash()` on
strings is randomized per process; an earlier run of this same command, in
a different process, produced different numbers from "the same" config —
see §3.2). Running `cli/run_india_blended_backtest.py` against the default
synthetic config (2010-2023, 64 NSE-style equities, 7 MCX-style
commodities) now reproducibly produces:

| | Sharpe | Note |
|---|---|---|
| Blended (EQ_MOM_01 + MCX_TREND_01, 50:50) | −0.217 | |
| EQ_MOM_01 standalone | +0.071 | roughly flat |
| MCX_TREND_01 standalone | −0.593 | negative, similar whipsaw pattern to the global-futures system's own synthetic result |
| **MCX_CARRY_01 standalone** | **+1.142** | passes all three implemented activation-gate criteria |

### 3.2 Bug Found and Fixed: Non-Deterministic Synthetic Data Across Processes

`data/synthetic.py`, `data/synthetic_equity.py`, `data/synthetic_curve.py`,
and `strategies/carry.py` all derived a per-symbol RNG seed via
`hash(symbol) % N`, using Python's *built-in* `hash()`. Since Python 3.3,
string hashing is randomized per process (`PYTHONHASHSEED`) unless
explicitly fixed — meaning "the same `random_seed=42` config" silently
produced *different* fabricated data every time a fresh process ran it.
This was caught by re-running the (nominally identical) robustness suite in
a separate process and finding a materially different baseline Sharpe.
Fixed with a SHA256-based `stable_hash()` (`trading_system/util.py`),
verified by a new regression test
(`tests/integration/test_cross_process_reproducibility.py`) that spawns two
Python processes with *different* `PYTHONHASHSEED` values and asserts
byte-identical output. This directly violated Prompt.md §28's
reproducibility requirement and is exactly the kind of defect this
project's own testing discipline exists to catch — flagged here rather than
silently corrected without a trace. The qualitative pattern of every result
already discussed in this document (blended negative, MCX trend negative,
carry strongly positive due to the data-construction bias in §3.1) held
before and after the fix; only the precise figures changed.

**The MCX_CARRY_01 result must not be read as evidence carry "works."** It is very likely a **synthetic-data construction artifact**: the carry signal (`data/synthetic_curve.py`'s regime-switching `basis_slope`) is read *directly and contemporaneously* from today's front/next contract prices, with zero estimation lag. The trend signals, by contrast, are backward-looking averages over 21-252 day windows that necessarily lag behind a regime change. Since the synthetic generator's regimes are genuinely persistent (by construction, to give trend something to detect), carry's zero-lag read of that same persistence detects it far more cleanly than trend's lagged-average read does — an asymmetry in how the fabricated data happens to be constructed, not a finding about real commodity curves. The activation gate correctly identified a strong, low-correlation, cost-surviving signal and said "activate" — which shows the **gate mechanics work as designed** — but `IndiaSystemConfig`'s hard safeguard (§ below) still keeps `mcx_carry_01`'s risk share at zero in the actual blended portfolio, exactly as intended: a synthetic-data pass is not sufficient grounds for a real-data decision, and none was made here.

## 4. Things Implemented This Milestone

See `Docs/Final_Report.md` (updated) for the authoritative up-to-date status. Built and tested (149 total tests across the whole project):

- `CrossSectionalMomentumStrategy` (EQ_MOM_01) -- top-N selection, inverse-vol weighting, single-name/sector caps, restricted to its own eligible asset class (a real scope bug was found and fixed here during integration: it initially scored every instrument in a shared multi-asset-class store, not just NSE equities -- see `tests/unit/test_cross_sectional_momentum.py`'s regression test).
- `MCXTrendSleeve` (MCX_TREND_01) -- reuses `features.trend_signal.composite_trend_score` unchanged with the 4-horizon [21,63,126,252] set and 60-day realized (not EWMA) volatility, flat cross-asset normalization.
- `MCXCarryStrategy` (MCX_CARRY_01) -- curve-slope formula, built and unit-tested, deliberately never wired into the blended engine's sleeve list.
- `data/roll.py` -- deterministic active-contract/front-next resolution from dated contract metadata (fixed-days-before-expiry only; OI-based early migration deferred, no real OI data yet).
- `data/synthetic_equity.py`, `data/synthetic_curve.py` -- fabricated NSE-equity (sector-labeled, regime-switching alpha) and MCX-curve (index + multi-expiry dated contracts, regime-switching basis slope) data, same "pipeline check, not evidence" status as the global system's synthetic data.
- `data/combined.py` -- `CombinedDataSource`, the actual blending primitive.
- `portfolio/covariance.py`, `portfolio/blend.py` -- rolling-covariance vol estimate and equal-ex-ante-risk-per-sleeve blending (RISK_01), kept separate from the global-futures system's zero-correlation sizing path.
- `portfolio/participation.py` -- liquidity participation cap.
- `execution/india_costs.py` -- itemized India cost model (STT variants, stamp duty, SEBI turnover fee, GST on brokerage, all versioned; brokerage/spread/impact are placeholder estimates, MCX CTT rate is an explicit unfilled gap).
- `backtest/blended_engine.py` -- `BlendedPortfolioEngine`, per-sleeve rebalance scheduling (monthly/daily coexisting), contract-roll resolution, covariance-based vol targeting. Performance note: an initial version recomputed a full ~500+-instrument covariance matrix every trading day regardless of how few symbols were actually active; fixed to slice to only the currently-held symbols first (~6x speedup), since this matters for a system meant to scale to real multi-year, multi-instrument data.
- `backtest/validation_split.py` -- the exact discovery/validation/holdout date split from §1.5.
- `config/india_schema.py` -- `IndiaSystemConfig`, with a hard `__post_init__` safeguard against ever giving `mcx_carry_01` a nonzero blended risk share.
- `cli/run_india_blended_backtest.py` -- runs the blended portfolio, each sleeve standalone, the carry activation gate, and the validation split; logs to the shared experiment tracker.

## 5. Explicitly Not Implemented (flagged, not silently skipped)

Real NSE/MCX data (still synthetic-only, same limitation as the global-futures system), rank-buffer hysteresis challenger for EQ_MOM_01 (baseline top-30 only implemented; the hysteresis variant is a documented follow-up), the exact validation-split dates as an enforced default (the utility exists and is tested but isn't yet wired as the default for every report), PBO diagnostic, block-bootstrap/trade-order-permutation Monte Carlo, versioned exchange-calendar data beyond the single current snapshot transcribed from the research document, real instrument-master fields beyond the subset needed for the synthetic backtest, NSE quality challenger, India-VIX-as-directional-signal (correctly excluded per research), options features, ML challengers, circuit-breaker/halt simulation, intraday execution mode.
