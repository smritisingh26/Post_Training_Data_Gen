"""
Orchestrator: one river, a fork (router), a shared gate.

Stage A triage -> Stage B route -> Stage C generate (opt1/opt2/opt3)
  -> Stage D harness = admission gate -> serialize (public + full).
Stage E (Adaptive Data finish) is a separate, optional, credit-metered step; see
docs/ADAPTIVE_DATA.md. It is not run here to avoid spending credits in the demo.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from .schema import Sample, ProblemClass, SelfCorrection, Track, write_jsonl
from .providers import ProviderConfig, make_providers
from .replay_bank import BANK
from .triage import triage, TriageResult
from .harness import evaluate, summarize, make_llm_judge_hook, HarnessReport
from .tracks import opt1_branch_repair, opt2_honest_completion, opt3_injection

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    samples: list[Sample]
    reports: list[HarnessReport]
    triage_log: list[dict]


def load_seeds(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def run(cfg: dict, live: bool) -> RunResult:
    pcfg = ProviderConfig(
        solver_model=cfg["providers"]["solver_model"],
        judge_model=cfg["providers"]["judge_model"],
        nim_base_url=cfg["providers"]["nim_base_url"],
        saboteur_model=cfg["providers"]["saboteur_model"],
    )
    solver, judge, saboteur = make_providers(pcfg, live=live, stub_bank=BANK)
    seeds = load_seeds(cfg["pilot"]["seeds_path"])
    log.info(f"loaded {len(seeds)} seeds (live={live}, solver={solver.name}, "
            f"judge={judge.name}, saboteur={saboteur.name})")

    samples: list[Sample] = []
    triage_log: list[dict] = []

    # ---- Stage A + B + C: triage, route, generate --------------------------
    n = len(seeds)
    for i, seed in enumerate(seeds, 1):
        log.info(f"[{i}/{n}] {seed['id']}: triaging")
        tr: TriageResult = triage(seed["instruction"], judge,
                                  stub_key=seed.get("triage_stub_key", "triage_default"))
        log.info(f"[{i}/{n}] {seed['id']}: triage -> class={tr.problem_class.value} "
                f"verifiable={tr.verifiable} source={tr.source}")
        triage_log.append({
            "id": seed["id"], "class": tr.problem_class.value,
            "verifiable": tr.verifiable, "source": tr.source,
            "obstruction": tr.obstruction,
        })

        if tr.problem_class == ProblemClass.SOLVABLE and seed.get("verifier"):
            log.info(f"[{i}/{n}] {seed['id']}: generating via opt1 (branch-repair)")
            s = opt1_branch_repair.generate(seed, solver, live=live)
            if s:
                samples.append(s)
                if live and s.meta.provenance.pre_correction_wrong is False:
                    log.info(f"[{i}/{n}] {seed['id']}: natural attempt was correct -> "
                            f"topping up genuine-correction yield via saboteur injection")
                    injected = opt3_injection.inject_and_repair(seed, s, solver, saboteur, live=live)
                    if injected:
                        samples.append(injected)
                        log.info(f"[{i}/{n}] {seed['id']}: injected-repair sample "
                                f"self_correction={injected.meta.self_correction.value}")
                    else:
                        log.warning(f"[{i}/{n}] {seed['id']}: injection top-up failed, skipping")
        else:
            log.info(f"[{i}/{n}] {seed['id']}: generating via opt2 (honest-completion)")
            s = opt2_honest_completion.generate(seed, solver, tr, live=live)
            samples.append(s)
        log.info(f"[{i}/{n}] {seed['id']}: done")

    # ---- Option 3: manufacture one labeled theatrical negative (honeypot) ---
    # Consumes an already-verified Option-1 sample as its base (DESIGN.md §3: opt3
    # is a booster, not an independent problem source).
    opt1_base = next((s for s in samples
                      if s.meta.track == Track.OPT1 and s.meta.provenance.verifier_passed), None)
    if opt1_base:
        log.info(f"generating opt3 theatrical negative (honeypot) from {opt1_base.id}")
        samples.append(opt3_injection.make_theatrical_negative(opt1_base, saboteur, live=live))
    else:
        log.warning("no verified opt1 sample available -> skipping opt3 theatrical negative")

    # ---- Stage D: harness = admission gate ---------------------------------
    # The LLM judge layer only runs live -- it needs a real judge model to be
    # meaningful, and evaluate() must stay keyless-capable by default for the
    # black-box eval-batch deliverable, so this is opt-in per call, not a
    # change to evaluate()'s own default behavior.
    judge_hook = make_llm_judge_hook(judge) if live else None
    log.info(f"running harness over {len(samples)} samples (llm_judge={'on' if live else 'off'})")
    reports = [evaluate(s, judge_hook=judge_hook) for s in samples]

    # ---- privileged post-pass: split "no correction" solvable-track samples -
    # by verified correctness. Uses Provenance.verifier_passed, which DESIGN.md
    # marks off-limits to the shared black-box evaluate() -- so this can only
    # live here (generation-time, privileged), never in harness.py. Verified
    # one-shot solves are a legitimate, deliberately-controlled "no correction
    # needed" pool distinct from dataset.jsonl (whose no-correction fraction is
    # OPT2's honest completions); an unverified/wrong "no correction" sample is
    # neither clean nor a self-correction demo, so it's discarded.
    #
    # Also intercepts route=="negatives" for self_correction==NONE: d2_theatrical's
    # text detector only looks at correction-marker density, not intent, so a
    # genuinely confused repair attempt that degenerates into repetitive rambling
    # can trip the same lexical signature as deliberate fake theater even though
    # nothing was ever claimed as a genuine correction. Since nothing was claimed,
    # "theatrical" is a category error for these -- the privileged verifier result
    # is authoritative here and overrides the black-box guess. Self-declared
    # theatrical honeypots are untouched: they carry self_correction==THEATRICAL,
    # not NONE, so they never match this first branch.
    #
    # A second, narrower case: self_correction==GENUINE (a REAL, verifier-confirmed
    # correction -- both tracks only ever set GENUINE when the verifier confirmed
    # the final answer) can still land in route=="negatives" if its explanation
    # happens to use grounding language outside harness.py's fixed keyword list.
    # Provably, this can only happen together with d1's genuine_correction_missing
    # also firing (d2 requires grounded==0 in response+thought combined, which is a
    # superset of d1's response-only check, so d2 firing implies d1's `present` is
    # False too) -- meaning the REAL problem is an explanation-quality issue, not
    # fabrication. Routing this to "negatives" would corrupt that pool's use for
    # calibrating the theatricality discriminator (DESIGN.md §8) with a non-theatrical
    # sample; "discard" reflects what's actually true: verifiably correct, but not
    # explained clearly enough to admit.
    for s, r in zip(samples, reports):
        if r.route not in ("dataset", "negatives") or s.meta.track not in (Track.OPT1, Track.OPT3):
            continue
        if s.meta.self_correction == SelfCorrection.NONE:
            if s.meta.provenance.verifier_passed:
                r.admit, r.route = True, "clean_solutions"
                r.reasons.append("no correction needed, verifier-confirmed correct -> clean_solutions pool")
            else:
                r.admit, r.route = False, "discard"
                r.reasons.append("no correction surfaced and NOT verifier-confirmed correct -> discard")
        elif s.meta.self_correction == SelfCorrection.GENUINE and r.route == "negatives":
            r.admit, r.route = False, "discard"
            r.reasons.append("verifier-confirmed genuine correction, but explanation didn't clearly "
                             "demonstrate grounding -> not fabricated (excluded from negatives), "
                             "not clearly explained enough for dataset -> discard")

    return RunResult(samples=samples, reports=reports, triage_log=triage_log)


def persist(rr: RunResult, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    admitted = [s for s, r in zip(rr.samples, rr.reports) if r.route == "dataset"]
    negatives = [s for s, r in zip(rr.samples, rr.reports) if r.route == "negatives"]
    clean_solutions = [s for s, r in zip(rr.samples, rr.reports) if r.route == "clean_solutions"]
    discards = [s for s, r in zip(rr.samples, rr.reports) if r.route == "discard"]

    write_jsonl(admitted, os.path.join(out_dir, "dataset.jsonl"), public=True)
    write_jsonl(admitted, os.path.join(out_dir, "dataset.full.jsonl"), public=False)
    write_jsonl(negatives, os.path.join(out_dir, "negatives.jsonl"), public=False)
    write_jsonl(clean_solutions, os.path.join(out_dir, "clean_solutions.jsonl"), public=False)
    write_jsonl(discards, os.path.join(out_dir, "discards.jsonl"), public=False)

    report_path = os.path.join(out_dir, "harness_report.json")
    with open(report_path, "w") as f:
        json.dump({
            "summary": summarize(rr.reports),
            "triage": rr.triage_log,
            "per_sample": [{
                "id": r.sample_id, "route": r.route, "admit": r.admit,
                "reasons": r.reasons,
                "signals": [{"name": s.name, "flag": s.flag, "evidence": s.evidence}
                            for s in r.signals],
            } for r in rr.reports],
        }, f, indent=2)

    return {
        "admitted": len(admitted),
        "negatives": len(negatives),
        "clean_solutions": len(clean_solutions),
        "discarded": len(discards),
        "out_dir": out_dir,
    }
