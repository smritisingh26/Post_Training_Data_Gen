"""
Option 3 -- Adversarial Error-Injection with Consequence Propagation (supplement).

Two jobs (DESIGN.md §4):
  (a) top up genuine-correction YIELD when natural harvesting is too sparse
      (`inject_and_repair` -- see below), and
  (b) manufacture LABELED THEATRICAL NEGATIVES on purpose, so the training set has
      hard negatives and the harness's theatricality detector can be measured
      (honeypots) (`make_theatrical_negative`).

Both consume an already-generated, verifier-passed Option-1 sample as their base
(DESIGN.md §3: Option 3 is a booster, not an independent problem source) and hand it
to the SABOTEUR -- a deliberately weaker model. In live mode this is a real call to
the weaker model; in stub mode `make_theatrical_negative` replays a hand-authored
canned trace for reproducibility (`inject_and_repair` is live-only -- see its
docstring).

Honest guardrail: an injected error only yields a GENUINE positive if the recovery
is load-bearing (verified). If it isn't, the sample is a THEATRICAL negative -- which
is still useful, just labeled as such.
"""
from __future__ import annotations

import re

from ..schema import (Sample, Meta, Provenance, SelfCorrection, Track)
from ..providers import Provider
from ..verifier import build_verifier

_FINAL_RE = re.compile(r"FINAL:\s*(-?\d+)", re.I)
_INJECTED_RE = re.compile(r"^INJECTED:\s*(.+)$", re.I | re.M)


_SABOTEUR_SYS = (
    "You are deliberately inserting a FAKE moment of self-doubt into an already-correct "
    "solution, to build a labeled training example of theatrical (non-genuine) "
    "self-correction. Insert exactly one brief 'wait, actually, let me reconsider...' aside "
    "partway through, then have the reasoning conclude the original answer was right all "
    "along. Do NOT change the final answer. Do NOT introduce or fix any real error -- the "
    "hesitation must be empty theater with nothing behind it. Return the full rewritten "
    "solution."
)


def _inject_theater(response: str, saboteur: Provider) -> str:
    user = f"Original correct solution:\n\n{response}\n\nRewrite it with the fabricated hesitation inserted."
    return saboteur.complete(_SABOTEUR_SYS, user, temperature=0.9)


def make_theatrical_negative(base: Sample, saboteur: Provider, live: bool) -> Sample:
    """Produce a labeled THEATRICAL negative from an already-verified Option-1 base sample."""
    if live:
        thought = f"(saboteur) injecting a fabricated, non-grounded hesitation into {base.id}'s solution"
        response = _inject_theater(base.response, saboteur)
    else:
        thought = saboteur.complete("scratchpad", "STUB_KEY: theatrical_thought\n", temperature=0.9)
        response = saboteur.complete("answer", "STUB_KEY: theatrical_response\n", temperature=0.9)
    return Sample(
        id=f"opt3__theatrical_negative__{base.id}",
        instruction=base.instruction,
        thought=thought,
        response=response,
        meta=Meta(
            problem_class=base.meta.problem_class,
            self_correction=SelfCorrection.THEATRICAL,
            track=Track.OPT3,
            verifiable=base.meta.verifiable,
            correction_is_grounded=False,   # the "catch" was fabricated
            completion_honest=True,
            provenance=Provenance(
                injected_error="fabricated 'wait/actually' reconsideration with no real error",
                branch_history=[f"saboteur({saboteur.name}): inserted non-grounded reconsideration into {base.id}"],
                solver_model=base.meta.provenance.solver_model,
            ),
        ),
    )


_CORRUPT_SYS = (
    "You will corrupt a correct step-by-step math solution with exactly ONE realistic "
    "error -- the kind of slip a mid-tier model would plausibly make (a dropped "
    "inclusion-exclusion term, a sign flip, an off-by-one, forgetting to apply a stated "
    "constraint, an arithmetic slip). Keep every other step identical; propagate the "
    "error through to a new WRONG final line 'FINAL: <number>'. After that, on its own "
    "line, write 'INJECTED: <one-sentence description of exactly what you changed>'."
)

