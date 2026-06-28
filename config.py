"""
Configuration for the ZigZag Harmonic Pattern bot.

These mirror the `input()` parameters from the original Pine Script,
plus the new settings needed to run standalone (data source, Telegram, paper trading).
"""

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
EXCHANGE_ID = "hyperliquid"          # ccxt exchange id (public endpoints only, no API key needed)
SYMBOL = "BTC/USDT"
BASE_TIMEFRAME = "1m"            # the timeframe candles are fetched/streamed at
POLL_SECONDS = 5                 # how often to check for a new closed candle

# ---------------------------------------------------------------------------
# Strategy inputs (from the original .pine script)
# ---------------------------------------------------------------------------
USE_HEIKIN_ASHI = False          # useHA
USE_ALT_TIMEFRAME = True         # useAltTF
ALT_TIMEFRAME = "60"             # tf  (Pine "60" = 60 minutes = 1h). Use ccxt-style "1h" internally.
ALT_TIMEFRAME_CCXT = "1h"        # ccxt resample target corresponding to ALT_TIMEFRAME

SHOW_PATTERNS = True             # showPatterns (cosmetic in Pine; kept for parity/logging)

# Fibonacci levels to compute/display (all True in the original)
FIB_LEVELS = {
    "0.000": True,
    "0.236": True,
    "0.382": True,
    "0.500": True,
    "0.618": True,
    "0.764": True,
    "1.000": True,
}

# ---------------------------------------------------------------------------
# Target 1 / Target 2 trade parameters (from the original inputs)
# ---------------------------------------------------------------------------
TARGET01_TRADE_SIZE_PCT = 20.0   # % of equity
TARGET01_EW_RATE = 0.236         # entry window fib rate
TARGET01_TP_RATE = 0.618         # take-profit fib rate
TARGET01_SL_RATE = -0.236        # stop-loss fib rate

TARGET02_ACTIVE = False
TARGET02_TRADE_SIZE_PCT = 20.0
TARGET02_EW_RATE = 0.236
TARGET02_TP_RATE = 1.618
TARGET02_SL_RATE = -0.236

# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------
INITIAL_CAPITAL = 500.0          # matches strategy(initial_capital=500) in the original
PYRAMIDING = 0                   # strategy(pyramiding=0): only one open position per direction at a time

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
import os

TELEGRAM_BOT_TOKEN = '8963017446:AAGX-YLLJ-o8yJeiwXsVImvpsSbFfVJ1u7U'
TELEGRAM_CHAT_ID = '5552791187'

# ---------------------------------------------------------------------------
# History / lookback
# ---------------------------------------------------------------------------
HISTORY_BARS = 500                # how many historical candles to seed on startup
LOG_FILE = "logs/zigzag_bot.log"
TRADES_CSV = "logs/trades.csv"
