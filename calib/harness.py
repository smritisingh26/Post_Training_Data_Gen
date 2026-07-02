"""
Eval harness = admission gate (DESIGN.md §8).

CRITICAL design point: this is the BLACK-BOX deliverable. It must run on bare
(instruction, thought, response) triples from ANY batch -- including ones we did
not generate and that carry no provenance. So every detector here works on text
alone. (The generation-time gate MAY additionally use privileged provenance via
verifier re-checks; that white-box path lives in the tracks, not here.)

Detectors map to the verified EDA failure modes:
  D1 genuine-correction-present  : is there a real turn, or is the response laundered?
  D2 theatrical-correction       : "Actually/Wait" that catches nothing (filler)
  D3 fabricated-rigor            : claims a completed proof/result (esp. on impossible)
  D4 compression                 : hard step hand-waved to authority/"numerically"
  D5 meta-leakage                : scratchpad/meta phrases leaked into response
  D6 length-vs-difficulty        : ramble / collapse (efficiency)

Repetition/looping collapse is deliberately NOT a lexical detector here. A first
attempt (sliding n-gram repeat count, then n-gram diversity ratio) was tested
directly against real generated samples and found to have no threshold that
separates genuine degenerate looping from legitimate math writing that reuses
fixed terminology (a modulus, a divisor set) at a comparable lexical density --
in the tested data the false-positive case was sometimes MORE lexically
repetitive than the true positive. Rather than ship a heuristic that actively
discards good data, this is judged semantically instead (see
make_llm_judge_hook's REPETITIVE question) -- a real, acknowledged gap for
fully keyless runs, named rather than papered over with a broken proxy.

Each detector returns a Signal(flag, score, evidence). The gate turns signals +
the sample's declared labels into an admit/reject/route-to-negatives decision.

These are HEURISTIC text detectors. The honest-accounting note (writeup) states:
they measure causal-load-bearing-ness and surface lexical tells as a PROXY for
"genuine vs theatrical" -- there is no ground-truth metric for that distinction.
An LLM judge can be layered on top (judge_hook) for the non-lexical calls.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .schema import Sample, ProblemClass, SelfCorrection
from .providers import Provider


@dataclass
class Signal:
    name: str
    flag: bool            # True = failure-mode present
    score: float          # 0..1 strength
    evidence: str = ""


@dataclass
class HarnessReport:
    sample_id: str
    signals: list[Signal] = field(default_factory=list)
    admit: bool = True
    route: str = "dataset"   # dataset | negatives | discard
    reasons: list[str] = field(default_factory=list)

    def by(self, name: str) -> Optional[Signal]:
        return next((s for s in self.signals if s.name == name), None)


# --- lexical resources ------------------------------------------------------

_CORRECTION_MARKERS = re.compile(
    r"\b(wait|actually|hold on|let me reconsider|on second thought|that'?s not right|"
    r"i made an error|scratch that|let me re-?(?:derive|check|examine)|correction|"
    r"i was wrong|this is wrong|doesn'?t hold|does not hold)\b", re.I)

# markers that a correction is anchored to a REAL, specific caught error
_GROUNDED_CORRECTION = re.compile(
    r"(double[- ]count|counted twice|inclusion[- ]exclusion|sign error|off by one|"
    r"can'?t be negative|cannot be negative|must subtract|overcount|"
    r"violates|contradicts the constraint|units? (?:don'?t|do not) match|"
    r"dimension(?:al)? mismatch|re-?reading the (?:problem|context))", re.I)

_FABRICATED_RIGOR = re.compile(
    r"(this completes the proof|q\.?e\.?d|∎|we have (?:thus )?proven|hence (?:we have )?proved|"
    r"thus .{0,30}(?:proven|proved|holds)|the exact solution is|closed[- ]form solution is|"
    r"every step is rigorous|is provably)", re.I)

# Additive-only (never remove existing patterns -- would regress the
# fabricated_rigor tests in tests/test_all.py). Patched, not solved: live
# phrasing varies more than the hand-authored stub text these were tuned
# against, so this is a best-effort widening, not a guarantee -- cases like
# this genuinely need an LLM-judge layer eventually, not just more regex.
_HONEST_HEDGE = re.compile(
    r"(no closed[- ]form|cannot be solved exactly|is an open problem|remains unproven|"
    r"no general (?:analytic|closed)|not possible to prove|this is a numerical verification|"
    r"cannot be determined|underspecified|is not a (?:rigorous )?proof|"
    r"no known (?:closed|analytic)|there is no (?:known )?(?:exact|general|closed-form) solution|"
    r"no exact (?:closed-form )?solution exists)", re.I)

# Additive-only, same caveat as _HONEST_HEDGE: catches explicit hand-waves-to-
# authority, not general "summarizes rather than explains" -- a response that's
# just short and conclusion-only with no derivation trips none of these phrases.
# See make_llm_judge_hook() below for the semantic check regex can't do.
_COMPRESSION = re.compile(
    r"(available in the literature|standard reference|can be found in any|"
    r"follows from the literature|details? (?:follow|are omitted|left to the reader)|"
    r"it is known numerically|known numerically|beyond the scope|omitted for brevity|"
    r"standard (?:method|technique)s? (?:apply|can be used)|"
    r"trivially follows|left as an exercise|the details are straightforward|"
    r"can be shown that|it can be verified that)", re.I)

_META_LEAK = re.compile(
    r"(internal scratchpad|scratchpad notes?|as requested|as the user|the request for|"
    r"we were asked|the problem asks|i (?:should|will) now (?:write|produce) the (?:final )?(?:answer|response))",
    re.I)


# --- detectors --------------------------------------------------------------

def d1_genuine_correction(s: Sample) -> Signal:
    """A genuine correction should be PRESENT IN THE RESPONSE and grounded.
    Flag=True means the *failure* (no genuine correction where one is claimed)."""
    resp_markers = len(_CORRECTION_MARKERS.findall(s.response))
    grounded = len(_GROUNDED_CORRECTION.findall(s.response))
    thought_markers = len(_CORRECTION_MARKERS.findall(s.thought))

    if s.meta.self_correction == SelfCorrection.GENUINE:
        # The correction counts as SURFACED if the response contains either an explicit
        # marker ("that doesn't hold") OR a grounded anchor ("overcounts", "counted twice").
        # Genuineness still requires a grounded anchor. Failure = not surfaced, or all the
        # wrestling is buried in `thought` with nothing in `response`.
        surfaced = (resp_markers >= 1 or grounded >= 1)
        present = surfaced and grounded >= 1
        scrubbed = thought_markers >= 3 and resp_markers == 0 and grounded == 0
        flag = (not present) or scrubbed
        ev = f"resp_markers={resp_markers} grounded={grounded} thought_markers={thought_markers}"
        return Signal("genuine_correction_missing", flag, 1.0 if flag else 0.0, ev)
    # for NONE/THEATRICAL, this detector doesn't assert a failure by itself
    return Signal("genuine_correction_missing", False, 0.0,
                  f"n/a (declared {s.meta.self_correction.value})")


def d2_theatrical(s: Sample) -> Signal:
    """Correction markers present but NOT anchored to any real caught error."""
    markers = len(_CORRECTION_MARKERS.findall(s.response)) + len(_CORRECTION_MARKERS.findall(s.thought))
    grounded = len(_GROUNDED_CORRECTION.findall(s.response)) + len(_GROUNDED_CORRECTION.findall(s.thought))
    flag = markers >= 2 and grounded == 0
    score = min(1.0, markers / 6.0) if flag else 0.0
    return Signal("theatrical_correction", flag, score,
                  f"markers={markers} grounded_anchors={grounded}")


def d3_fabricated_rigor(s: Sample) -> Signal:
    """Claims a completed proof/result -- a failure when the problem is impossible/ill_posed."""
    claims = len(_FABRICATED_RIGOR.findall(s.response))
    hedges = len(_HONEST_HEDGE.findall(s.response))
    impossible = s.meta.problem_class in (ProblemClass.IMPOSSIBLE, ProblemClass.ILL_POSED)
    flag = impossible and claims >= 1 and hedges == 0
    ev = f"class={s.meta.problem_class.value} claim_phrases={claims} hedges={hedges}"
    return Signal("fabricated_rigor", flag, 1.0 if flag else 0.0, ev)


def d4_compression(s: Sample) -> Signal:
    hits = len(_COMPRESSION.findall(s.response))
    flag = hits >= 1
    return Signal("compression", flag, min(1.0, hits / 3.0), f"handwave_phrases={hits}")


def d5_meta_leak(s: Sample) -> Signal:
    hits = len(_META_LEAK.findall(s.response))
    flag = hits >= 1
    return Signal("meta_leak", flag, min(1.0, hits / 2.0), f"meta_phrases={hits}")


def d6_length(s: Sample, lo: int = 200, hi: int = 20000) -> Signal:
    """Efficiency guard: too short = collapsed, too long = ramble. Length in chars."""
    n = len(s.response)
    flag = n < lo or n > hi
    where = "collapsed" if n < lo else ("ramble" if n > hi else "ok")
    return Signal("length_efficiency", flag, 0.5 if flag else 0.0, f"len={n} ({where})")


DETECTORS: list[Callable[[Sample], Signal]] = [
    d1_genuine_correction, d2_theatrical, d3_fabricated_rigor,
    d4_compression, d5_meta_leak, d6_length,
]

# Which signals are hard blockers (reject/route) vs soft (warn but admit).
# compression and length_efficiency are hard blocks: the pilot's success
# criteria name these as disqualifying, same standing as theatrical
# self-correction -- a soft warn that still admits would defeat the point.
_HARD_BLOCK = {"theatrical_correction", "fabricated_rigor", "genuine_correction_missing",
               "compression", "length_efficiency",
               "llm_judge_compressed", "llm_judge_fabricated", "llm_judge_repetitive"}
_SOFT = {"meta_leak"}


def evaluate(s: Sample, judge_hook: Optional[Callable[[Sample], list[Signal]]] = None
             ) -> HarnessReport:
    rep = HarnessReport(sample_id=s.id)
    rep.signals = [d(s) for d in DETECTORS]
    if judge_hook:
        rep.signals.extend(judge_hook(s))

    fired_hard = [sig for sig in rep.signals if sig.flag and sig.name in _HARD_BLOCK]
    fired_soft = [sig for sig in rep.signals if sig.flag and sig.name in _SOFT]

    # Route to negatives if EITHER the text detector fires OR the sample is
    # self-declared theatrical -- a self-declared label must always win, so
    # wording alone can't slip a known-theatrical trace into the dataset.
    declared_theatrical = s.meta.self_correction == SelfCorrection.THEATRICAL
    detected_theatrical = any(sig.name in ("theatrical_correction", "llm_judge_fabricated")
                              for sig in fired_hard)

    if declared_theatrical or detected_theatrical:
        rep.admit, rep.route = False, "negatives"
        if detected_theatrical:
            rep.reasons.append("theatrical correction -> routed to labeled-negatives pile")
        else:
            rep.reasons.append("self-declared theatrical (undetected by text signals) "
                               "-> routed to labeled-negatives pile")
    elif fired_hard:
        rep.admit, rep.route = False, "discard"
        rep.reasons += [f"hard block: {sig.name} ({sig.evidence})" for sig in fired_hard]
    else:
        rep.admit, rep.route = True, "dataset"
        if fired_soft:
            rep.reasons += [f"soft warn: {sig.name} ({sig.evidence})" for sig in fired_soft]

    return rep


# --- LLM judge layer -----------------------------------------------
# Catches what the lexical detectors structurally can't: semantic compression
# (a short, conclusion-only response that never trips a hand-wave PHRASE) and
# semantically-hollow explanations (grounded-sounding vocabulary describing an
# error that doesn't actually hold up). Never wired in by default -- evaluate()
# stays keyless-capable for the black-box eval-batch deliverable; callers that
# have a live judge model available pass make_llm_judge_hook(judge) explicitly.

_JUDGE_SYS = (
    "You are auditing one (instruction, response) reasoning trace for a training "
    "dataset. You may also be shown a PRIOR CLAIM the response is reacting to -- if "
    "so, use it to check whether the response's described correction is real, rather "
    "than assuming it is or isn't. Answer three questions about the RESPONSE text.\n\n"
    "Q1 COMPRESSED: does the response summarize or state conclusions/results without "
    "showing the actual derivation at each step, given the instruction's difficulty? "
    "(A short response that fully shows its work is NOT compressed. A response that "
    "skips or hand-waves a hard step is.)\n\n"
    "Q2 FABRICATED_CORRECTION: does the response contain self-correction language "
    "(e.g. 'wait', 'actually', 'let me reconsider', 'that's wrong')? If so, is the "
    "described error real, specific, and load-bearing to the final answer, or does it "
    "read like a vague/hollow pretext for a dramatic reversal with no substantive "
    "mistake behind it? If a PRIOR CLAIM is shown, check the described correction "
    "against it directly. Answer false if there is no self-correction language at all.\n\n"
    "Q3 REPETITIVE: does the response get stuck in a degenerate loop -- circling back "
    "to re-derive or re-assert the SAME point over and over in a way that reads like it "
    "got stuck, making no new progress? This is NOT the same as either (a) legitimately "
    "reusing the same terminology or number many times because the problem itself "
    "involves a fixed, recurring quantity (a fixed modulus, a divisor mentioned "
    "descriptively at each step) while still making steady progress, or (b) an "
    "organized report-style answer restating ONE conclusion across clearly-labeled "
    "sections (e.g. a summary, then a detailed explanation, then a closing statement) -- "
    "this is normal and expected for honest non-completion answers on impossible or "
    "ill-posed problems, which have no numeric derivation to progress through and are "
    "supposed to support one conclusion from a few angles. Only answer true for genuine "
    "circular restatement that reads as the model failing to move forward, not for "
    "deliberate structure or shared vocabulary.\n\n"
    "Return STRICT JSON only: {\"compressed\": true|false, \"compressed_evidence\": "
    "\"<one sentence>\", \"fabricated_correction\": true|false, \"fabricated_evidence\": "
    "\"<one sentence>\", \"repetitive\": true|false, \"repetitive_evidence\": \"<one sentence>\"}"
)


def make_llm_judge_hook(judge: Provider) -> Callable[[Sample], list[Signal]]:
    """Build a judge_hook closure bound to a live judge Provider (Claude, per DESIGN.md
    §6). Fails safe: any parse/API problem yields non-flagging signals rather than
    blocking a sample on a judge error."""
    def hook(s: Sample) -> list[Signal]:
        prior = s.meta.provenance.prior_attempt_text
        prior_block = (f"PRIOR CLAIM (shown to the model as something to check; may be "
                       f"wrong):\n{prior}\n\n" if prior else "")
        user = f"INSTRUCTION:\n{s.instruction}\n\n{prior_block}RESPONSE:\n{s.response}\n\nJSON:"
        try:
            raw = judge.complete(_JUDGE_SYS, user, temperature=0.0)
            m = re.search(r"\{.*\}", raw, re.S)
            obj = json.loads(m.group(0) if m else raw)
        except Exception:
            return [
                Signal("llm_judge_compressed", False, 0.0, "judge output unparseable"),
                Signal("llm_judge_fabricated", False, 0.0, "judge output unparseable"),
                Signal("llm_judge_repetitive", False, 0.0, "judge output unparseable"),
            ]
        compressed = bool(obj.get("compressed", False))
        fabricated = bool(obj.get("fabricated_correction", False))
        repetitive = bool(obj.get("repetitive", False))
        return [
            Signal("llm_judge_compressed", compressed, 1.0 if compressed else 0.0,
                  str(obj.get("compressed_evidence", ""))[:200]),
            Signal("llm_judge_fabricated", fabricated, 1.0 if fabricated else 0.0,
                  str(obj.get("fabricated_evidence", ""))[:200]),
            Signal("llm_judge_repetitive", repetitive, 1.0 if repetitive else 0.0,
                  str(obj.get("repetitive_evidence", ""))[:200]),
        ]
    return hook


def summarize(reports: list[HarnessReport]) -> dict:
    from collections import Counter
    routes = Counter(r.route for r in reports)
    fired = Counter(sig.name for r in reports for sig in r.signals if sig.flag)
    return {
        "n": len(reports),
        "admitted": sum(1 for r in reports if r.admit),
        "routes": dict(routes),
        "signals_fired": dict(fired),
    }
