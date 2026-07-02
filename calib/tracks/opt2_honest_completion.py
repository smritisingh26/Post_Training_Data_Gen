"""
Option 2 -- Difficulty-Tiered Honest-Completion (2nd pillar).

For impossible / ill-posed prompts, the TARGET is honest non-completion: reason
toward the recognition of impossibility and state it plainly, ideally with the
"I can't prove X but can rigorously establish Y" move.

The elegant bit (DESIGN.md §5): the triage obstruction is INJECTED into the
generator's context, so honest admission is the path of least resistance rather
than something the model must discover under adversarial framing.
"""
from __future__ import annotations

from ..schema import (Sample, Meta, Provenance, ProblemClass, SelfCorrection, Track)
from ..providers import Provider
from ..triage import TriageResult


_HONEST_SYS = ("You are answering a hard technical prompt. If the task is unprovable, "
               "unsolvable in closed form, or underspecified, say so plainly and explain "
               "why, then state the strongest correct thing that CAN be established. "
               "Never fabricate a completed proof. Explain fully; do not compress.")


def generate(seed: dict, solver: Provider, triage_result: TriageResult, live: bool) -> Sample:
    obstruction = triage_result.obstruction or "This task cannot be completed as posed."
    user = (f"STUB_KEY: {seed['stub_key']}\n"
            f"[triage: class={triage_result.problem_class.value}; "
            f"obstruction={obstruction}]\n\n{seed['instruction']}")

    tkey = f"{seed['stub_key']}_thought"
    thought = solver.complete("Reasoning scratchpad.", f"STUB_KEY: {tkey}\n", temperature=0.6)
    response = solver.complete(_HONEST_SYS, user, temperature=0.6)

    return Sample(
        id=f"opt2__{seed['id']}",
        instruction=seed["instruction"],
        thought=thought,
        response=response,
        meta=Meta(
            problem_class=triage_result.problem_class,
            self_correction=SelfCorrection.NONE,   # honest-completion, no error-repair
            track=Track.OPT2,
            verifiable=False,
            correction_is_grounded=False,
            completion_honest=True,
            obstruction=obstruction,
            provenance=Provenance(
                branch_history=[f"triage={triage_result.source}:{triage_result.problem_class.value}"],
                solver_model=solver.name,
            ),
        ),
    )
