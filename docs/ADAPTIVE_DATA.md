# Stage E — Adaptive Data (Adapt Labs) as the finisher (Pending to be added!)

Adaptive Data is the **last-mile finisher/QA layer**, not the genuineness engine.
The pipeline produces verified `(instruction, thought, response)` triples; Adaptive
Data then normalizes length, enforces style, and grades quality.

## Why it's the finisher, not the generator

Adaptive Data (per its public docs) exposes a recipe-driven adapt pipeline:
`deduplication`, `prompt_rephrase`, `reasoning_traces`, plus run controls for
`length` (minimal/concise/detailed/extensive), `blueprint` (a system-prompt spec
layer), and `hallucination_mitigation`. It has **no verifier hook, no branch
sampling, no error-injection primitive, and no model selection**. So it cannot
*produce* genuine, verifier-grounded mid-generation self-correction — that logic
lives in this repo (Option 1's verifier loop). This is the expected
"falls short on a specific axis" finding for the reflections note.

Where it *does* help:
- `length: detailed|extensive` → directly counters the **compression** failure mode
- `blueprint` → encode the honest-completion / no-restatement spec as a system prompt
- `deduplication` → prompt-diversity hygiene at scale
- `grade_before → grade_after` → regression signal on the batch

## Credit budgeting (300 credits)

There is **no public $/credit price**; credits meter per-run × rows × recipes.
So 300 credits is **not** convertible to a row count from public info. Procedure:

1. `datasets.run(dataset_id, ..., estimate=True)` on the real recipe stack →
   read `estimatedCreditsConsumed`.
2. Pilot with `job_specification={"max_rows": 20..50}` to calibrate credits/row for
   *your* stack (reasoning_traces + detailed length + hallucination_mitigation
   costs more per row than a bare run).
3. Extrapolate with headroom. Treat 300 credits as **pilot-scale** — spend on the
   highest-value slice (the verified seed traces you expand yourself), not bulk.

## Sketch (pseudocode — requires the `adaption` SDK + key)

```python
from adaption import Adaption
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

# 1. estimate first — never blow credits by surprise
est = client.datasets.run(dataset_id, recipes={"reasoning_traces": True,
     "deduplication": True}, length="detailed", estimate=True)
print(est.estimatedCreditsConsumed, est.estimatedMinutes)

# 2. pilot on a few rows
client.datasets.run(dataset_id, job_specification={"max_rows": 20}, ...)

# 3. inspect grade_before -> grade_after, then scale within budget
```

Not wired into `calib/pipeline.py` by default so the demo never spends credits.
