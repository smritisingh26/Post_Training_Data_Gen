"""
Provider interface. One abstraction, three concrete backends, selected by role.

Roles (see DESIGN.md §6):
  - solver / saboteur -> NIM (Llama 3.1 70B, error-prone-but-coherent, free tier)
  - judge / triage    -> Anthropic (Claude Sonnet 4.6, kept sharp for trustworthy labels)

Design decision (DESIGN.md §3): STUB-BY-DEFAULT. The whole pipeline runs end-to-end
with NO api keys, returning deterministic canned traces from a replay bank, so a
reviewer can reproduce everything. Passing --live (and setting keys) swaps in real calls.

NIM uses the OpenAI-compatible endpoint https://integrate.api.nvidia.com/v1 .
Anthropic uses the Messages API. Both are hidden behind .complete(system, user).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

log = logging.getLogger(__name__)


class Provider(Protocol):
    name: str
    def complete(self, system: str, user: str, temperature: float = 0.7,
                 max_tokens: int = 4096) -> str: ...


# --------------------------------------------------------------------------- #
# Live backends (only imported/constructed when --live and keys are present).  #
# They are thin on purpose; the pipeline logic never depends on which is used. #
# --------------------------------------------------------------------------- #

class NIMProvider:
    """OpenAI-compatible client pointed at NVIDIA's hosted endpoint."""
    def __init__(self, model: str, base_url: str, api_key: str):
        from openai import OpenAI  # imported lazily
        self.name = f"nim::{model}"
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, system, user, temperature=0.7, max_tokens=4096) -> str:
        r = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return r.choices[0].message.content


class AnthropicProvider:
    """Claude Messages API, used for the judge/triage roles."""
    def __init__(self, model: str, api_key: str):
        import anthropic  # imported lazily
        self.name = f"anthropic::{model}"
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system, user, temperature=0.2, max_tokens=4096) -> str:
        r = self._client.messages.create(
            model=self.model, system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return "".join(b.text for b in r.content if getattr(b, "type", None) == "text")


# --------------------------------------------------------------------------- #
# Stub backend: deterministic replay. Keyless. Used by default.               #
# --------------------------------------------------------------------------- #

class StubProvider:
    """
    Returns canned completions keyed by a tag the caller passes in the user prompt
    as a leading line 'STUB_KEY: <key>'. Falls back to an echo. This lets us run
    the *entire* control flow deterministically without any network.
    """
    def __init__(self, role: str, bank: dict[str, str]):
        self.name = f"stub::{role}"
        self._bank = bank

    def complete(self, system, user, temperature=0.0, max_tokens=4096) -> str:
        key = None
        for line in user.splitlines():
            if line.startswith("STUB_KEY:"):
                key = line.split("STUB_KEY:", 1)[1].strip()
                break
        if key and key in self._bank:
            return self._bank[key]
        return self._bank.get("__default__", "[stub] no canned response for this prompt")


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #

@dataclass
class ProviderConfig:
    solver_model: str
    judge_model: str
    nim_base_url: str
    saboteur_model: str


def make_providers(cfg: ProviderConfig, live: bool, stub_bank: dict[str, str]
                   ) -> tuple[Provider, Provider, Provider]:
    """Return (solver, judge, saboteur). Stub unless live=True and the relevant key is set."""
    if not live:
        return (StubProvider("solver", stub_bank), StubProvider("judge", stub_bank),
                StubProvider("saboteur", stub_bank))

    nim_key = os.environ.get("NVIDIA_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    solver = (NIMProvider(cfg.solver_model, cfg.nim_base_url, nim_key)
              if nim_key else StubProvider("solver", stub_bank))
    judge = (AnthropicProvider(cfg.judge_model, anthropic_key)
             if anthropic_key else StubProvider("judge", stub_bank))
    saboteur = (NIMProvider(cfg.saboteur_model, cfg.nim_base_url, nim_key)
                if nim_key else StubProvider("saboteur", stub_bank))

    if not nim_key:
        log.warning("NVIDIA_API_KEY unset -> solver falls back to stub")
        log.warning("NVIDIA_API_KEY unset -> saboteur falls back to stub")
    else:
        log.info(f"solver provider: {solver.name}")
        log.info(f"saboteur provider: {saboteur.name}")
    if not anthropic_key:
        log.warning("ANTHROPIC_API_KEY unset -> judge falls back to stub")
    else:
        log.info(f"judge provider: {judge.name}")
    return solver, judge, saboteur
