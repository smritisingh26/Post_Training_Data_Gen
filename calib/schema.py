"""
Core data schema for the calibration pilot.

Every track (Option 1/2/3) emits a `Sample`. The harness/gate consumes it.
The design decision (see DESIGN.md §2.1): keep the given (instruction, thought,
response) split, but fix it so genuine self-correction SURVIVES into `response`
instead of being scrubbed out into `thought`. The `meta` block carries the labels
that let one dataset hold positives, hard negatives, and calibration pairs.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields, asdict
from enum import Enum
from typing import Any, Optional

log = logging.getLogger(__name__)


class ProblemClass(str, Enum):
    SOLVABLE = "solvable"
    IMPOSSIBLE = "impossible"     # open/unsolvable-as-posed (RH, general n-body closed form, ...)
    ILL_POSED = "ill_posed"       # underspecified / contradictory
    UNKNOWN = "unknown"           # unlabeled external data -- not classified, not guessed


class SelfCorrection(str, Enum):
    NONE = "none"                 # no correction in the trace (intentionally kept for a fraction)
    GENUINE = "genuine"           # real error, verifier-confirmed, really fixed
    THEATRICAL = "theatrical"     # fabricated error caught for show  -> hard negative
    UNKNOWN = "unknown"           # unlabeled external data -- no claim either way


class Track(str, Enum):
    OPT1 = "opt1_branch_repair"
    OPT2 = "opt2_honest_completion"
    OPT3 = "opt3_injection"
    UNKNOWN = "unknown"           # unlabeled external data -- not one of our own tracks


@dataclass
class Provenance:
    """White-box, generation-time info. NOT available to the black-box deliverable harness."""
    verifier: Optional[str] = None          # which checker grounded this (e.g. "sympy_count")
    verifier_passed: Optional[bool] = None  # did the FINAL answer pass ground truth
    pre_correction_wrong: Optional[bool] = None  # was the pre-correction claim verifiably wrong
    branch_history: list[str] = field(default_factory=list)
    injected_error: Optional[str] = None    # description if Option 3 planted an error
    prior_attempt_text: Optional[str] = None  # the wrong/corrupted claim `response` is
                                               # reacting to, when one exists -- lets a
                                               # judge verify a described correction
                                               # instead of guessing (see harness.py)
    solver_model: Optional[str] = None
    judge_model: Optional[str] = None


@dataclass
class Meta:
    problem_class: ProblemClass
    self_correction: SelfCorrection
    track: Track
    verifiable: bool = False
    correction_is_grounded: bool = False    # the caught error was real, not asserted
    completion_honest: bool = True          # expressed confidence matches verifiable status
    compressed: bool = False                # summarizes rather than explains
    obstruction: Optional[str] = None       # for impossible/ill_posed: why it can't be done
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Sample:
    id: str
    instruction: str
    thought: str
    response: str
    meta: Meta

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        # enums -> their string values
        d["meta"]["problem_class"] = self.meta.problem_class.value
        d["meta"]["self_correction"] = self.meta.self_correction.value
        d["meta"]["track"] = self.meta.track.value
        return d

    def to_public_json(self) -> dict[str, Any]:
        """What a black-box consumer sees: the triple + labels, NO privileged provenance."""
        d = self.to_json()
        d["meta"].pop("provenance", None)
        return d

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Sample":
        m = d["meta"]
        prov = m.get("provenance") or {}
        meta = Meta(
            problem_class=ProblemClass(m["problem_class"]),
            self_correction=SelfCorrection(m["self_correction"]),
            track=Track(m["track"]),
            verifiable=m.get("verifiable", False),
            correction_is_grounded=m.get("correction_is_grounded", False),
            completion_honest=m.get("completion_honest", True),
            compressed=m.get("compressed", False),
            obstruction=m.get("obstruction"),
            provenance=Provenance(**prov),
        )
        return Sample(id=d["id"], instruction=d["instruction"],
                      thought=d["thought"], response=d["response"], meta=meta)

    @staticmethod
    def from_bare_json(d: dict[str, Any]) -> "Sample":
        """Tolerant loader for the black-box deliverable: a genuinely external batch
        may carry no `meta` at all, or labels in a foreign vocabulary. Missing or
        unrecognized problem_class/self_correction/track fall back to UNKNOWN rather
        than raising -- the detectors that depend on those fields already degrade
        gracefully when they're UNKNOWN (see harness.py)."""
        m = d.get("meta") or {}
        prov = m.get("provenance") or {}

        def _enum_or_unknown(enum_cls, value, unknown):
            try:
                return enum_cls(value)
            except (ValueError, TypeError):
                return unknown

        # tolerate foreign/extra keys in an external batch's "provenance" block
        # (if it even has one) rather than crashing on an unexpected keyword.
        prov_fields = {f.name for f in fields(Provenance)}
        prov_clean = {k: v for k, v in prov.items() if k in prov_fields} if isinstance(prov, dict) else {}

        meta = Meta(
            problem_class=_enum_or_unknown(ProblemClass, m.get("problem_class"), ProblemClass.UNKNOWN),
            self_correction=_enum_or_unknown(SelfCorrection, m.get("self_correction"), SelfCorrection.UNKNOWN),
            track=_enum_or_unknown(Track, m.get("track"), Track.UNKNOWN),
            verifiable=m.get("verifiable", False),
            correction_is_grounded=m.get("correction_is_grounded", False),
            completion_honest=m.get("completion_honest", True),
            compressed=m.get("compressed", False),
            obstruction=m.get("obstruction"),
            provenance=Provenance(**prov_clean),
        )
        return Sample(id=str(d.get("id", "")), instruction=str(d.get("instruction", "")),
                      thought=str(d.get("thought", "")), response=str(d.get("response", "")),
                      meta=meta)


def write_jsonl(samples: list[Sample], path: str, public: bool = False) -> None:
    with open(path, "w") as f:
        for s in samples:
            row = s.to_public_json() if public else s.to_json()
            f.write(json.dumps(row) + "\n")


def read_jsonl(path: str) -> list[Sample]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Sample.from_json(json.loads(line)))
    return out


def read_jsonl_lenient(path: str) -> tuple[list[Sample], int]:
    """Black-box loader for external batches: tolerates missing/foreign meta (via
    Sample.from_bare_json) AND skips-and-logs any row that's malformed in some
    other way (bad JSON, missing required text fields) rather than aborting the
    whole file. Returns (samples, n_skipped)."""
    out = []
    skipped = 0
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Sample.from_bare_json(json.loads(line)))
            except Exception as e:
                skipped += 1
                log.warning(f"{path}:{lineno}: skipping malformed row ({type(e).__name__}: {e})")
    return out, skipped
