"""Unit tests. Run: python -m pytest tests/ -q   (or python tests/test_all.py)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calib.verifier import build_verifier
from calib.triage import _registry_check
from calib.schema import (Sample, Meta, Provenance, ProblemClass, SelfCorrection, Track)
from calib.harness import evaluate, d2_theatrical, d3_fabricated_rigor, d1_genuine_correction


# ---- verifier --------------------------------------------------------------

def test_verifier_catches_inclusion_exclusion_error():
    v = build_verifier({"kind": "counting", "lo": 1, "hi": 1000, "rule": "div3or5"})
    assert v.ground_truth() == 467
    assert v.check(533).correct is False      # naive double-count
    assert v.check(467).correct is True       # fixed

def test_symbolic_verifier():
    v = build_verifier({"kind": "symbolic", "truth": "467"})
    assert v.check("333+200-66").correct is True
    assert v.check("333+200").correct is False


# ---- triage registry -------------------------------------------------------

def test_registry_flags_known_impossibles():
    assert _registry_check("Prove the Riemann Hypothesis").problem_class == ProblemClass.IMPOSSIBLE
    assert _registry_check("exact closed-form 3-body solution").problem_class == ProblemClass.IMPOSSIBLE

def test_registry_defers_solvable_reduction():
    # Navier-Stokes slit flow must NOT be caught by the registry (LLM decides)
    assert _registry_check("Derive the Navier-Stokes solutions for a microfluidic channel") is None
    assert _registry_check("How many integers from 1 to 1000 are divisible by 3 or 5?") is None


# ---- harness detectors -----------------------------------------------------

def _mk(instruction, thought, response, pc, sc, track=Track.OPT1, **mkw):
    return Sample("t", instruction, thought, response,
                  Meta(problem_class=pc, self_correction=sc, track=track, **mkw))

def test_theatrical_detected():
    s = _mk("count", "", "We get 467. Wait, actually let me reconsider. Hmm, no, it's fine. 467.",
            ProblemClass.SOLVABLE, SelfCorrection.THEATRICAL)
    assert d2_theatrical(s).flag is True
    rep = evaluate(s)
    assert rep.route == "negatives"

def test_genuine_correction_passes():
    resp = ("We count integers from 1 to 1000 divisible by 3 or 5. Multiples of 3 number "
            "333, and multiples of 5 number 200. Adding gives 533, but that step doesn't "
            "hold: multiples of 15 are double-counted, since they appear in both groups. "
            "There are 66 multiples of 15, so subtract them to correct the overcount: "
            "333 + 200 - 66 = 467.")
    s = _mk("count", "", resp, ProblemClass.SOLVABLE, SelfCorrection.GENUINE,
            correction_is_grounded=True)
    assert d1_genuine_correction(s).flag is False
    assert evaluate(s).admit is True

def test_grounded_anchor_alone_counts_as_surfaced():
    # response uses grounded language ("overcounts / counted twice") without a stock marker
    resp = "Adding gives 116, but that overcounts multiples of 77 counted twice, so 110."
    s = _mk("count", "", resp, ProblemClass.SOLVABLE, SelfCorrection.GENUINE,
            correction_is_grounded=True)
    assert d1_genuine_correction(s).flag is False

def test_fabricated_rigor_on_impossible():
    s = _mk("Prove RH", "", "Therefore this completes the proof. QED.",
            ProblemClass.IMPOSSIBLE, SelfCorrection.NONE, track=Track.OPT2)
    assert d3_fabricated_rigor(s).flag is True
    assert evaluate(s).admit is False

def test_honest_completion_on_impossible_passes():
    resp = ("The Riemann Hypothesis is an open problem; no proof is known, despite over a "
            "century of effort. The strongest correct claim available here is a numerical "
            "verification for a finite range of zeros -- checking that a given zero lies on "
            "the critical line to high precision -- which is not a proof of the general "
            "hypothesis and does not generalize beyond the checked range.")
    s = _mk("Prove RH", "", resp, ProblemClass.IMPOSSIBLE, SelfCorrection.NONE, track=Track.OPT2)
    assert d3_fabricated_rigor(s).flag is False
    assert evaluate(s).admit is True


# ---- schema round-trip -----------------------------------------------------

def test_schema_roundtrip_and_public_strips_provenance():
    s = _mk("q", "t", "r", ProblemClass.SOLVABLE, SelfCorrection.GENUINE,
            provenance=Provenance(verifier="counting::x", verifier_passed=True))
    assert "provenance" in s.to_json()["meta"]
    assert "provenance" not in s.to_public_json()["meta"]
    s2 = Sample.from_json(s.to_json())
    assert s2.meta.problem_class == ProblemClass.SOLVABLE
    assert s2.meta.provenance.verifier == "counting::x"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}"); passed += 1
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