_BLIND_REPAIR_SYS = (
    "Carefully re-derive this solution step by step, checking every intermediate "
    "calculation against the problem statement. If you find an error, explain it "
    "explicitly and give the corrected reasoning. If everything already checks out, "
    "confirm the answer as-is. End with a line 'FINAL: <number>'."
)


def _extract_final(text: str) -> int | None:
    # take the LAST match, not the first -- the repair prompt embeds the
    # injected wrong FINAL: line as context, which the model may quote before
    # giving its own corrected one.
    nums = _FINAL_RE.findall(text)
    return int(nums[-1]) if nums else None


def _corrupt(correct_response: str, saboteur: Provider) -> tuple[str, int | None, str]:
    """Ask the saboteur to corrupt one step. Returns (trace_shown_to_solver, claimed, description)."""
    user = f"Correct solution:\n\n{correct_response}\n\nCorrupt it as instructed."
    raw = saboteur.complete(_CORRUPT_SYS, user, temperature=0.9)
    m = _INJECTED_RE.search(raw)
    description = m.group(1).strip() if m else "(saboteur did not describe its edit)"
    trace = _INJECTED_RE.sub("", raw).strip()
    return trace, _extract_final(trace), description


def inject_and_repair(seed: dict, base: Sample, solver: Provider, saboteur: Provider,
                      live: bool) -> Sample | None:
    """
    Top up genuine-correction yield when the natural attempt was already correct
    (DESIGN.md §4 job (a)): have the saboteur plant a real, verifier-confirmed-wrong
    error into `base`'s correct trace, then have the solver reason forward BLIND
    (never told an error exists) and recover. Live-only -- pointless in stub mode,
    since stub seeds are authored to always slip on the natural first pass already.
    Returns None if the saboteur's injection doesn't actually break the answer even
    after one retry, or if the solver can't be shown a corrupted claim to re-verify.
    """
    if not live:
        return None
    verifier = build_verifier(seed["verifier"])

    verdict = None
    for _ in range(2):  # one retry if the injection doesn't actually break the answer
        trace, claimed, description = _corrupt(base.response, saboteur)
        if claimed is not None:
            verdict = verifier.check(claimed)
            if not verdict.correct:
                break
        verdict = None
    if verdict is None:
        return None

    branch_history = [
        f"saboteur({saboteur.name}): injected error -- {description}",
        f"injected claim: {verdict.claim} vs truth {verdict.ground_truth} -> WRONG (confirmed)",
    ]

    repair_user = f"{seed['instruction']}\n\nProposed solution:\n\n{trace}"
    thought = solver.complete(_BLIND_REPAIR_SYS, repair_user, temperature=0.7)
    response = solver.complete("Final answer with the surfaced correction explained in full. "
                               "End with a line 'FINAL: <number>'.",
                               repair_user, temperature=0.7)

    final_num = _extract_final(response)
    final_ok = None
    if final_num is not None:
        fv = verifier.check(final_num)
        final_ok = fv.correct
        branch_history.append(f"final re-verify: {fv.claim} -> {'OK' if fv.correct else 'WRONG'}")

    grounded = bool(final_ok)

    return Sample(
        id=f"opt3__injected_repair__{seed['id']}",
        instruction=seed["instruction"],
        thought=thought,
        response=response,
        meta=Meta(
            problem_class=base.meta.problem_class,
            self_correction=SelfCorrection.GENUINE if grounded else SelfCorrection.NONE,
            track=Track.OPT3,
            verifiable=True,
            correction_is_grounded=grounded,
            completion_honest=True,
            provenance=Provenance(
                verifier=verifier.name,
                verifier_passed=final_ok,
                pre_correction_wrong=True,
                branch_history=branch_history,
                injected_error=description,
                prior_attempt_text=trace,
                solver_model=solver.name,
            ),
        ),
    )
