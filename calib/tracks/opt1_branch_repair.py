"""
Option 1 -- Verifier-Gated Branch-and-Repair (the spine).

Loop: solver attempts (warm) -> verifier checks the claimed answer against ground
truth -> if WRONG, branch: the solver is shown the discrepancy and reasons forward
to a repair -> re-verify. The genuine correction is surfaced INTO THE RESPONSE.

Genuineness is structural: the only errors that enter a kept trace are ones the
local verifier confirmed wrong. The model cannot fabricate the error.

In stub mode the "attempt" and "repair" come from the replay bank; the VERIFIER
runs for real either way (it's local SymPy), so the grounding is genuine even in
the keyless demo. In live mode, the repair step is ALSO live: the solver is shown
its own wrong attempt plus the verifier's confirmation that it's wrong (never the
ground-truth number itself) and asked to find and fix the error for real.
"""
from __future__ import annotations

import re

from ..schema import (Sample, Meta, Provenance, ProblemClass, SelfCorrection, Track)
from ..providers import Provider
from ..verifier import build_verifier


_SOLVE_SYS = ("You are solving a math problem. Show your reasoning, then end with a line "
              "'FINAL: <number>'. Do not restate the problem.")

_REPAIR_SYS = ("Reasoning scratchpad: find the actual error in your previous attempt, explain "
               "it explicitly, then give the corrected reasoning. End with a line 'FINAL: <number>'.")

_ANSWER_RE = re.compile(r"FINAL:\s*(-?\d+)", re.I)
_TRAILING_EQ_RE = re.compile(r"=\s*(-?\d+)\s*\.?\s*$", re.M)


def _extract_answer(text: str) -> int | None:
    # take the LAST match, not the first -- repair prompts embed a prior wrong
    # FINAL: line as context, which the model may quote before giving its own.
    nums = _ANSWER_RE.findall(text)
    return int(nums[-1]) if nums else None


def _extract_final_number(text: str) -> int | None:
    n = _extract_answer(text)
    if n is not None:
        return n
    nums = _TRAILING_EQ_RE.findall(text)
    return int(nums[-1]) if nums else None


def generate(seed: dict, solver: Provider, live: bool) -> Sample | None:
    """Produce one Option-1 sample, or None if this seed isn't verifiable-solvable."""
    if "verifier" not in seed:
        return None
    verifier = build_verifier(seed["verifier"])

    # --- attempt (warm) ---
    user = f"STUB_KEY: {seed['stub_key']}\n{seed['instruction']}"
    attempt = solver.complete(_SOLVE_SYS, user, temperature=0.8)
    claimed = _extract_answer(attempt)

    branch_history = [f"attempt: claimed={claimed}"]
    pre_correction_wrong = None
    verdict = None

    if claimed is not None:
        verdict = verifier.check(claimed)
        pre_correction_wrong = (not verdict.correct)
        branch_history.append(f"verify: {verdict.claim} vs truth {verdict.ground_truth} "
                              f"-> {'OK' if verdict.correct else 'WRONG'}")

    # --- branch + repair (only interesting when the attempt was genuinely wrong) ---
    prior_attempt_text = None
    if live and pre_correction_wrong:
        # genuinely live: show the solver its own wrong attempt and the verifier's
        # confirmation that it's wrong (NOT the ground-truth number), and ask it to
        # find and fix the error for real.
        repair_user = (
            f"{seed['instruction']}\n\n"
            f"Your previous attempt reasoned:\n{attempt}\n\n"
            f"A checker confirms the final claimed answer ({verdict.claim}) is WRONG. "
            f"Find your error, explain it explicitly, then give the corrected reasoning. "
            f"End with a line 'FINAL: <number>'."
        )
        thought = solver.complete(_REPAIR_SYS, repair_user, temperature=0.7)
        response = solver.complete("Final answer with the surfaced correction explained in full. "
                                   "End with a line 'FINAL: <number>'.",
                                   repair_user, temperature=0.7)
        branch_history.append("repair: live")
        prior_attempt_text = attempt
    elif claimed is None or not pre_correction_wrong:
        # nothing confirmed wrong -- don't fabricate a "repair"; keep the attempt's own text.
        thought = attempt
        response = attempt
        branch_history.append("repair: skipped (nothing confirmed wrong)")
    else:
        # stub mode: the finished, correction-surfaced trace is authored to the bank
        # keyed opt1_<id>_{thought,response}.
        tkey = f"opt1_{seed['id']}_thought"
        rkey = f"opt1_{seed['id']}_response"
        thought = solver.complete("Reasoning scratchpad.", f"STUB_KEY: {tkey}\n", temperature=0.7)
        response = solver.complete("Final answer with surfaced correction.",
                                   f"STUB_KEY: {rkey}\n", temperature=0.7)
        branch_history.append("repair: stub replay")

    # re-verify the final numeric answer that appears in the response
    final_num = _extract_final_number(response)
    final_ok = None
    if final_num is not None:
        fv = verifier.check(final_num)
        final_ok = fv.correct
        branch_history.append(f"final re-verify: {fv.claim} -> {'OK' if fv.correct else 'WRONG'}")

    grounded = bool(pre_correction_wrong) and bool(final_ok)

    return Sample(
        id=f"opt1__{seed['id']}",
        instruction=seed["instruction"],
        thought=thought,
        response=response,
        meta=Meta(
            problem_class=ProblemClass.SOLVABLE,
            self_correction=SelfCorrection.GENUINE if grounded else SelfCorrection.NONE,
            track=Track.OPT1,
            verifiable=True,
            correction_is_grounded=grounded,
            completion_honest=True,
            provenance=Provenance(
                verifier=verifier.name,
                verifier_passed=final_ok,
                pre_correction_wrong=pre_correction_wrong,
                branch_history=branch_history,
                prior_attempt_text=prior_attempt_text,
                solver_model=solver.name,
            ),
        ),
    )
