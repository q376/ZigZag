"""
Main loop for the standalone ZigZag Harmonic Pattern bot.

Replicates, bar-by-bar, the logic of the original Pine strategy:

    target01_buy_entry = (buy_patterns_00 or buy_patterns_01) and close <= f_last_fib(target01_ew_rate)
    target01_buy_close = high >= f_last_fib(target01_tp_rate) or low <= f_last_fib(target01_sl_rate)
    target01_sel_entry = (sel_patterns_00 or sel_patterns_01) and close >= f_last_fib(target01_ew_rate)
    target01_sel_close = low <= f_last_fib(target01_tp_rate) or high >= f_last_fib(target01_sl_rate)

    (and the analogous target02_* block, gated by target02_active)

Flow each cycle:
  1. Fetch latest candles.
  2. Build the "trading" series: either raw base-tf candles (useAltTF=False),
     or base-tf candles resampled to the alt timeframe (useAltTF=True) -- since
     the zigzag/patterns in the original are computed on whichever series sz
     ends up representing.
  3. Optionally convert that series to Heikin-Ashi.
  4. Run the zigzag state machine bar-by-bar to get x/a/b/c/d.
  5. Detect harmonic patterns, compute fib levels off c/d.
  6. Evaluate entry/close conditions against the latest CLOSED bar, fire trades
     + Telegram alerts.
"""

import time
import sys
import traceback

import pandas as pd

import config
from data_feed import (
    make_exchange, fetch_ohlcv_df, to_heikin_ashi, resample_ohlcv, pine_tf_to_pandas_rule,
)
from zigzag_engine import ZigZagState, update_zigzag, get_xabcd, detect_patterns, fib_levels
from paper_broker import PaperBroker
from notifier import send_telegram


def build_trading_series(base_df: pd.DataFrame) -> pd.DataFrame:
    """
    Mirrors:
        _ticker = useHA ? heikenashi(tickerid) : tickerid
        sz = useAltTF ? (change(time(tf)) != 0 ? security(_ticker, tf, zigzag()) : na) : zigzag()

    i.e. choose alt-timeframe resampling if enabled, then Heikin-Ashi conversion
    if enabled, on top of whichever timeframe we land on.
    """
    df = base_df
    if config.USE_ALT_TIMEFRAME:
        rule = pine_tf_to_pandas_rule(config.ALT_TIMEFRAME)
        df = resample_ohlcv(df, rule)
    if config.USE_HEIKIN_ASHI:
        df = to_heikin_ashi(df)
    return df


def replay_zigzag(df: pd.DataFrame):
    """
    Feeds the full historical dataframe through the zigzag state machine to
    rebuild x/a/b/c/d as of the most recent CLOSED bar. Returns (state, xabcd).
    """
    state = ZigZagState()
    for _, row in df.iterrows():
        update_zigzag(state, row["open"], row["high"], row["low"], row["close"])
    return state, get_xabcd(state)


def evaluate_and_trade(broker: PaperBroker, last_bar, xabcd):
    """
    last_bar: pandas Series with open/high/low/close of the latest CLOSED bar
              on the *base* timeframe (entries/exits use raw price action,
              matching the original script's close/high/low references which
              run on the chart's native series regardless of sz's timeframe).
    xabcd: (x, a, b, c, d) tuple, or None if not enough pivots yet.
    """
    if xabcd is None:
        return

    x, a, b, c, d = xabcd
    close, high, low = last_bar["close"], last_bar["high"], last_bar["low"]

    bull_hits = detect_patterns(x, a, b, c, d, mode=1)
    bear_hits = detect_patterns(x, a, b, c, d, mode=-1)

    buy_patterns = len(bull_hits) > 0
    sel_patterns = len(bear_hits) > 0

    levels, f_last_fib = fib_levels(c, d)

    _run_target(
        broker, target_name="target01",
        trade_size_pct=config.TARGET01_TRADE_SIZE_PCT,
        ew_rate=config.TARGET01_EW_RATE, tp_rate=config.TARGET01_TP_RATE, sl_rate=config.TARGET01_SL_RATE,
        active=True,
        buy_patterns=buy_patterns, sel_patterns=sel_patterns,
        close=close, high=high, low=low, f_last_fib=f_last_fib,
        bull_hits=bull_hits, bear_hits=bear_hits,
    )

    _run_target(
        broker, target_name="target02",
        trade_size_pct=config.TARGET02_TRADE_SIZE_PCT,
        ew_rate=config.TARGET02_EW_RATE, tp_rate=config.TARGET02_TP_RATE, sl_rate=config.TARGET02_SL_RATE,
        active=config.TARGET02_ACTIVE,
        buy_patterns=buy_patterns, sel_patterns=sel_patterns,
        close=close, high=high, low=low, f_last_fib=f_last_fib,
        bull_hits=bull_hits, bear_hits=bear_hits,
    )


