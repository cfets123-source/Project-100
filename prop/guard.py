"""Challenge rule guards (Topstep 50K Trading Combine style). All amounts in dollars.

Firm rules: profit target +$3,000; Maximum Loss Limit trails the end-of-day balance high by $2,000 and stops
at the starting balance; Daily Loss Limit $1,000. The bot uses tighter internal limits so it never reaches
the firm's: stop the day at -$800, and go flat for good when equity is within $400 of the trailing limit.
"""
from dataclasses import dataclass, field

TARGET = 3000.0
MLL = 2000.0
DAILY_STOP = 800.0
MLL_BUFFER = 400.0


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

    @property
    def floor(self):
        return min(self.start_balance, self.eod_high - MLL)

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def new_day(state, day, balance):
    """Call once per trading day before the open with the realized balance."""
    state.eod_high = max(state.eod_high, balance)  # balance at the start of a day = prior day's closing balance
    state.day, state.day_start_balance = day, balance
    if balance >= state.start_balance + TARGET:
        state.passed = state.finished = True
    if balance <= state.floor + MLL_BUFFER:
        state.finished = True
        state.halted_reason = "too close to the trailing loss limit"
    return state


def check(state, balance, open_pnl):
    """Return (allowed_to_trade, must_flatten, reason) for the current moment."""
    equity = balance + open_pnl
    if state.finished:
        return False, True, state.halted_reason or ("target reached" if state.passed else "finished")
    if equity >= state.start_balance + TARGET:
        state.passed = True
        return False, True, "profit target reached - stop and request the funded account"
    if equity <= state.floor + MLL_BUFFER:
        state.finished = True
        state.halted_reason = "within $%d of the trailing loss limit" % MLL_BUFFER
        return False, True, state.halted_reason
    if equity - state.day_start_balance <= -DAILY_STOP:
        state.halted_day = state.day
        return False, True, "daily stop (-$%d)" % DAILY_STOP
    if state.halted_day == state.day:
        return False, False, "stopped for today"
    return True, False, ""
