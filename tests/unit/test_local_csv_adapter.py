import pandas as pd

from trading_system.brokers.local_csv import LocalFileDataSource
from trading_system.data.interfaces import ContractMeta


def test_loads_csv_with_standard_columns(tmp_path):
    df = pd.DataFrame(
        {
            "Date": ["2020-01-01", "2020-01-02"],
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [100, 200],
        }
    )
    df.to_csv(tmp_path / "MYSTOCK.csv", index=False)

    source = LocalFileDataSource(
        tmp_path, universe=[ContractMeta(symbol="MYSTOCK", asset_class="equity_index")]
    )
    result = source.get_prices("MYSTOCK")
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result.index.is_monotonic_increasing


def test_loads_parquet_in_preference_to_csv(tmp_path):
    parquet_df = pd.DataFrame(
        {"open": [9.0], "high": [9.0], "low": [9.0], "close": [9.0], "volume": [1]},
        index=pd.to_datetime(["2021-01-01"]),
    )
    parquet_df.index.name = "date"
    parquet_df.to_parquet(tmp_path / "X.parquet")
    pd.DataFrame({"date": ["2020-01-01"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}).to_csv(
        tmp_path / "X.csv", index=False
    )

    source = LocalFileDataSource(tmp_path, universe=[ContractMeta(symbol="X", asset_class="fx")])
    result = source.get_prices("X")
    assert result.iloc[0]["open"] == 9.0


def test_raises_when_file_missing(tmp_path):
    source = LocalFileDataSource(tmp_path, universe=[ContractMeta(symbol="NOPE", asset_class="fx")])
    try:
        source.get_prices("NOPE")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_raises_when_no_date_column(tmp_path):
    pd.DataFrame({"open": [1], "close": [1]}).to_csv(tmp_path / "BAD.csv", index=False)
    source = LocalFileDataSource(tmp_path, universe=[ContractMeta(symbol="BAD", asset_class="fx")])
    try:
        source.get_prices("BAD")
        assert False, "expected ValueError"
    except ValueError:
        pass