def _run_target(broker, target_name, trade_size_pct, ew_rate, tp_rate, sl_rate, active,
                 buy_patterns, sel_patterns, close, high, low, f_last_fib,
                 bull_hits, bear_hits):
    if not active:
        return

    buy_slot = f"{target_name}_buy"
    sel_slot = f"{target_name}_sell"

    buy_entry_cond = buy_patterns and close <= f_last_fib(ew_rate)
    buy_close_cond = high >= f_last_fib(tp_rate) or low <= f_last_fib(sl_rate)
    sel_entry_cond = sel_patterns and close >= f_last_fib(ew_rate)
    sel_close_cond = low <= f_last_fib(tp_rate) or high >= f_last_fib(sl_rate)

    # --- closes first (mirrors strategy.close being independent of new entries) ---
    if broker.has_open(buy_slot) and buy_close_cond:
        pnl = broker.close_position(buy_slot, price=close)
        send_telegram(f"🔵 CLOSE {buy_slot} @ {close:.2f} | PnL: {pnl:+.2f} | Equity: {broker.equity:.2f}")

    if broker.has_open(sel_slot) and sel_close_cond:
        pnl = broker.close_position(sel_slot, price=close)
        send_telegram(f"🔴 CLOSE {sel_slot} @ {close:.2f} | PnL: {pnl:+.2f} | Equity: {broker.equity:.2f}")

    # --- entries ---
    if buy_entry_cond:
        pos = broker.open_position(buy_slot, side="long", trade_size_pct=trade_size_pct,
                                    price=close, comment=f"buy {target_name}")
        if pos:
            send_telegram(
                f"🟢 ENTRY {buy_slot} LONG @ {close:.2f} | qty={pos.qty:.6f}\n"
                f"Patterns: {', '.join(bull_hits)}"
            )

    if sel_entry_cond:
        pos = broker.open_position(sel_slot, side="short", trade_size_pct=trade_size_pct,
                                    price=close, comment=f"sell {target_name}")
        if pos:
            send_telegram(
                f"🟢 ENTRY {sel_slot} SHORT @ {close:.2f} | qty={pos.qty:.6f}\n"
                f"Patterns: {', '.join(bear_hits)}"
            )


def main():
    exchange = make_exchange()
    broker = PaperBroker(initial_capital=config.INITIAL_CAPITAL)

    send_telegram(
        f"🤖 ZigZag bot started\nSymbol: {config.SYMBOL}\nBase TF: {config.BASE_TIMEFRAME}\n"
        f"Alt TF: {config.ALT_TIMEFRAME if config.USE_ALT_TIMEFRAME else 'disabled'}\n"
        f"Initial capital: {config.INITIAL_CAPITAL}"
    )

    last_seen_bar_time = None

    while True:
        try:
            base_df = fetch_ohlcv_df(exchange, config.SYMBOL, config.BASE_TIMEFRAME, config.HISTORY_BARS)

            # drop the last (still-forming) candle -- only act on CLOSED bars
            closed_base_df = base_df.iloc[:-1]
            current_bar_time = closed_base_df.index[-1]

            if current_bar_time != last_seen_bar_time:
                last_seen_bar_time = current_bar_time

                trading_df = build_trading_series(closed_base_df)
                state, xabcd = replay_zigzag(trading_df)

                last_base_bar = closed_base_df.iloc[-1]
                evaluate_and_trade(broker, last_base_bar, xabcd)

                print(f"[{current_bar_time}] close={last_base_bar['close']:.2f} "
                      f"equity={broker.equity:.2f} open={list(broker.positions.keys())}")

            time.sleep(config.POLL_SECONDS)

        except KeyboardInterrupt:
            send_telegram("🛑 Bot stopped manually.")
            break
        except Exception as e:
            err = f"⚠️ Bot error: {e}"
            print(err)
            traceback.print_exc()
            send_telegram(err)
            time.sleep(config.POLL_SECONDS * 2)


if __name__ == "__main__":
    main()
