# Running the pipeline live (real models)

The repo is **stub-by-default**, so it reproduces with no keys. This doc covers the
live path.

## 1. Keys

Two keys for generation, one optional for the finisher:

| Env var | Provider | Role | Model | Cost |
|---|---|---|---|---|
| `NVIDIA_API_KEY` | NVIDIA NIM | solver | Llama 3.1 70B (see `config.yaml`) | free tier, ~40 RPM |
| `NVIDIA_API_KEY` | NVIDIA NIM | saboteur | Llama 3.1 8B, deliberately weaker | same key, same tier |
| `ANTHROPIC_API_KEY` | Anthropic | judge / triage | Claude Sonnet 4.6 | paid per token |
| `ADAPTION_API_KEY` | Adapt Labs | Stage E finisher | n/a | 300 pilot credits |

```bash
cp .env.example .env      # fill in NVIDIA_API_KEY and ANTHROPIC_API_KEY
pip install -r requirements.txt
```

That's it: `requirements.txt` already pins `openai`, `anthropic`, and
`python-dotenv`, and `calib/run.py` calls `load_dotenv()` on startup, so `.env`
is picked up automatically. No manual `export` needed.

## 2. Confirm the NIM model slugs

NIM catalog slugs change. Before a live run, open https://build.nvidia.com/models,
find your solver and saboteur models, and copy their exact slugs into
`config.yaml` (`providers.solver_model`, `providers.saboteur_model`). The
defaults (`meta/llama-3.1-70b-instruct`, `meta/llama-3.1-8b-instruct`) are
placeholders that were current at authoring time.

The solver and saboteur are deliberately different models, not the same model
reused: the solver is strong enough to solve most pilot problems correctly on
the first try, and the saboteur is weaker specifically so it makes realistic,
in-distribution mistakes when asked to corrupt a trace (see §3 below).

## 3. Generate

```bash
python -m calib.run generate --live
```

If a key is missing, that role silently falls back to stub (you'll see a
`[warn]`), so you can run solver-live / judge-stub or vice versa while
iterating.

### How genuine corrections actually get produced

Two independent sources feed Option 1:

1. **Natural slips.** The solver's first attempt is checked against a local
   verifier. If it's genuinely wrong, the solver is shown its own mistake
   (never the answer) and repairs it live.
2. **Saboteur injection (the primary source in practice).** If the first
   attempt is already correct, there's nothing to naturally repair, so the
   saboteur is asked to corrupt the correct trace with one realistic error.
   The verifier confirms the injection actually broke the answer, then the
   solver is shown the corrupted trace blind (never told an error was
   planted) and asked to find and fix it. This is what makes yield possible
   even when a strong solver rarely slips on its own; there's no need to
   downgrade the solver model to force more mistakes.

Watch `data/samples/discards.jsonl` if injection yield seems low: the
saboteur's corruption quality can degrade on harder, more multi-step seeds,
occasionally producing an incoherent edit rather than one clean mistake. The
pipeline catches this safely (the sample is discarded, not silently admitted),
but it's worth knowing when tuning seed difficulty.

## 4. Tuning the difficulty band (the yield lever)

Since injection is the primary yield source, seed difficulty matters less for
*whether* you get corrections and more for *what kind* of natural slips you
occasionally harvest for free. Add seeds to `data/seeds/seeds.json` with a
`verifier` spec, run, and inspect `harness_report.json`'s `routes` and
`signals_fired`:
- lots of `clean_solutions` and few `dataset` entries: injection isn't
  producing enough verified corrections; check `discards.jsonl` for why
  (`llm_judge_fabricated`, `genuine_correction_missing`, or a failed
  injection retry are the usual culprits)
- too many discards or malformed responses in general: problems may be too
  hard for the current solver, or the saboteur's corruptions are too
  incoherent for the solver to meaningfully react to

## 5. Evaluating a batch (including ones you didn't generate)

```bash
python -m calib.run eval-batch FILE.jsonl              # black-box, keyless
python -m calib.run eval-batch FILE.jsonl --live        # + LLM judge layer
```

`eval-batch` is the deliverable harness: it runs on bare triples from any
source, tolerating missing or foreign metadata (unrecognized labels fall back
to "unknown" instead of crashing) and skipping malformed rows instead of
aborting the whole file. `--live` additionally wires in the LLM judge
(needs `ANTHROPIC_API_KEY`), which catches semantic issues, such as
compression and fabricated-sounding corrections, that the lexical detectors
alone can't. The default (no `--live`) stays fully keyless.

`data/samples/clean_solutions.jsonl` and `data/samples/discards.jsonl` are two
of the output pools `generate` produces alongside `dataset.jsonl` and
`negatives.jsonl`: `clean_solutions` holds verified-correct, no-drama solves
(kept separate so they don't dilute the self-correction dataset), and
`discards` holds anything that failed the gate, kept for audit instead of
being silently dropped.

## 6. Stage E, Adaptive Data (optional, spends credits)

See `docs/ADAPTIVE_DATA.md`. Always call the cost estimator and pilot on
`max_rows` before a full run: credits are not convertible to a row count from
public pricing.
