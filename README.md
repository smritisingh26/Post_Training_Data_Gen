# Calibration Pilot

A generation pipeline + eval harness for a post-training dataset that teaches a
long-context reasoning model **genuine mid-generation self-correction** — while
avoiding the two disqualifying failure modes: **compressed answers** and
**theatrical self-correction** (fabricating an error to "catch").

The full design rationale is in [`DESIGN.md`](DESIGN.md). Two-page writeup and
one-page reflections are in [`docs/`](docs/).

---

## Quickstart (keyless, reproducible — no API keys needed)

```bash
pip install -r requirements.txt          # sympy + pyyaml are enough for this
python -m calib.run generate             # runs the whole pipeline in STUB mode
python tests/test_all.py                 # 10 unit tests
```

`generate` runs the entire river — triage → route → generate (Opt 1/2/3) →
harness gate → serialize — using deterministic replay fixtures, so you get
identical output every time with no network. **The SymPy verifier runs for real
even in stub mode**, so Option-1 corrections are genuinely grounded.

Outputs land in `data/samples/`:
- `dataset.jsonl` — admitted samples, **public schema** (triple + labels, no provenance)
- `dataset.full.jsonl` — same, **with white-box provenance** (verifier verdicts, branch history)
- `negatives.jsonl` — labeled **theatrical** hard-negatives (routed here, not discarded)
- `harness_report.json` — per-sample gate decisions + triage log

## Run the black-box harness on ANY batch

The harness is the deliverable that must run on batches you did **not** generate,
on bare triples with no provenance:

```bash
python -m calib.run eval-batch data/samples/given_as_batch.jsonl
```

`given_as_batch.jsonl` is the **30 original provided samples** re-expressed as a
foreign batch. Running the harness on it independently reproduces the EDA's two
critical findings — `fabricated_rigor` fires on exactly the 4 Riemann-Hypothesis
records, and theatrical/filler correction is pervasive (see
`data/samples/given_batch_harness_demo.json`). This is the before/after evidence:
the given data mostly fails the gate; the pilot's own output passes it.

## Live run (real models)

See [`docs/REAL_RUN_INSTRUCTIONS.md`](docs/REAL_RUN_INSTRUCTIONS.md). In short:
```bash
cp .env.example .env      # fill in NVIDIA_API_KEY + ANTHROPIC_API_KEY
python -m calib.run generate --live
```
Solver = Llama 3.1 70B on NVIDIA NIM (free tier); judge/triage = Claude Sonnet 4.6.
Confirm the NIM model slug on your dashboard first (see config.yaml note).

---

## Architecture (one river, a fork, a shared gate)

```
prompts → TRIAGE (registry + LLM) → ROUTE ┬ verifiable-solvable → Opt1 branch-and-repair
                                          ├ impossible/ill-posed → Opt2 honest-completion
                                          └ (yield/negatives)    → Opt3 injection
                                            → HARNESS = admission gate → dataset / negatives / discard
                                              → (Stage E: Adaptive Data finish, optional)
```

| Component | File | Role |
|---|---|---|
| Schema | `calib/schema.py` | the triple + metadata; public vs full (provenance) views |
| Verifier | `calib/verifier.py` | **local SymPy** ground-truth signal (no network) |
| Triage | `calib/triage.py` | class/verifiable/obstruction; registry + LLM |
| Providers | `calib/providers/` | NIM + Anthropic + **stub** backends (stub by default) |
| Opt 1 | `calib/tracks/opt1_branch_repair.py` | verifier-gated genuine correction (the spine) |
| Opt 2 | `calib/tracks/opt2_honest_completion.py` | honest non-completion + abstention |
| Opt 3 | `calib/tracks/opt3_injection.py` | labeled theatrical negatives + yield top-up |
| Harness | `calib/harness.py` | black-box detectors + admission gate |
| Orchestrator | `calib/pipeline.py` | Stage A→D wiring |
| CLI | `calib/run.py` | `generate`, `eval-batch` |

## Honest accounting

Every harness detector measures **causal load-bearing-ness** and lexical tells as
a **proxy** for "genuine vs. theatrical" — a distinction with no ground-truth
metric. The proxy is strongest for Option 1 (the verifier re-check is nearly a
real metric) and weaker for Options 2/3. And none of it measures the true target,
**downstream training impact**, which no 48-hour eval can. See the reflections note.
