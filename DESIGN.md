# Calibration Pilot — Design Document

*Post-training dataset teaching a long-context reasoning model to produce long-form,
fully-explained reasoning with genuine mid-generation self-correction.*

---

## 0. The problem in one line

Produce `(instruction, thought, response)` triples where any self-correction is **genuine**
(a real error, really caught, really fixed) and never **theatrical** (an error fabricated so it
can be "caught"), where explanations **explain** rather than compress, and where **impossible
problems are honestly admitted** rather than fabricated through.

Two named failure modes must not appear:
1. **Compressed answers** — summarize rather than explain.
2. **Theatrical self-correction** — model invents an error to catch. Disqualifies a batch.

Most-important criterion (from the brief): how well the data helps the model **use context and
reason efficiently** — i.e. this is largely a **non-verifiable-reward** problem.

---

## 1. What the provided data told us (EDA, verified)

30 records, 4 fields (`id`, `instruction`, `thought`, `response`), **6 unique prompt families**,
each sampled 4–6×. `thought` ≈ 2× the length of `response`.

Verified findings:

| # | Finding | Level | Count |
|---|---|---|---|
| 1 | **Genuine self-correction absent from the output** (target behavior appears zero times) | Critical | 30/30 |
| 2 | **Fabricated rigor on unanswerable prompts** (strict) — RH 4/4 fabricate a proof; SGD ~3/5 prove a strawman + self-certify | Critical | 7/30 (~13/30 incl. soft overclaims) |
| 3 | **Hidden/scrubbed self-correction** — wrestling lives in `thought`, `response` is laundered clean | High | 22/30 |
| 4 | **Filler "self-correction"** — "Actually…/Wait…" that catches no real error | High | ~29/30 |
| 5 | **Trace–answer inconsistency** — `thought` admits doubt, `response` stamps ∎ | High | 4–6/30 |
| 6 | Rigor self-certification ("every step is rigorous", "provably") | Medium | 9/30 |
| 7 | Meta/scratchpad leakage into `response` (one literal "*Internal scratchpad notes:*") | Medium | 6/30 |
| 8 | Monotone prompt style / low diversity (6 templates, one register) | Medium | 30/30 |
| 9 | Compression — hard step hand-waved to "the literature"/"numerically known" | Medium | high-signal, small n |

**Key asymmetry (drives the whole strategy):** on 3-body (impossible), the model honestly says
"no closed-form solution exists" in 4/6 — but on RH (impossible) it fabricates a proof 4/4. Same
model, same register. So the failure is **not** "can't say I-don't-know"; it's that the
"prove the famous open problem" framing overrides calibration. The RH `thought` literally admits
impossibility, then the `response` deletes that admission.

**Reclassification caught during EDA:** Navier–Stokes prompts *look* impossible (general N–S is a
Millennium problem) but the actual task — fully-developed power-law slit flow — is a **solvable
reduction**, and the model solves it correctly. So "looks impossible" ≠ "is impossible"; the
triage step (below) must judge the *actual* task, not the grand framing.

---

## 2. Core strategic decisions

### 2.1 Genuineness cannot be prompted — it must be structurally produced
Asking a model to "reason and check yourself" is the *theater generator* — it is exactly what
produced the fabricated corrections in the samples, and matches Huang et al. (ICLR 2024): LLMs
cannot reliably self-correct **without external feedback**. Therefore every genuine correction in
our data must be anchored to an **external correctness signal**, not to a self-critique prompt.

### 2.2 Verifiability is a scaffold, not the reward
The target property (genuine, non-theatrical, well-explained reasoning) is **non-verifiable** —
there is no unit test for "this explanation is genuine." We use verifiable domains **only because
they are the one setting where we can manufacture a genuine error cheaply and prove it was
genuine**. The behavior is then meant to generalize to non-verifiable prose. Consequence: the
final dataset contains **both** verifiable-domain traces (quality anchor / validation) and
non-verifiable + derivational traces including the given prompts (where the product actually
lives). State this framing explicitly in the writeup.

