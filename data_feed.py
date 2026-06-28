"""
Market data feed: fetches OHLCV from a crypto exchange (via ccxt, public endpoints,
no API key needed for candle data), with optional Heikin-Ashi conversion and
optional resampling to an "alt timeframe" -- mirroring the original script's
`useHA` and `useAltTF` + `security(_ticker, tf, ...)` behavior.
"""

import time
import pandas as pd
import ccxt

import config


def make_exchange():
    exchange_cls = getattr(ccxt, config.EXCHANGE_ID)
    return exchange_cls({"enableRateLimit": True})


def fetch_ohlcv_df(exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def to_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standard Heikin-Ashi conversion, equivalent to Pine's heikenashi(tickerid):
        HA_close = (O+H+L+C)/4
        HA_open  = (prevHA_open + prevHA_close)/2   (first bar: (O+C)/2)
        HA_high  = max(H, HA_open, HA_close)
        HA_low   = min(L, HA_open, HA_close)
    """
    ha = df.copy()
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    ha_open = pd.Series(index=df.index, dtype="float64")

    ha_open.iloc[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0

    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)

    ha["open"] = ha_open
    ha["high"] = ha_high
    ha["low"] = ha_low
    ha["close"] = ha_close
    return ha


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    Resample base-timeframe candles up to a higher timeframe, e.g. 1m -> 1h.
    This is the standalone equivalent of Pine's security(_ticker, tf, ...) call
    that samples the alt-timeframe zigzag only once per new alt-tf bar
    (`change(time(tf)) != 0`).
    """
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = df.resample(rule).agg(agg).dropna()
    return out


PANDAS_RULE_MAP = {
    "1": "1min", "3": "3min", "5": "5min", "15": "15min", "30": "30min",
    "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
    "D": "1D", "W": "1W",
}


def pine_tf_to_pandas_rule(pine_tf: str) -> str:
    return PANDAS_RULE_MAP.get(pine_tf, pine_tf)
