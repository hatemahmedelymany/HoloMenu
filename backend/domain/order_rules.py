"""
Domain rules for order status transitions.

This file MUST NOT import any framework dependencies (FastAPI, HTTPException, etc.).
"""

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"confirmed", "cancelled", "expired"},
    "confirmed": {"cooking", "cancelled"},
    "cooking":   {"ready", "cancelled"},
    "ready":     {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "expired":   set(),
}


class InvalidStatusTransitionError(ValueError):
    """Raised when an order status change violates the domain transition rules."""
    pass


def assert_valid_transition(current: str, new: str) -> None:
    """Validate current to new state transition. Raises InvalidStatusTransitionError if invalid."""
    if new not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidStatusTransitionError(
            f"Cannot move order from '{current}' to '{new}'"
        )