### 2.3 Honest non-completion is a first-class target, generated on purpose
Fabricated rigor was the critical EDA failure, and AbstentionBench (Kirichenko et al., 2025) shows
reasoning fine-tuning **degrades** abstention by ~24% on average. So if we train self-correction
without deliberately generating honest-non-completion data, we make the critical failure **worse**.
Genuine mid-trace correction ("that step doesn't hold — fix it") and honest non-completion ("that
step *can't* hold, and that's fundamental") are the **same calibration skill** aimed at a
recoverable vs. an unrecoverable obstacle.

### 2.4 Efficiency / length is a target, not a free variable
"Long-form" has an upper bound set by "every token earns its place." A 15k-token ramble that
self-corrects is still a failure. Length is curated to difficulty, not maximized.

---

## 3. The pipeline — ONE river, a fork, a shared gate

The three "options" are **not three pipelines**. They are three generation strategies sharing one
spine, differentiated by a router, rejoining at one admission gate.

```
                         ┌─────────────────────────────────────────────┐
   prompts ──▶  STAGE A: TRIAGE (shared, runs once)                    │
                  stamps: solvable | impossible | ill-posed            │
                          (+ verifiable | non-verifiable for solvable) │
                          (+ obstruction note for impossible)          │
                         └──────────────┬──────────────────────────────┘
                                        │ STAGE B: ROUTE
             ┌──────────────────────────┼───────────────────────────┐
             ▼                          ▼                           ▼
   verifiable-solvable          impossible / ill-posed      solvable but
             │                          │                   correction-starved
   ┌─────────▼─────────┐      ┌─────────▼─────────┐      ┌────────▼──────────┐
   │ OPTION 1          │      │ OPTION 2          │      │ OPTION 3 (booster)│
   │ Verifier-gated    │      │ Honest-completion │      │ Adversarial error │
   │ branch-and-repair │      │ + abstention      │      │ injection; feeds  │
   │ (the SPINE)       │      │ (2nd pillar)      │      │ ON option-1 traces│
   └─────────┬─────────┘      └─────────┬─────────┘      └────────┬──────────┘
             └──────────────────────────┼───────────────────────┘
                                        ▼
              STAGE D: HARNESS = ADMISSION GATE (shared, runs on EVERY candidate)
                 pass ▶ dataset  |  clean-theatrical ▶ labeled-negatives pile  |  else ▶ discard
                                        ▼
              STAGE E: ADAPTIVE DATA FINISH (length normalize, blueprint style, grade)
                                        ▼
                          (instruction, thought, response) + metadata  ──▶  DATASET
```

All three tracks emit the **same schema**. Option 3 is a *booster* that consumes Option 1 outputs,
not an independent problem source.

---

## 4. The three tracks

### Option 1 — Verifier-Gated Branch-and-Repair (the spine)
- **Setup:** pool of problems with machine-checkable ground truth (code+tests, SymPy, SAT/SMT,
  numeric eval); a warm-temperature generator that genuinely slips; an orchestration loop:
  generate → verify step-by-step → branch from first confirmed-wrong step → repair → re-verify.
- **Genuineness:** the error is **discovered, not authored** — only verifier-confirmed real errors
  enter the trace. Control lives in **when the loop branches**, not in any prompt.
- **Prompts:** almost entirely **additional** (verifiable domains; the given prompts are mostly
  not verifiable). This division of labor is a feature — say so.
- **Adaptive fit:** genuineness engine is ours; Adaptive Data is the **finisher** (length,
  blueprint, grade).
- **Impossibility:** uses the triage stamp **defensively** — impossible/ill-posed routed OUT.
- **Agentic?** Lightly — orchestrated tool-augmented loop, not an autonomous planner.

### Option 2 — Difficulty-Tiered Honest-Completion (2nd pillar)
- **Setup:** curated set across solvable / impossible / ill-posed, each with a **gold
  `problem_class` label**; the triage classifier; a generator that reasons toward *and admits*
  impossibility.
- **Genuineness (of calibration):** expressed confidence checked against the **gold label** — if
  label=impossible and response claims a proof, caught mechanically.
- **Prompts:** heavily the **given** prompts (RH, 3-body = impossible exemplars; the good 3-body
  samples already show the target) **plus additions**.
- **Adaptive fit:** `blueprint` encodes the honest-completion spec; `length` stops collapse to a
  one-line refusal. Gold labels + grading are ours.
- **Impossibility:** this is the **star** — see §5.
- **Agentic?** The **triage** step is the agentic part (esp. retrieval/probe variant); generation
  is guided single-pass.

### Option 3 — Adversarial Error-Injection w/ Consequence Propagation (supplement)
- **Setup:** three roles — **saboteur** (weaker checkpoint injects a realistic error),
  **solver** (reasons forward from corrupted step), **faithfulness judge** (confirms recovery is
  load-bearing). Verifier confirms the injected error truly breaks the answer.
- **Genuineness:** via **consequence propagation** — the error must have downstream symptoms the
  solver hits organically (negative variance, dimension mismatch, failing test). **Biggest
  caveat:** most prone to *becoming* theater if the planted error is too clean/flagged; gated hard
  by the judge; **supplement, never spine**.
- **Prompts:** additional/derived (inject into already-correct traces).
- **Adaptive fit:** least dependent; loop is entirely ours.
- **Impossibility:** can manufacture **over-abstention negatives** (claim unprovable when solvable)
  to stress Option 2's harness.
- **Agentic?** **Most agentic** — genuine multi-role (saboteur ↔ solver ↔ judge). Flag as the
  "innovative approach."

---

## 5. The triage classifier — highest-leverage shared component ("the nice sub-problem")

Runs once, up front (Stage A). Stamps `solvable | impossible | ill-posed`, plus
`verifiable | non-verifiable` for solvables, plus an **obstruction note** for impossibles.

- **Build tiers (cheap→rich):** (a) classification prompt to a strong model — "solvable in closed
  form / provable / well-posed? if not, name the obstruction"; (b) + **retrieval** to catch
  *known* open/impossible problems (RH, general 3-body, squaring the circle); (c) a small **triage
  agent** that runs a short solvability probe and watches for a known barrier.
- **Two jobs for the stamp:** (1) **route** to the right track; (2) **set target behavior + gold
  label** for the harness.
- **Enforcing admission of impossibility (the elegant bit):** inject the triage output into the
  generator's context — the generator is *told* `class=impossible, obstruction=…`, making honest
  admission the path of least resistance instead of something it must discover under pressure.
- **Must judge the actual task, not the framing** (the Navier–Stokes trap).
- **Measure it:** hand-audit a sample of labels; report classifier error rate in the writeup (it
  propagates everywhere).

---

## 6. Models

- **Generator / solver:** strong long-CoT reasoning model (frontier API), **warm temperature** so
  it slips naturally → real errors to catch.
- **Saboteur (Opt 3):** deliberately **weaker** checkpoint → realistic, in-distribution mistakes.
- **Judge / labeler:** strong model **+ deterministic verifier** — verifier does the grounding;
  judge handles non-verifiable calls (compressed? correction load-bearing?).
- Adaptive Data does **not** expose model choice → genuineness-producing calls must be our own API
  calls. (Reflections-note finding.)

---

## 7. Metadata schema (per triple)

Richer than a single boolean so one dataset carries positives, hard negatives, and calibration
pairs:

```json
{
  "id": "...",
  "instruction": "...",
  "thought": "...",
  "response": "...",
  "meta": {
    "self_correction": "none | genuine | theatrical",
    "correction_is_grounded": true,
    "problem_class": "solvable | impossible | ill_posed",
    "verifiable": true,
    "completion_honest": true,
    "compressed": false,
    "track": "opt1 | opt2 | opt3",
    "provenance": { "verifier": "...", "branch_history": "...", "injected_error": null }
  }
}
```

Deliberately include a **fraction of no-correction traces** so the model doesn't learn that every
trace must contain a dramatic reversal (primary guard against theatricality).

---

## 8. Eval harness = admission gate (runs BEFORE anything enters the dataset)

Per-track primary + secondary detectors:

| Track | Primary detector | Secondary detector |
|---|---|---|
| Opt 1 | **Correction re-verification** — pre-correction claim verifiably WRONG *and* final verifiably RIGHT (near-real metric) | **Lanham-style ablation** — truncate before correction, force answer; genuine iff already committed to wrong answer |
| Opt 2 | **Abstention calibration matrix** — confusion matrix over classes; loudly report *fabricates-on-impossible* and *over-abstains-on-solvable* | **Claim-vs-status consistency** (NLI/judge) — expressed completion status vs gold class |
| Opt 3 | **Theatricality discriminator + honeypots** — validate on labeled pairs; seed known-theatrical honeypots to measure detector **recall** | **Injection-leakage / surprise check** — ablation + perplexity spike at correction point |
| All | **Compression check** — flag hard-step hand-waves to "the literature"/"numerically"; length-vs-difficulty | **Meta-leakage check** — scratchpad/meta phrases in `response` |

**White-box gate vs. black-box deliverable:** the generation-time gate may use privileged info
(verifier ground truth, branch history, injection provenance). The **deliverable harness** must run
**black-box on bare triples**, including batches we didn't generate. Keep them logically separate
(even if shared code) so a blind spot doesn't corrupt labels and eval simultaneously.

**Gate outcomes:** pass → dataset; clean-theatrical (esp. from Opt 3) → labeled-negatives pile;
else → discard.

---

## 9. Adaptive Data — role & budget

- **Role:** last-mile **finisher/QA**, not the genuineness generator. Uses: `length`
  (detailed/extensive → kills compression), `blueprint` (style/spec system prompt),
  `deduplication`, `reasoning_traces` (format), and `grade_before → grade_after` (regression
  catch). No verifier hook, no branch sampling, no error-injection, no model choice → the
  genuineness logic is ours. (This is the expected "falls short on a specific axis" finding.)
- **Budget (300 credits):** no public $/credit price; credits meter per-run × rows × recipes.
  Procedure: `datasets.run(..., estimate=True)` on the real config → read
  `estimatedCreditsConsumed`; pilot `max_rows=20–50` to calibrate credits/row for our recipe stack;
  extrapolate with headroom. Treat 300 credits as **pilot-scale** — spend on the highest-value
  slice (seed traces we verify + expand ourselves).

---

## 10. Deliverables & end goal

- **End goal:** the dataset (triples + metadata), plus the pipeline that made it and the harness
  that guards it. Adding validated triples to the dataset **is** the goal of the pilot.
- **Honest asterisk (put in writeup):** the dataset is the *proximate* goal; Adapt Labs ultimately
  cares about **downstream training impact**, which no 48-hour eval can measure. Everything the
  harness scores is a **proxy** for training value — strongest for Opt 1 (re-verification ≈ real
  metric), weaker for Opt 2/3. There is **no ground-truth metric for genuine-vs-theatrical**; we
  measure *causal load-bearing-ness* as the proxy. Name this gap rather than paper over it.

- Repo deliverables: generation pipeline, eval harness, generated samples, reproducible README.
- Technical writeup (≤2 pages): approach, results, risks at scale, what to resolve before scaling.
- Reflections note (≤1 page): tradeoffs, where we got stuck, another-week list, where Adaptive Data
  helped vs. fell short.

---

## 11. Proposed pilot composition (draft — needs your numbers)

- **Domain mix:** ~60% solvable (verifiable, for genuine corrections) / ~25% impossible-or-open
  (honest completion) / ~15% ill-posed (surface ambiguity). Tunable to the downstream model's
  weakest axis.
- **Trace structure decision (OPEN):** keep the `thought`/`response` split but fix it so correction
  **survives into `response`**, vs. collapse to one surfaced trace. The brief's "long-form,
  fully-explained reasoning with genuine mid-generation self-correction" reads as one visible trace
  → leans toward surfacing correction in `response`.
