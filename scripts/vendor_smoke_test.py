"""Manual, live smoke test for a broker/vendor adapter.

The automated test suite (tests/unit/test_zerodha_adapter.py,
test_angel_one_adapter.py, test_indmoney_adapter.py) only exercises each
adapter's parsing/chunking/caching logic against a MOCKED client, because
this development environment has no authenticated Angel One or INDmoney
session, and its Zerodha Kite session isn't logged in either. That is a
real gap: none of the three vendor adapters have been checked against a
live account. Run this script yourself, with your own credentials, before
trusting an adapter for actual research.

This script deliberately does not read or accept API keys/passwords/TOTP
anywhere -- per this project's credential policy, YOU authenticate using
the vendor's own official SDK/login flow, then pass the resulting client
object to the block below. Uncomment only the vendor you're testing.

Run with: python scripts/vendor_smoke_test.py
"""
from __future__ import annotations

from datetime import date, timedelta


def smoke_test_zerodha() -> None:
    # from kiteconnect import KiteConnect
    # kite = KiteConnect(api_key="YOUR_API_KEY")
    # kite.set_access_token("YOUR_ACCESS_TOKEN")  # from your own login flow
    #
    # from trading_system.brokers.base import InstrumentMapping
    # from trading_system.brokers.zerodha_kite import ZerodhaKiteDataSource
    #
    # mapping = [InstrumentMapping(symbol="RELIANCE", asset_class="equity_index", vendor_id="738561")]
    # source = ZerodhaKiteDataSource(kite, mapping, date.today() - timedelta(days=30), date.today())
    # df = source.get_prices("RELIANCE")
    # print(df.tail())
    # assert not df.empty and df.index.is_monotonic_increasing
    print("Uncomment and fill in your Kite session to run this smoke test.")


def smoke_test_angel_one() -> None:
    # from SmartApi import SmartConnect
    # import pyotp
    # smart = SmartConnect(api_key="YOUR_API_KEY")
    # smart.generateSession("YOUR_CLIENT_CODE", "YOUR_PASSWORD", pyotp.TOTP("YOUR_TOTP_SECRET").now())
    #
    # from trading_system.brokers.base import InstrumentMapping
    # from trading_system.brokers.angel_one import AngelOneDataSource
    #
    # mapping = [InstrumentMapping(symbol="RELIANCE", asset_class="equity_index", vendor_id="2885", exchange="NSE")]
    # source = AngelOneDataSource(smart, mapping, date.today() - timedelta(days=30), date.today())
    # df = source.get_prices("RELIANCE")
    # print(df.tail())
    # assert not df.empty and df.index.is_monotonic_increasing
    print("Uncomment and fill in your Angel One session to run this smoke test.")


def smoke_test_indmoney() -> None:
    # import requests
    # session = requests.Session()
    # access_token = "YOUR_ACCESS_TOKEN"  # from indstocks.com dashboard or /generate/token
    #
    # from trading_system.brokers.base import InstrumentMapping
    # from trading_system.brokers.indmoney import INDmoneyDataSource
    #
    # mapping = [InstrumentMapping(symbol="TCS", asset_class="equity_index", vendor_id="NSE_11536")]
    # source = INDmoneyDataSource(session, access_token, mapping, date.today() - timedelta(days=30), date.today())
    # df = source.get_prices("TCS")
    # print(df.tail())
    # assert not df.empty and df.index.is_monotonic_increasing
    #
    # NOTE: if this fails with an interval error, the daily-interval string
    # guessed in indmoney.py ("1day") may be wrong -- check the response
    # error message and fix INDmoneyDataSource's default interval.
    print("Uncomment and fill in your INDstocks access token to run this smoke test.")


if __name__ == "__main__":
    smoke_test_zerodha()
    smoke_test_angel_one()
    smoke_test_indmoney()
