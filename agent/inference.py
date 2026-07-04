"""Provider-blind inference seam (salvaged from the mesh-era orchestrator).

This thin CLI-on-PATH adapter IS the inference boundary (BRIEF §4 / [H5]). It is *less*
locked-in than adopting an SDK as the loop: the Anthropic Agent SDK, if wanted, goes behind
this seam as one provider — never replacing it. BYO inference stays free, forever.

Providers:
  - "claude"   (default): the locally-authenticated `claude` CLI — BYO Claude, no API key.
  - "opencode": provider-neutral — bring ANY model (Anthropic/OpenAI/Gemini/OpenRouter) or a
                FREE local model via Ollama. Selected with $LUDWIG_PROVIDER.
Model tiering ([H5], BRIEF §5): the LOOP reads `standards.yaml: inference.codegen_tier`
and `critic_tier` and passes `model=` accordingly. You can also pass `model=` directly
to override tier selection. Tier names are provider-specific (e.g. "sonnet" for claude,
"anthropic/claude-sonnet-4-6" for opencode).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

# Signatures of a provider rate/usage/session limit (vs a plain transient error). A throttle is not a
# codegen failure — it is the measurement apparatus, not Ludwig, saying "slow down". We back off *longer*
# on these so a single transient limit self-heals instead of bubbling up as an empty program (which the
# eval would otherwise miscount as a geometry miss — the A4 throttling artifact, FINDINGS 2026-07-04).
_THROTTLE_RE = re.compile(
    r"rate.?limit|429|overloaded|usage limit|quota|too many requests|try again|"
    r"capacity|throttl|please wait|resource_exhausted",
    re.IGNORECASE,
)


def _run_cli(cmd: list[str], *, timeout: int, retries: int, who: str) -> str:
    """Run an inference CLI headlessly with retry/backoff on transient failures.

    Rate/usage limits get a longer, throttle-aware backoff (base 8s, capped) so a burst of sequential
    calls — an eval batch, a repair storm — rides out the limit window instead of failing hard.
    """
    last = ""
    for attempt in range(retries + 1):
        throttled = False
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
            last = proc.stderr.strip() or "empty response"
            throttled = bool(_THROTTLE_RE.search(proc.stderr or ""))
        except FileNotFoundError:
            raise RuntimeError(f"{who} not found on PATH")
        except subprocess.TimeoutExpired:
            last = f"timed out after {timeout}s"
        if attempt < retries:
            # throttle: 8s, 16s, 24s … (spaced across the limit window); plain transient: 1s, 2s, 4s.
            time.sleep(min(8 * (attempt + 1), 60) if throttled else 2 ** attempt)
    raise RuntimeError(f"{who} failed after {retries + 1} attempts: {last}")


def _provider_claude(prompt, *, allow_read, image, timeout, retries, model):  # noqa: ARG001
    cmd = ["claude"]
    if model:
        cmd += ["--model", model]          # optional tier override (opus/sonnet/haiku/…)
    cmd += ["-p", prompt]
    if allow_read:
        cmd += ["--allowedTools", "Read"]  # lets the (demoted) vision critic view a render
    return _run_cli(cmd, timeout=timeout, retries=retries, who="the `claude` CLI")


def _provider_opencode(prompt, *, allow_read, image, timeout, retries, model):  # noqa: ARG001
    cmd = ["opencode", "run"]
    model = model or os.environ.get("LUDWIG_MODEL")   # provider/model, e.g. anthropic/claude-sonnet-4-6
    if model:
        cmd += ["-m", model]
    if image:
        cmd += ["-f", image]
    cmd.append(prompt)
    return _run_cli(cmd, timeout=timeout, retries=retries, who="the `opencode` CLI")


_PROVIDERS = {"claude": _provider_claude, "opencode": _provider_opencode}
PROVIDER_BIN = {"claude": "claude", "opencode": "opencode"}


def provider_name() -> str:
    return os.environ.get("LUDWIG_PROVIDER", "claude")


def infer(prompt: str, *, allow_read: bool = False, image: str | None = None,
          timeout: int = 240, retries: int = 2, model: str | None = None) -> str:
    """Provider-agnostic inference call. Dispatches to the selected backend.

    Args:
        prompt: The prompt text to send.
        model: Optional model name override. The LOOP sets this from standards.yaml tier
               config; you can also pass it directly to force a specific model.
               If None, the provider's default model is used.
    """
    name = provider_name()
    fn = _PROVIDERS.get(name)
    if fn is None:
        sys.exit(f"Unknown inference provider {name!r}. Choose one of: {', '.join(_PROVIDERS)}")
    return fn(prompt, allow_read=allow_read, image=image,
              timeout=timeout, retries=retries, model=model)
