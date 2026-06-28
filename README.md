# ZigZag Harmonic Pattern Bot (standalone Python port)

This is a standalone Python port of the TradingView Pine Script
`[STRATEGY][RS]ZigZag PA Strategy V4.1`. It runs outside TradingView,
pulls live candles from Binance's public API, replicates the script's
zigzag + harmonic-pattern + Fibonacci-target logic, **paper-trades**
the signals (no real money, no exchange API key required), and sends
a Telegram alert on every entry/exit.

## What got ported

| Original Pine concept | Python equivalent |
|---|---|
| `zigzag()` (candle-flip zigzag) | `zigzag_engine.update_zigzag()` |
| `valuewhen(sz, sz, n)` for x/a/b/c/d | `zigzag_engine.get_xabcd()` (deque of last 5 pivots) |
| 16 `isXxx()` harmonic pattern functions | 1:1 ported in `zigzag_engine.py` |
| `f_last_fib()` / fib plots | `zigzag_engine.fib_levels()` |
| `useHA` (Heikin-Ashi) | `data_feed.to_heikin_ashi()` |
| `useAltTF` + `security(tf, ...)` | `data_feed.resample_ohlcv()` |
| `strategy.entry/close`, equity, pyramiding=0 | `paper_broker.PaperBroker` |
| Alerts (new — TradingView used plot labels) | `notifier.send_telegram()` |

## Setup

```bash
pip install -r requirements.txt
```

Set your Telegram credentials as environment variables (create a bot via
[@BotFather](https://t.me/BotFather) and get your chat ID via @userinfobot
or similar):

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-your-token"
export TELEGRAM_CHAT_ID="123456789"
```

If you skip this, the bot still runs — alerts just print to the console
instead of sending to Telegram.

## Configure

Edit `config.py`:
- `SYMBOL`, `BASE_TIMEFRAME` — what to trade and at what base resolution (default `BTC/USDT`, `1m`)
- `USE_ALT_TIMEFRAME` / `ALT_TIMEFRAME_CCXT` — resample to a higher timeframe before computing the zigzag (default: on, 1h), matching the original's default `useAltTF=true, tf='60'`
- `USE_HEIKIN_ASHI` — off by default, matching the original
- `TARGET01_*` / `TARGET02_*` — trade size %, entry-window/TP/SL Fibonacci rates, same defaults as the original script's inputs
- `INITIAL_CAPITAL` — paper trading starting balance (default 500, matching the original)

## Run

```bash
python3 main.py
```

The bot polls every `POLL_SECONDS` (default 5s) for a newly closed base-timeframe
candle. On each new candle it:
1. Rebuilds the zigzag/x-a-b-c-d state from the trailing history window (`HISTORY_BARS`)
2. Detects harmonic patterns
3. Checks Target 1 / Target 2 entry & exit conditions against the latest closed bar
4. Opens/closes simulated positions in `PaperBroker`, logs them to `logs/trades.csv`
5. Sends a Telegram message for every entry and exit

## Important differences from the original / things to know

- **This trades on simulated paper positions only.** No real orders are placed
  anywhere. Wiring in a real exchange/broker (ccxt's authenticated trading
  methods, or a forex/stock broker SDK) is a separate, deliberate step — ask
  if/when you want that.
- **Pattern logic is ratio-based and narrow**, so on quiet/random price action
  you may go a long time without a single pattern match — that's expected
  behavior carried over from the original script, not a bug.
- **`pyramiding=0` is enforced**: a new entry signal for a slot (`target01_buy`,
  `target01_sell`, etc.) is ignored while a position in that slot is already open,
  exactly like the original strategy declaration.
- **History window**: each cycle replays the last `HISTORY_BARS` candles through
  the zigzag state machine from scratch. This is simpler and safer than trying
  to maintain incremental state across restarts, at the cost of some recomputation
  — fine at 1m/1h timeframes, but increase `HISTORY_BARS` if patterns seem to
  appear/disappear inconsistently near the edge of the window.
- **Binance public endpoints** are used for OHLCV only — no API key, no
  authentication, no rate-limit concerns beyond ccxt's built-in throttling.

## Files

- `config.py` — all settings (mirrors the original script's `input()` calls)
- `zigzag_engine.py` — zigzag state machine + all 16 harmonic pattern detectors + fib levels
- `data_feed.py` — Binance OHLCV fetch, Heikin-Ashi conversion, alt-timeframe resampling
- `paper_broker.py` — simulated position/equity tracking, trade logging to CSV
- `notifier.py` — Telegram alert sender
- `main.py` — the polling loop that ties it all together
