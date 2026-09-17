from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def scan(self, universe: list[str]) -> list[str]:
        """Return candidate symbols from a universe."""

    @abstractmethod
    def qualify(self, symbol: str, context: dict) -> bool:
        """Hard filter: does this candidate meet strategy preconditions?"""

    @abstractmethod
    def generate_signal(self, symbol: str, context: dict) -> dict | None:
        """Return a signal dict (direction, score, thesis) or None."""

    @abstractmethod
    def calculate_entry(self, symbol: str, context: dict) -> float: ...

    @abstractmethod
    def calculate_stop(self, symbol: str, context: dict) -> float: ...

    @abstractmethod
    def calculate_target(self, symbol: str, context: dict) -> float: ...

    @abstractmethod
    def calculate_position_size(self, entry: float, stop: float, risk_dollars: float) -> float:
        return risk_dollars / abs(entry - stop) if entry != stop else 0.0

    @abstractmethod
    def calculate_expected_rr(self, entry: float, stop: float, target: float) -> float:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        return reward / risk if risk else 0.0

    @abstractmethod
    def invalidate(self, symbol: str, context: dict) -> bool:
        """Has the setup thesis been invalidated?"""

    @abstractmethod
    def exit_rules(self, position: dict, context: dict) -> str | None:
        """Return exit reason string if an exit condition is met, else None."""
