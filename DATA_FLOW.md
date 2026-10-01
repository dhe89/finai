# FinAI Data & AI Flow

## Runtime

```text
/data/*.csv
     |
     v
finai_ui/data_service.py
     |
     +------------------------------+
     |                              |
     v                              v
Web pages                    Financial Intelligence Engine
                                   |
                                   v
                            Analysis Evidence
                                   |
                                   v
                         AI Financial Analyst
                                   |
                                   v
                              Verifier
                                   |
                                   v
                              Final Answer
```

## AI request flow

```text
Question
  |
  v
Semantic Planner
  |  understands goal/focus/comparisons/dimensions
  v
Python Financial Intelligence Engine
  |  retrieves and calculates facts
  |  MoM / YoY / year-start / target / trend
  |  P&L drivers / balance-sheet drivers
  |  product aggregation / relationships
  |  optional correlation
  v
Evidence Package
  |
  v
AI Analyst
  |  interprets evidence
  |  explains drivers and implications
  |  distinguishes fact vs consideration
  v
Deterministic Verifier
  |
  v
User-facing conclusion
```

Chat history is intentionally not sent to the analyst as prior user turns. Each request is isolated to the current question + its evidence package.
