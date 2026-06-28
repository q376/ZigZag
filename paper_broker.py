"""
Paper-trading broker: simulates what TradingView's strategy engine did automatically
(`strategy.entry`, `strategy.close`, equity tracking, pyramiding=0) since we no longer
have that engine once we're running standalone.

Rules mirrored from the original `strategy(...)` declaration and entry/close calls:
- pyramiding=0: at most one open position per "slot" (target01 / target02) at a time;
  a new entry signal is ignored while a position in that slot is already open.
- qty is computed as (trade_size_pct * equity / 100) / price, same formula as the
  original script's manual qty calculation (since explicit qty= means units, not %).
- Closing a position realizes P&L into equity immediately (mirrors strategy.close).
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
import csv
import os
import time

import config


@dataclass
class Position:
    slot: str            # "target01_buy" / "target01_sell" / "target02_buy" / "target02_sell"
    side: str             # "long" or "short"
    qty: float
    entry_price: float
    entry_time: float
    comment: str = ""


class PaperBroker:
    def __init__(self, initial_capital: float, trades_csv: str = config.TRADES_CSV):
        self.equity = initial_capital
        self.initial_capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades_csv = trades_csv
        self._ensure_csv()

    def _ensure_csv(self):
        os.makedirs(os.path.dirname(self.trades_csv), exist_ok=True)
        if not os.path.exists(self.trades_csv):
            with open(self.trades_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "slot", "side", "comment", "qty", "entry_price", "exit_price",
                    "entry_time", "exit_time", "pnl", "equity_after"
                ])

    def has_open(self, slot: str) -> bool:
        return slot in self.positions

    def open_position(self, slot: str, side: str, trade_size_pct: float,
                       price: float, comment: str = "") -> Optional[Position]:
        """
        Mirrors:
            qty = (trade_size_pct * equity / 100) / price
            strategy.entry(slot, long=..., qty=qty, when=entry_condition)
        Respects pyramiding=0: refuses if a position is already open in this slot.
        """
        if self.has_open(slot):
            return None  # pyramiding=0 -> ignore new entries while one is open
        if self.equity <= 0 or price <= 0:
            return None

        qty = (trade_size_pct * self.equity / 100.0) / price
        pos = Position(slot=slot, side=side, qty=qty, entry_price=price,
                        entry_time=time.time(), comment=comment)
        self.positions[slot] = pos
        return pos

    def close_position(self, slot: str, price: float) -> Optional[float]:
        """
        Mirrors strategy.close(slot, when=close_condition).
        Realizes P&L into equity and removes the position. Returns realized P&L,
        or None if there was nothing open.
        """
        pos = self.positions.pop(slot, None)
        if pos is None:
            return None

        if pos.side == "long":
            pnl = (price - pos.entry_price) * pos.qty
        else:  # short
            pnl = (pos.entry_price - price) * pos.qty

        self.equity += pnl
        self._log_trade(pos, price, pnl)
        return pnl

    def _log_trade(self, pos: Position, exit_price: float, pnl: float):
        with open(self.trades_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                pos.slot, pos.side, pos.comment, f"{pos.qty:.8f}",
                f"{pos.entry_price:.2f}", f"{exit_price:.2f}",
                pos.entry_time, time.time(), f"{pnl:.2f}", f"{self.equity:.2f}"
            ])

    def open_positions_summary(self) -> str:
        if not self.positions:
            return "No open positions."
        lines = []
        for slot, pos in self.positions.items():
            lines.append(f"{slot}: {pos.side} {pos.qty:.6f} @ {pos.entry_price:.2f}")
        return "\n".join(lines)
