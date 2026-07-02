# Running the pipeline live (real models)

The repo is **stub-by-default** so it reproduces with no keys. This doc covers the
live path.

## 1. Keys

Two keys for generation, one optional for the finisher:

| Env var | Provider | Role | Cost |
|---|---|---|---|
| `NVIDIA_API_KEY` | NVIDIA NIM | solver / saboteur (Llama 3.1 70B) | free tier, ~40 RPM |
| `ANTHROPIC_API_KEY` | Anthropic | judge / triage (Claude Sonnet 4.6) | paid per token |
| `ADAPTION_API_KEY` | Adapt Labs | Stage E finisher | 300 pilot credits |

```bash
cp .env.example .env    # fill in the keys
pip install -r requirements.txt openai anthropic
export $(grep -v '^#' .env | xargs)   # or use python-dotenv
```

## 2. Confirm the NIM model slug

NIM catalog slugs change. Before a live run, open https://build.nvidia.com/models,
find your solver model, and copy its exact slug into `config.yaml`
(`providers.solver_model`). The default `meta/llama-3.1-70b-instruct` is a
placeholder that was current at authoring time.

Why Llama 3.1 70B and not a frontier model: the solver must **genuinely slip** on
mid-difficulty problems so Option 1 can harvest real corrections. A frontier model
one-shots the pilot problems and starves yield. If 70B's natural error rate is too
low during your run, drop to an 8B-class model (more errors, more malformed traces
to filter).

## 3. Generate

```bash
python -m calib.run generate --live
```

If a key is missing, that role silently falls back to stub (you'll see a `[warn]`),
so you can run solver-live / judge-stub or vice versa while iterating.

## 4. Tuning the difficulty band (the yield lever)

Option 1 needs problems in the middle band — hard enough that the solver slips,
easy enough that it recovers. Add seeds to `data/seeds/seeds.json` with a
`verifier` spec, run, and inspect `harness_report.json`:
- too many `self_correction: none` on solvable problems → problems too easy, raise difficulty
- too many discards / malformed → problems too hard or model too weak

## 5. Stage E — Adaptive Data (optional, spends credits)

See `docs/ADAPTIVE_DATA.md`. Always call the cost estimator and pilot on
`max_rows` before a full run — credits are not convertible to a row count from
public pricing.
