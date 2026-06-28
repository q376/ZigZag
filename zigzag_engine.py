"""
Direct Python port of the Pine Script's zigzag + harmonic pattern logic.

Pine reference (original script):

    zigzag() =>
        _isUp = close >= open
        _isDown = close <= open
        _direction = _isUp[1] and _isDown ? -1 : _isDown[1] and _isUp ? 1 : nz(_direction[1])
        _zigzag = _isUp[1] and _isDown and _direction[1] != -1 ? highest(2)
                : _isDown[1] and _isUp and _direction[1] != 1  ? lowest(2)
                : na

    x = valuewhen(sz, sz, 4)
    a = valuewhen(sz, sz, 3)
    b = valuewhen(sz, sz, 2)
    c = valuewhen(sz, sz, 1)
    d = valuewhen(sz, sz, 0)

    xab = abs(b-a)/abs(x-a)
    xad = abs(a-d)/abs(x-a)
    abc = abs(b-c)/abs(a-b)
    bcd = abs(c-d)/abs(b-c)

Important notes on semantics, since these are easy to get subtly wrong:

- This is NOT a percentage/ATR zigzag. It flips direction purely based on a
  reversal in candle color (close vs open), and a flip is only "confirmed"
  (i.e. produces a zigzag point) when the *previous* bar's direction matches
  what's expected for a turn. The pivot value itself is the highest/lowest of
  the last 2 bars (`highest(2)` / `lowest(2)`), not just the current bar.
- `valuewhen(series, value, occurrence)` returns the value of `value` the
  `occurrence`-th time `series` was non-na, counting backwards from (and
  including) the current bar. occurrence=0 means "most recent non-na value
  up to and including this bar".
- All of x/a/b/c/d, therefore, are step functions: they only change on bars
  where a new zigzag pivot appears, and otherwise hold their last value
  (this mirrors valuewhen's "holds until next match" behavior).
"""

from dataclasses import dataclass, field
from typing import Optional, Deque
from collections import deque


@dataclass
class ZigZagState:
    """Rolling state needed to compute the zigzag incrementally, bar by bar."""
    prev_close: Optional[float] = None
    prev_open: Optional[float] = None
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    prev_is_up: Optional[bool] = None
    prev_is_down: Optional[bool] = None
    direction: int = 0  # nz() default -> 0 until first flip

    # last 2 bars' highs/lows, for highest(2)/lowest(2)
    last2_high: Deque[float] = field(default_factory=lambda: deque(maxlen=2))
    last2_low: Deque[float] = field(default_factory=lambda: deque(maxlen=2))

    # zigzag pivot history (only non-na points), most recent last
    pivots: Deque[float] = field(default_factory=lambda: deque(maxlen=10))


def update_zigzag(state: ZigZagState, o: float, h: float, l: float, c: float) -> Optional[float]:
    """
    Feed one new bar (open/high/low/close) into the zigzag state machine.
    Returns the new zigzag pivot value for this bar, or None if no pivot formed
    (equivalent to Pine's `na`).

    This must be called once per *closed* bar, in chronological order.
    """
    is_up = c >= o
    is_down = c <= o

    state.last2_high.append(h)
    state.last2_low.append(l)

    pivot = None

    if state.prev_is_up is not None:
        # _direction = _isUp[1] and _isDown ? -1 : _isDown[1] and _isUp ? 1 : nz(_direction[1])
        if state.prev_is_up and is_down:
            new_direction = -1
        elif state.prev_is_down and is_up:
            new_direction = 1
        else:
            new_direction = state.direction  # nz(_direction[1])

        # _zigzag = _isUp[1] and _isDown and _direction[1] != -1 ? highest(2)
        #         : _isDown[1] and _isUp and _direction[1] != 1  ? lowest(2)
        #         : na
        # NOTE: _direction[1] is the direction *before* this bar's update.
        prev_direction = state.direction
        if state.prev_is_up and is_down and prev_direction != -1:
            pivot = max(state.last2_high) if len(state.last2_high) == 2 else h
        elif state.prev_is_down and is_up and prev_direction != 1:
            pivot = min(state.last2_low) if len(state.last2_low) == 2 else l

        state.direction = new_direction

    # roll state forward
    state.prev_is_up = is_up
    state.prev_is_down = is_down
    state.prev_close = c
    state.prev_open = o
    state.prev_high = h
    state.prev_low = l

    if pivot is not None:
        state.pivots.append(pivot)

    return pivot


