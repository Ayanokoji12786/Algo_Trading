"""Vendor/broker data-source adapters.

Every adapter here implements trading_system.data.interfaces.DataSource
(get_universe, get_prices) -- that two-method contract is the entire
integration surface. See Docs/Vendor_Integration.md for which vendors are
ready to use out of the box and how to add another one.

Adapter classes are not re-exported at package level -- import the one you
need directly, e.g. ``from trading_system.brokers.zerodha_kite import
ZerodhaKiteDataSource``. None of these modules import a vendor SDK
themselves (they accept an already-authenticated client via a typing
Protocol, structurally, not by inheritance), so trading_system.brokers has
no hard dependency on kiteconnect/smartapi-python/requests being installed;
you only need the relevant SDK installed to *create* that authenticated
client in your own script (see pyproject.toml's optional dependency groups
for which package that is per vendor).
"""
