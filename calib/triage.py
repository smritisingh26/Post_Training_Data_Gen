"""
Triage: the highest-leverage shared component (DESIGN.md §5).

Runs once per prompt, before generation. Stamps:
  - problem_class: solvable | impossible | ill_posed
  - verifiable:    bool (only meaningful for solvable)
  - obstruction:   for impossible/ill_posed, WHY it can't be done

Two-tier build (pilot scope): (a) LLM classifier for judgment, backed by
(b) a small hardcoded REGISTRY of known-impossible/open problems. The registry
catches the famous cases where an LLM might waver (RH, general n-body closed
form, squaring the circle, general quintic in radicals, halting problem). The
LLM handles the "looks impossible but is a solvable reduction" cases -- e.g. the
Navier-Stokes microfluidic slit-flow trap the EDA caught -- which a registry
cannot judge.

The (c) agentic solvability-probe tier is deferred to scale (noted in writeup).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .schema import ProblemClass
from .providers import Provider


# --- (b) hardcoded registry of known-impossible / open-as-posed problems ----
# Each entry: matcher regex -> (class, obstruction). Order matters (first hit).
REGISTRY: list[tuple[str, ProblemClass, str]] = [
    (r"riemann hypothesis",
     ProblemClass.IMPOSSIBLE,
     "The Riemann Hypothesis is an open problem; no known proof exists. Finite "
     "zero-checking is a numerical verification, not a proof of the hypothesis."),
    (r"(exact|closed[- ]?form).*(three|3|n)[- ]?body|(three|3|n)[- ]?body.*(exact|closed)",
     ProblemClass.IMPOSSIBLE,
     "The general n-body (n>=3) problem has no closed-form solution; only special "
     "solutions (restricted problem, Lagrange points, Jacobi integral) exist."),
    (r"squar(e|ing) the circle",
     ProblemClass.IMPOSSIBLE,
     "Squaring the circle is impossible with compass and straightedge (pi is transcendental)."),
    (r"(general )?quintic.*(radicals|solvab)",
     ProblemClass.IMPOSSIBLE,
     "The general quintic is not solvable in radicals (Abel-Ruffini)."),
    (r"halting problem",
     ProblemClass.IMPOSSIBLE,
     "The halting problem is undecidable (Turing)."),
]


@dataclass
class TriageResult:
    problem_class: ProblemClass
    verifiable: bool
    obstruction: str | None
    source: str  # "registry" or "llm"


_TRIAGE_SYS = (
    "You are a triage classifier for math/logic problems. Judge the ACTUAL task, "
    "not its grand framing (e.g. 'derive the Navier-Stokes solution for a "
    "fully-developed slit channel' is a SOLVABLE reduction, not the open "
    "Millennium problem). Return STRICT JSON only."
)

_TRIAGE_TMPL = """STUB_KEY: {stub_key}
Classify this problem.

PROBLEM:
{instruction}

Return JSON with keys:
  "problem_class": one of "solvable" | "impossible" | "ill_posed"
  "verifiable": true if a solvable problem has a machine-checkable numeric/symbolic answer
  "obstruction": if impossible/ill_posed, one sentence why; else null
JSON:"""


def _registry_check(instruction: str) -> TriageResult | None:
    text = instruction.lower()
    for pattern, cls, obstruction in REGISTRY:
        if re.search(pattern, text):
            return TriageResult(cls, verifiable=False, obstruction=obstruction, source="registry")
    return None


def _parse_llm(raw: str) -> TriageResult:
    # tolerate code fences / prose around the JSON
    m = re.search(r"\{.*\}", raw, re.S)
    obj = json.loads(m.group(0)) if m else json.loads(raw)
    return TriageResult(
        problem_class=ProblemClass(obj["problem_class"]),
        verifiable=bool(obj.get("verifiable", False)),
        obstruction=obj.get("obstruction"),
        source="llm",
    )


def triage(instruction: str, judge: Provider, stub_key: str = "") -> TriageResult:
    """Registry first (defensive, high-confidence), then LLM for everything else."""
    hit = _registry_check(instruction)
    if hit is not None:
        return hit
    raw = judge.complete(_TRIAGE_SYS,
                         _TRIAGE_TMPL.format(instruction=instruction, stub_key=stub_key or "triage_default"),
                         temperature=0.0)
    try:
        return _parse_llm(raw)
    except Exception:
        # fail safe: treat unparseable as ill_posed so it doesn't slip into a
        # track that assumes ground truth.
        return TriageResult(ProblemClass.ILL_POSED, False,
                            "triage parse failure; routed conservatively", source="llm")
