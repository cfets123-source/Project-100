"""Challenge rule guards (Topstep 50K Trading Combine style). All amounts in dollars.

Firm rules: profit target +$3,000; Maximum Loss Limit trails the end-of-day balance high by $2,000 and stops
at the starting balance; Daily Loss Limit $1,000. The bot uses tighter internal limits so it never reaches
the firm's: stop the day at -$800, and go flat for good when equity is within $400 of the trailing limit.
Limits scale with account size (50K/100K/150K). Consistency rule: the best single day must stay within
CONSISTENCY of the profit target, otherwise the firm raises the target to best_day / CONSISTENCY - so the bot
keeps trading instead of stopping at the original target. Funded/practice accounts have no profit target.
"""
import re
from dataclasses import dataclass, field, fields

TARGET = 3000.0
MLL = 2000.0
DAILY_STOP = 800.0
MLL_BUFFER = 400.0
CONSISTENCY = 0.50  # stricter than Topstep's published 55% so the bot never stops short of the real target
RULES = {50: (3000.0, 2000.0, 800.0, 400.0), 100: (6000.0, 3000.0, 1600.0, 600.0), 150: (9000.0, 4500.0, 2400.0, 900.0)}


def size_k(name):
    """Account size in $K from the account name (e.g. 50KTC-... -> 50); unknown sizes use the 50K rules."""
    m = re.search(r"(\d+)K", (name or "").upper())
    return int(m.group(1)) if m and int(m.group(1)) in RULES else 50


def kind_for(name):
    n = (name or "").upper()
    if "PRACTICE" in n:
        return "practice"
    if re.search(r"\d+KTC", n) or "COMBINE" in n:
        return "combine"
    return "funded"


def apply_rules(state, name, kind=None, overrides=None):
    """Set the limits for this account (from its name, or an explicit kind and per-firm overrides). Idempotent."""
    target, mll, daily, buffer = RULES[size_k(name)]
    state.kind = kind or kind_for(name)
    state.target = target if state.kind == "combine" else None
    if state.kind == "funded":
        buffer = 150.0 * size_k(name) / 50  # after a payout the cushion is small; a $400 buffer would end the account
    state.mll, state.daily_stop, state.mll_buffer = mll, daily, buffer
    for k, v in (overrides or {}).items():
        if k in ("target", "mll", "daily_stop", "mll_buffer", "consistency"):
            setattr(state, k, None if (k == "target" and state.kind != "combine") else float(v))
    return state


@dataclass
class ChallengeState:
    start_balance: float
    eod_high: float
    day: str = ""
    day_start_balance: float = 0.0
    halted_day: str = ""
    halted_reason: str = ""
    passed: bool = False
    finished: bool = False
    notes: list = field(default_factory=list)
    kind: str = "combine"
    target: float = TARGET
    mll: float = MLL
    daily_stop: float = DAILY_STOP
    mll_buffer: float = MLL_BUFFER
    best_day: float = 0.0
    consistency: float = CONSISTENCY

    @property
    def floor(self):
        return min(self.start_balance, self.eod_high - self.mll)

    def required_target(self, today_pnl=0.0):
        """Profit needed to pass, raised by the consistency rule; None when the account has no target."""
        if self.target is None:
            return None
        return max(self.target, max(self.best_day, today_pnl) / (self.consistency or CONSISTENCY))

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def new_day(state, day, balance):
    """Call once per trading day before the open with the realized balance."""
    if state.day and state.day != day:  # yesterday's realized result counts toward the consistency rule
        state.best_day = max(state.best_day, balance - state.day_start_balance)
    state.eod_high = max(state.eod_high, balance)  # balance at the start of a day = prior day's closing balance
    state.day, state.day_start_balance = day, balance
    need = state.required_target()
    if need is not None and balance >= state.start_balance + need:
        state.passed = state.finished = True
    if balance <= state.floor + state.mll_buffer:
        state.finished = True
        state.halted_reason = "too close to the trailing loss limit"
    return state


def check(state, balance, open_pnl):
    """Return (allowed_to_trade, must_flatten, reason) for the current moment."""
    equity = balance + open_pnl
    if state.finished:
        return False, True, state.halted_reason or ("target reached" if state.passed else "finished")
    need = state.required_target(equity - state.day_start_balance)
    if need is not None and equity >= state.start_balance + need:
        state.passed = True
        return False, True, "profit target reached - stop and request the funded account"
    if equity <= state.floor + state.mll_buffer:
        state.finished = True
        state.halted_reason = "within $%d of the trailing loss limit" % state.mll_buffer
        return False, True, state.halted_reason
    if equity - state.day_start_balance <= -state.daily_stop:
        state.halted_day = state.day
        return False, True, "daily stop (-$%d)" % state.daily_stop
    if state.halted_day == state.day:
        return False, False, "stopped for today"
    return True, False, ""