def get_xabcd(state: ZigZagState):
    """
    Equivalent of x/a/b/c/d via valuewhen(sz, sz, n).
    state.pivots holds non-na zigzag values in chronological order (oldest -> newest).
    valuewhen(sz, sz, 0) = most recent pivot, ..., valuewhen(sz, sz, 4) = 5th most recent.

    Returns (x, a, b, c, d) or None if fewer than 5 pivots exist yet.
    """
    if len(state.pivots) < 5:
        return None
    p = list(state.pivots)[-5:]   # 5 most recent, oldest->newest
    x, a, b, c, d = p[0], p[1], p[2], p[3], p[4]
    return x, a, b, c, d


# ---------------------------------------------------------------------------
# Harmonic pattern ratio checks - direct port of each isXxx(_mode) function.
# _mode: 1 = bullish ("d < c"), -1 = bearish ("d > c")
# ---------------------------------------------------------------------------

def _ratios(x, a, b, c, d):
    xab = abs(b - a) / abs(x - a) if (x - a) != 0 else float("inf")
    xad = abs(a - d) / abs(x - a) if (x - a) != 0 else float("inf")
    abc = abs(b - c) / abs(a - b) if (a - b) != 0 else float("inf")
    bcd = abs(c - d) / abs(b - c) if (b - c) != 0 else float("inf")
    return xab, xad, abc, bcd


def _dir_ok(mode, c, d):
    return d < c if mode == 1 else d > c


def isBat(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.382 <= xab <= 0.5 and 0.382 <= abc <= 0.886 and
            1.618 <= bcd <= 2.618 and xad <= 1.000 and _dir_ok(mode, c, d))


def isAntiBat(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.500 <= xab <= 0.886 and 1.000 <= abc <= 2.618 and
            1.618 <= bcd <= 2.618 and 0.886 <= xad <= 1.000 and _dir_ok(mode, c, d))


