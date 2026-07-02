"""
Verifier: the deterministic, local, network-free correctness signal.

This is the heart of why Option-1 corrections are GENUINE and not theatrical:
the error is discovered by an independent checker against ground truth, never
authored by the model. The judge LLM is never asked to grade correctness that
this verifier can decide.

Two verifier kinds cover the pilot's verifiable domain (competition-style math):
  - CountingVerifier: brute-forces set-cardinality problems ("how many n in [a,b]
    satisfy P") so inclusion-exclusion slips are caught exactly.
  - SymbolicVerifier: uses SymPy to check a claimed closed-form / value against
    ground truth (equation solving, simplification equality).

Each verifier exposes .check(claim) -> VerdictResult with a hard boolean.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import sympy as sp


@dataclass
class VerdictResult:
    correct: bool
    ground_truth: str
    claim: str
    detail: str = ""


class CountingVerifier:
    """Ground truth for 'how many integers in [lo, hi] satisfy predicate'."""

    def __init__(self, lo: int, hi: int, predicate: Callable[[int], bool], label: str = "count"):
        self.lo, self.hi, self.predicate, self.label = lo, hi, predicate, label
        self._truth = sum(1 for n in range(lo, hi + 1) if predicate(n))

    @property
    def name(self) -> str:
        return f"counting::{self.label}"

    def ground_truth(self) -> int:
        return self._truth

    def check(self, claimed_value: int) -> VerdictResult:
        ok = int(claimed_value) == self._truth
        return VerdictResult(
            correct=ok,
            ground_truth=str(self._truth),
            claim=str(claimed_value),
            detail=f"brute-forced |{{n in [{self.lo},{self.hi}] : {self.label}}}| = {self._truth}",
        )


class SymbolicVerifier:
    """Ground truth for a symbolic value/expression, checked with SymPy equality."""

    def __init__(self, truth_expr: str, symbols: str = "", label: str = "symbolic"):
        self.label = label
        self._syms = sp.symbols(symbols) if symbols else ()
        self._truth = sp.sympify(truth_expr)

    @property
    def name(self) -> str:
        return f"symbolic::{self.label}"

    def ground_truth(self) -> str:
        return str(self._truth)

    def check(self, claimed_expr: str) -> VerdictResult:
        claim = sp.sympify(claimed_expr)
        # equality via simplification of the difference
        ok = sp.simplify(claim - self._truth) == 0
        return VerdictResult(
            correct=bool(ok),
            ground_truth=str(self._truth),
            claim=str(claim),
            detail=f"sympy simplify(claim - truth) == 0 -> {ok}",
        )


# ---- registry so seeds can name a verifier declaratively -------------------

def build_verifier(spec: dict) -> object:
    """
    spec examples:
      {"kind": "counting", "lo": 1, "hi": 1000, "rule": "div3or5"}
      {"kind": "symbolic", "truth": "467", "label": "count_div3or5"}
    """
    kind = spec["kind"]
    if kind == "counting":
        rule = spec["rule"]
        pred = _RULES[rule]
        return CountingVerifier(spec["lo"], spec["hi"], pred, label=rule)
    if kind == "symbolic":
        return SymbolicVerifier(spec["truth"], spec.get("symbols", ""), spec.get("label", "symbolic"))
    raise ValueError(f"unknown verifier kind: {kind}")


# named predicates referenced by seeds (kept explicit for reproducibility)
_RULES: dict[str, Callable[[int], bool]] = {
    "div3or5": lambda n: n % 3 == 0 or n % 5 == 0,
    "div7or11": lambda n: n % 7 == 0 or n % 11 == 0,
    "perfect_square": lambda n: int(n ** 0.5) ** 2 == n,
    # harder: 4-set inclusion-exclusion -- easy to stop after the pairwise
    # correction and forget the triple/quadruple terms.
    "div2_3_5_7": lambda n: n % 2 == 0 or n % 3 == 0 or n % 5 == 0 or n % 7 == 0,
    # harder: modular arithmetic over a range spanning negative integers.
    "mod7_rem3": lambda n: n % 7 == 3,
    # harder: naive inclusion-exclusion for "div4 or div6" is correct on its
    # own, but the problem adds a further "and not div12" exclusion that's
    # easy to drop.
    "div4or6_not12": lambda n: (n % 4 == 0 or n % 6 == 0) and n % 12 != 0,
}
