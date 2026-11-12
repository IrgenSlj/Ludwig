"""The model call: a command the operator configures, prompt on stdin, answer on stdout.

Any provider fits behind a command (a hosted model's CLI, an EU-hosted endpoint wrapper,
a local model through Ollama), so no SDK becomes a dependency. Unset means assist is off,
and nothing is sent anywhere.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

MAX_PROMPT_CHARS = 60_000


class AssistOff(RuntimeError):
    """Assist is not configured."""


class AssistFailed(RuntimeError):
    """The model command failed or gave nothing."""


@dataclass(frozen=True)
class CommandProvider:
    """Runs `command` with the prompt on stdin."""

    command: str
    timeout: int = 120

    def complete(self, prompt: str) -> str:
        """The model's answer to one prompt."""
        if len(prompt) > MAX_PROMPT_CHARS:
            raise AssistFailed(f"prompt too long ({len(prompt)} characters)")
        try:
            proc = subprocess.run(shlex.split(self.command), input=prompt, capture_output=True,
                                  text=True, timeout=self.timeout, check=False)  # fmt: skip
        except FileNotFoundError:
            raise AssistFailed(f"assist command not found: {self.command.split()[0]}") from None
        except subprocess.TimeoutExpired:
            raise AssistFailed(f"assist command timed out after {self.timeout}s") from None
        if proc.returncode != 0 or not proc.stdout.strip():
            detail = (proc.stderr or "no output").strip().splitlines()[-1:] or ["no output"]
            raise AssistFailed(f"assist command failed: {detail[0][:300]}")
        return proc.stdout.strip()


def from_env() -> CommandProvider | None:
    """LUDWIG_ASSIST_COMMAND (e.g. `claude -p` or `ollama run llama3.1`); None when unset."""
    command = os.environ.get("LUDWIG_ASSIST_COMMAND", "").strip()
    if not command:
        return None
    return CommandProvider(command, int(os.environ.get("LUDWIG_ASSIST_TIMEOUT", "120")))