def isAltBat(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (xab <= 0.382 and 0.382 <= abc <= 0.886 and
            2.0 <= bcd <= 3.618 and xad <= 1.13 and _dir_ok(mode, c, d))


def isButterfly(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (xab <= 0.786 and 0.382 <= abc <= 0.886 and
            1.618 <= bcd <= 2.618 and 1.27 <= xad <= 1.618 and _dir_ok(mode, c, d))


def isAntiButterfly(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.236 <= xab <= 0.886 and 1.130 <= abc <= 2.618 and
            1.000 <= bcd <= 1.382 and 0.500 <= xad <= 0.886 and _dir_ok(mode, c, d))


def isABCD(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.382 <= abc <= 0.886 and 1.13 <= bcd <= 2.618 and _dir_ok(mode, c, d))


def isGartley(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.5 <= xab <= 0.618 and 0.382 <= abc <= 0.886 and
            1.13 <= bcd <= 2.618 and 0.75 <= xad <= 0.875 and _dir_ok(mode, c, d))


def isAntiGartley(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.500 <= xab <= 0.886 and 1.000 <= abc <= 2.618 and
            1.500 <= bcd <= 5.000 and 1.000 <= xad <= 5.000 and _dir_ok(mode, c, d))


def isCrab(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.500 <= xab <= 0.875 and 0.382 <= abc <= 0.886 and
            2.000 <= bcd <= 5.000 and 1.382 <= xad <= 5.000 and _dir_ok(mode, c, d))


def isAntiCrab(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.250 <= xab <= 0.500 and 1.130 <= abc <= 2.618 and
            1.618 <= bcd <= 2.618 and 0.500 <= xad <= 0.750 and _dir_ok(mode, c, d))


def isShark(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.500 <= xab <= 0.875 and 1.130 <= abc <= 1.618 and
            1.270 <= bcd <= 2.240 and 0.886 <= xad <= 1.130 and _dir_ok(mode, c, d))


def isAntiShark(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.382 <= xab <= 0.875 and 0.500 <= abc <= 1.000 and
            1.250 <= bcd <= 2.618 and 0.500 <= xad <= 1.250 and _dir_ok(mode, c, d))


def is5o(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (1.13 <= xab <= 1.618 and 1.618 <= abc <= 2.24 and
            0.5 <= bcd <= 0.625 and 0.0 <= xad <= 0.236 and _dir_ok(mode, c, d))


def isWolf(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (1.27 <= xab <= 1.618 and 0 <= abc <= 5 and
            1.27 <= bcd <= 1.618 and 0.0 <= xad <= 5 and _dir_ok(mode, c, d))


def isHnS(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (2.0 <= xab <= 10 and 0.90 <= abc <= 1.1 and
            0.236 <= bcd <= 0.88 and 0.90 <= xad <= 1.1 and _dir_ok(mode, c, d))


def isConTria(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (0.382 <= xab <= 0.618 and 0.382 <= abc <= 0.618 and
            0.382 <= bcd <= 0.618 and 0.236 <= xad <= 0.764 and _dir_ok(mode, c, d))


def isExpTria(x, a, b, c, d, mode):
    xab, xad, abc, bcd = _ratios(x, a, b, c, d)
    return (1.236 <= xab <= 1.618 and 1.000 <= abc <= 1.618 and
            1.236 <= bcd <= 2.000 and 2.000 <= xad <= 2.236 and _dir_ok(mode, c, d))


PATTERN_FUNCS = {
    "ABCD": isABCD,
    "Bat": isBat,
    "AntiBat": isAntiBat,
    "AltBat": isAltBat,
    "Butterfly": isButterfly,
    "AntiButterfly": isAntiButterfly,
    "Gartley": isGartley,
    "AntiGartley": isAntiGartley,
    "Crab": isCrab,
    "AntiCrab": isAntiCrab,
    "Shark": isShark,
    "AntiShark": isAntiShark,
    "5-O": is5o,
    "Wolf Wave": isWolf,
    "Head and Shoulders": isHnS,
    "Contracting Triangle": isConTria,
    "Expanding Triangle": isExpTria,
}

# Patterns that use _xad <= upper bound only loosely in the original Pine code
# (isBat has a redundant double-condition `xad <= 0.618 and xad <= 1.000`,
# which simplifies to just `xad <= 1.000` -- already applied above).


def detect_patterns(x, a, b, c, d, mode):
    """Return list of pattern names that match for the given mode (1=bull, -1=bear)."""
    hits = []
    for name, fn in PATTERN_FUNCS.items():
        try:
            if fn(x, a, b, c, d, mode):
                hits.append(name)
        except ZeroDivisionError:
            continue
    return hits


def fib_levels(c: float, d: float):
    """
    Port of:
        fib_range = abs(d-c)
        f_last_fib(_rate) => d > c ? d-(fib_range*_rate) : d+(fib_range*_rate)

    Returns a dict of rate -> price level, plus a callable for arbitrary rates.
    """
    fib_range = abs(d - c)

    def f_last_fib(rate: float) -> float:
        return d - (fib_range * rate) if d > c else d + (fib_range * rate)

    levels = {
        "0.000": f_last_fib(0.000),
        "0.236": f_last_fib(0.236),
        "0.382": f_last_fib(0.382),
        "0.500": f_last_fib(0.500),
        "0.618": f_last_fib(0.618),
        "0.764": f_last_fib(0.764),
        "1.000": f_last_fib(1.000),
    }
    return levels, f_last_fib
