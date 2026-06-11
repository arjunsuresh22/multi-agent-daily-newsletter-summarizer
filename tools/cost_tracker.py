import os
import sys

# Pricing per million tokens (USD)
_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
}

BUDGET_USD = float(os.getenv("RUN_BUDGET_USD", "0.50"))


class BudgetExceeded(Exception):
    pass


class CostTracker:
    """Singleton that tracks cumulative API spend for one run.py execution.
    Raises BudgetExceeded and kills the process if spend crosses RUN_BUDGET_USD.
    """
    _instance = None

    def __init__(self):
        self.total = 0.0

    @classmethod
    def get(cls) -> "CostTracker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    def add(self, model: str, input_tokens: int, output_tokens: int):
        pricing = _PRICING.get(model, {"input": 3.00, "output": 15.00})
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        self.total += cost
        print(f"  [budget] ${self.total:.4f} used of ${BUDGET_USD:.2f} limit")
        if self.total > BUDGET_USD:
            self._kill()

    def _kill(self):
        import subprocess
        print(f"\n  BUDGET EXCEEDED (${self.total:.4f} > ${BUDGET_USD:.2f}) — killing all run.py processes.")
        subprocess.run(["pkill", "-9", "-f", "run.py"], capture_output=True)
        raise BudgetExceeded(f"Spend ${self.total:.4f} exceeded budget ${BUDGET_USD:.2f}.")
