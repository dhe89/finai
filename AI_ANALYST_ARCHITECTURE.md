# FinAI AI Analyst Architecture

## Why the architecture changed

The previous prototype relied on a fixed semantic intent layer. That approach required new intent rules and dictionaries whenever users asked a new type of financial question.

The new architecture treats the LLM as a **semantic analysis planner and analyst**, while Python remains the deterministic financial calculation layer.

## Components

### `finai_ui/ai/planner.py`

Understands the current question and creates an analysis plan dynamically:

- scope
- analytical goal
- focus
- comparison requirements
- dimensions
- drill-down requirement
- relationship analysis
- trend analysis
- target analysis
- correlation requirement
- data requirements

It does not use a fixed intent dictionary.

### `finai_ui/financial_engine.py`

Deterministic source of financial facts:

- current snapshot
- MoM
- YoY
- year-start comparison
- target gap and achievement
- 12-month trend
- P&L line-item changes
- balance-sheet drivers
- loan/investment/DPK/funding product aggregation
- optional Pearson correlation

### `finai_ui/ai/analyst.py`

Turns the evidence into a useful financial analysis. It is explicitly allowed to:

- explain why a metric moved when evidence supports the explanation
- connect related financial statements
- discuss implications
- provide considerations
- use carefully qualified assumptions

It must not invent facts or claim causality without support.

### `finai_ui/ai/verifier.py`

Deterministic final guardrail:

- rejects empty output
- rejects visible internal reasoning/meta text
- rejects obvious unsupported financial numbers
- supplies a safe fallback when the analyst model fails

### `finai_ui/ai/openrouter.py`

Low-level provider client only. It is not the financial reasoning layer.

## Evidence levels

The analyst should distinguish:

1. **Fact** — directly present in data.
2. **Derived fact** — calculated by Python.
3. **Analytical interpretation** — relationship supported by available data.
4. **Consideration/assumption** — plausible implication explicitly qualified as such.

## Example

Question:

> Kenapa laba September turun padahal pendapatan naik?

The planner can dynamically request:

- current profit/revenue
- MoM and YoY
- target
- P&L driver changes
- margin/trend context

Python calculates the values. The analyst then explains which revenue and expense movements support the observed profit movement, and identifies what should be monitored.

No new `PROFIT_DIAGNOSIS` intent is required.

## Future extension

New analytical capabilities should normally be added to `financial_engine.py` as reusable tools rather than adding new question intents.

Examples:

- margin decomposition
- liquidity analysis
- asset quality analysis
- funding mix analysis
- forecast
- scenario analysis
- concentration analysis
