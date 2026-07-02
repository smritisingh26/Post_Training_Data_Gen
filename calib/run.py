#!/usr/bin/env python3
"""
Calibration Pilot CLI.

  python -m calib.run generate            # stub-by-default, keyless, reproducible
  python -m calib.run generate --live     # uses NVIDIA_API_KEY + ANTHROPIC_API_KEY
  python -m calib.run eval-batch FILE.jsonl         # run the black-box harness on ANY batch
  python -m calib.run eval-batch FILE.jsonl --live  # + LLM judge layer (needs ANTHROPIC_API_KEY)

The eval-batch command is the deliverable harness: it runs on bare triples from
any source, including batches you did not generate -- rows with no `meta` at all,
or meta in a foreign vocabulary, are tolerated (labels default to "unknown" rather
than crashing the batch); a malformed row is skipped and logged, not fatal.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .pipeline import run, persist
from .schema import read_jsonl_lenient
from .harness import evaluate, summarize, make_llm_judge_hook

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")


def _load_cfg(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def cmd_generate(args):
    cfg = _load_cfg(args.config)
    rr = run(cfg, live=args.live)
    stats = persist(rr, cfg["pilot"]["out_dir"])
    print("\n=== GENERATION COMPLETE ===")
    print(f"mode: {'LIVE' if args.live else 'STUB (keyless, reproducible)'}")
    print(f"samples generated: {len(rr.samples)}")
    print(f"admitted to dataset: {stats['admitted']}")
    print(f"routed to negatives: {stats['negatives']}")
    print(f"routed to clean_solutions: {stats['clean_solutions']}")
    print(f"discarded: {stats['discarded']}")
    print(f"outputs in: {stats['out_dir']}/")
    print("\ntriage:")
    for t in rr.triage_log:
        print(f"  {t['id']:24} -> {t['class']:11} [{t['source']}] verifiable={t['verifiable']}")


def cmd_eval_batch(args):
    samples, n_skipped = read_jsonl_lenient(args.path)
    if n_skipped:
        print(f"[warn] skipped {n_skipped} malformed row(s) -- see log above")

    judge_hook = None
    if args.live:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            from .providers import AnthropicProvider
            cfg = _load_cfg(args.config)
            judge = AnthropicProvider(cfg["providers"]["judge_model"], anthropic_key)
            judge_hook = make_llm_judge_hook(judge)
            print(f"[info] llm judge layer: {judge.name}")
        else:
            print("[warn] --live set but ANTHROPIC_API_KEY unset -> running lexical-only")

    reports = [evaluate(s, judge_hook=judge_hook) for s in samples]
    print(json.dumps(summarize(reports), indent=2))
    for s, r in zip(samples, reports):
        fired = [sig.name for sig in r.signals if sig.flag]
        print(f"{s.id:34} route={r.route:9} fired={fired}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="calib.run")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="run the pilot generation pipeline")
    g.add_argument("--config", default="config.yaml")
    g.add_argument("--live", action="store_true", help="use real APIs (needs keys)")
    g.set_defaults(func=cmd_generate)

    e = sub.add_parser("eval-batch", help="run the black-box harness on a jsonl batch")
    e.add_argument("path")
    e.add_argument("--config", default="config.yaml")
    e.add_argument("--live", action="store_true",
                   help="also run the LLM judge layer (needs ANTHROPIC_API_KEY); "
                        "default stays fully keyless")
    e.set_defaults(func=cmd_eval_batch)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
