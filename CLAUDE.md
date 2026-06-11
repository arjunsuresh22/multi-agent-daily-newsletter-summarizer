# Daily Newsletter Summarizer

## Run
```bash
python3 -u run.py            # last 1 day, $0.50 budget
python3 -u run.py --days 3   # last 3 days
python3 -u run.py --budget 1.00  # raise budget to $1.00
```

## Budget enforcement
Every API call in the pipeline updates a live cost tracker.
If cumulative spend exceeds $0.50 (default), the tracker:
1. Prints the overage
2. Kills all run.py processes via `pkill -9 -f run.py`
3. Raises `BudgetExceeded` — no silent runaway spend

Override with `--budget N` or env var `RUN_BUDGET_USD=N`.

## Rules
- NEVER run automatically. Only run when the user explicitly asks.
- NEVER schedule or set up cron jobs without explicit instruction.
- Always give a token/cost estimate and wait for explicit approval before any LLM task.
- If a run is stuck or taking too long: `kill -9 $(pgrep -f run.py)`

## Priority sources (email)
a16z, Lenny's Newsletter, Chamath Palihapitiya, Nate's Substack,
Alpha Signal, Aishwarya Srinivasan, Semi-Analysis

## YouTube channels
Lenny's Podcast: UC6t1O76G0jYXOAoYCm153dA

## Output
`summaries/YYYY-MM-DD_digest.md` — one file per day, priority sources first.

## Feedback / calibration
```bash
python3 feedback.py "sender@example.com" "your feedback here"
```
