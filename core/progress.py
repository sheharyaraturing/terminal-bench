"""Progress reporting and cancellation for a single review run.

A RunControl is threaded through the pipeline legs so they can report what they
are doing while they do it, and so a long review can be stopped from outside.
"""
from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class RunCancelled(Exception):
    """Raised inside a leg when the run has been cancelled."""


@dataclass
class RunControl:
    """Progress sink plus a kill switch for the processes a run spawns."""

    on_progress: Callable[[str], None] | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    _processes: list[subprocess.Popen] = field(default_factory=list)
    _containers: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, message: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(message)
            except Exception:
                pass  # progress reporting must never break a run

    def raise_if_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise RunCancelled("run cancelled")

    def register_process(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._processes.append(proc)

    def register_container(self, name: str) -> None:
        with self._lock:
            if name not in self._containers:
                self._containers.add(name)
                self.emit(f"container up: {name}")

    def cancel(self) -> None:
        """Stop the run: kill spawned processes and their containers."""
        self.cancelled.set()
        self.emit("cancellation requested")
        with self._lock:
            processes, containers = list(self._processes), list(self._containers)

        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

        # harbor tears its compose project down on a clean finish, but not when
        # it is killed mid-run: both the container and its network survive.
        from .docker_cleanup import teardown_container

        for name in containers:
            for removed in teardown_container(name):
                self.emit(f"removed {removed}")


def describe_agent_event(line: str) -> str | None:
    """Turn one claude-code stream-json line into a short progress message.

    Returns None for lines that carry nothing worth showing.
    """
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        event = json.loads(line)
    except Exception:
        return None

    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        return f"agent started (model={event.get('model', '?')})"

    if etype == "assistant":
        parts: list[str] = []
        for block in event.get("message", {}).get("content", []) or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                parts.append(f"tool: {block.get('name', '?')} {_tool_target(block)}".rstrip())
            elif block.get("type") == "text":
                text = " ".join((block.get("text") or "").split())
                if text:
                    parts.append(f"agent: {text[:160]}")
        return " | ".join(parts) if parts else None

    if etype == "result":
        cost = event.get("total_cost_usd")
        suffix = f" (cost ${cost:.4f})" if isinstance(cost, (int, float)) and cost else ""
        if event.get("is_error"):
            return f"agent finished with an error: {str(event.get('result', ''))[:160]}"
        return f"agent finished{suffix}"

    return None


def _tool_target(block: dict) -> str:
    """The most useful single field from a tool_use input, for one-line output."""
    data = block.get("input") or {}
    if not isinstance(data, dict):
        return ""
    for key in ("file_path", "path", "command", "pattern", "url"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return " ".join(value.split())[:120]
    return ""


def _read_new_lines(path: Path, offsets: dict[Path, int]) -> list[str]:
    """Lines appended to `path` since the last call. Partial lines are held back."""
    try:
        data = path.read_bytes()
    except OSError:
        return []
    start = offsets.get(path, 0)
    if len(data) <= start:
        return []
    chunk = data[start:].decode(errors="replace")
    if not chunk.endswith("\n"):
        cut = chunk.rfind("\n")
        if cut == -1:
            return []
        chunk = chunk[: cut + 1]
    offsets[path] = start + len(chunk.encode())
    return chunk.splitlines()


# trial.log echoes the agent invocation verbatim, and that command embeds the
# entire evaluator prompt and JSON schema — hundreds of lines. Only lines
# starting with one of these prefixes are worth surfacing; everything else is
# that dump and would drown the log.
_TRIAL_PREFIXES = (
    "Running command:",
    "Uploading",
    "Downloading",
    "Building",
    "Pulling",
    "Starting",
    "Stopping",
    "Verifier",
    "Agent ",
    "Trial ",
)


def _describe_setup_line(line: str) -> str | None:
    """Condense a harbor trial.log line into something worth printing."""
    line = " ".join(line.split())
    if not line or not line.startswith(_TRIAL_PREFIXES):
        return None
    # The setup phase runs long shell one-liners; show the intent, not the script.
    if line.startswith("Running command:"):
        command = line[len("Running command:") :].strip()
        if "claude-code" in command or "claude --version" in command:
            return "setup: installing the claude-code agent in the container"
        if "apt-get" in command or "apk add" in command or "yum install" in command:
            return "setup: installing container packages"
        if command.startswith("export PATH") and "claude" in command:
            return "agent: starting the evaluator (this is the long part)"
        return f"setup: {command[:120]}"
    return f"trial: {line[:160]}"


def tail_trial_logs(
    jobs_dir: Path,
    control: RunControl,
    stop: threading.Event,
    interval: float = 2.0,
) -> None:
    """Follow harbor's trial logs while a check runs.

    harbor bind-mounts the container's /logs into <trial_dir>/, so both files
    below appear on the host and grow live — no docker exec needed:

      <trial_dir>/trial.log        setup progress (the long part: installing
                                   node and the agent inside the container)
      <trial_dir>/agent/*.txt      the agent's stream-json, once it starts
    """
    offsets: dict[Path, int] = {}
    while not stop.is_set():
        for log_path in sorted(jobs_dir.rglob("trial.log")):
            for line in _read_new_lines(log_path, offsets):
                message = _describe_setup_line(line)
                if message:
                    control.emit(f"  {message}")
        for log_path in sorted(jobs_dir.rglob("agent/*.txt")):
            for line in _read_new_lines(log_path, offsets):
                message = describe_agent_event(line)
                if message:
                    control.emit(f"  {message}")
        stop.wait(interval)


def watch_containers(
    name_fragment: str,
    control: RunControl,
    stop: threading.Event,
    interval: float = 3.0,
) -> None:
    """Record the containers a run creates so cancellation can remove them."""
    while not stop.is_set():
        try:
            proc = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for name in proc.stdout.splitlines():
                if name_fragment in name:
                    control.register_container(name)
        except Exception:
            pass
        stop.wait(interval)
