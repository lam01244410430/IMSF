"""P04-OPEN-03/04 proposals, not user-confirmed lifecycle decisions."""


class InventoryRequestError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code, self.code = status_code, code
        super().__init__()


def terminal_state(remaining, negative_kinds):
    if remaining > 0:
        return None
    kinds = set(negative_kinds)
    return (
        {
            "CONSUME": "CONSUMED",
            "DISPOSE": "DISCARDED",
            "RETURN": "RETURNED",
            "ADJUST_OUT": "ADJUSTED_OUT",
        }.get(next(iter(kinds)), "MIXED")
        if len(kinds) == 1
        else "MIXED"
    )
