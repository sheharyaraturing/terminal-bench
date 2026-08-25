"""The oracle runner. GENERATED — do not edit a task's copy.

`tasks/new_task.py runner <task>` copies this file to the task's
solution/oracle_runner.py, and `lint` fails a task whose copy has drifted.
Fix bugs here, then regenerate.

Harbor uploads solution/ wholesale to /solution, so solve.sh runs this module
and Python finds solve.py beside it.

This runner is task-agnostic. It knows two step kinds and nothing about excel,
word or workbooks: every tool call, with its real gateway name and its real
arguments, is written out in solution/manifest.json.

    {"steps": [
      {"do": "call", "tool": "word-get_document_text",
       "args": {"filename": "$ws/policy/M.docx"}, "name": "manual"},
      {"do": "solve", "name": "route"},
      {"do": "call", "tool": "excel-write_data_to_excel",
       "args": {"filepath": "$ws/log.xlsx", "sheet_name": "Routing",
                "data": {"$": "rows"}, "start_cell": "A1"}}
    ]}

    do: call    invoke `tool` with `args`. `$ws` in any string becomes the
                workspace path. `{"$": "x"}` becomes the value bound to x.
                With `name`, the result is bound under that name; `parse`
                decodes it first - "text" (default), "json", or "repr" for the
                Python-repr some servers return.
    do: solve   run the function `name` from solve.py. It receives everything
                bound so far and returns a dict whose keys join the pool. Two
                solves may not bind the same key.

A task needing no computation ships manifest.json alone.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import pathlib
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

GATEWAY_URL = os.environ.get("ORACLE_GATEWAY_URL", "http://127.0.0.1:8765/sse")


class ToolError(RuntimeError):
    """A tool errored, returned a failure, or returned something unparseable."""


class Gateway:
    """A session against the container's tool gateway, with a call log."""

    def __init__(self, session: ClientSession, names: set[str]) -> None:
        self._session = session
        self._names = names
        self.calls: list[str] = []

    async def call(self, tool: str, arguments: dict[str, Any]) -> str:
        if tool not in self._names:
            raise ToolError(
                f"the gateway does not expose {tool!r}; it published "
                f"{len(self._names)} tools, e.g. {sorted(self._names)[:5]}"
            )
        self.calls.append(tool)
        print(f"[{len(self.calls):02d}] {tool} {_brief(arguments)}", file=sys.stderr)

        result = await self._session.call_tool(tool, arguments)
        text = "".join(
            part.text for part in result.content if getattr(part, "type", None) == "text"
        )
        if result.isError:
            raise ToolError(f"{tool} failed: {text}")
        # Some servers report a typed failure as an ordinary successful return,
        # so isError alone would let a failed write through silently.
        if text.startswith("Error:"):
            raise ToolError(f"{tool} returned a failure: {text.splitlines()[0]}")
        return text


def _brief(arguments: dict[str, Any]) -> str:
    parts = []
    for key, value in arguments.items():
        if isinstance(value, list):
            shown = f"[{len(value)} rows]" if value and isinstance(value[0], list) else f"[{len(value)}]"
        else:
            shown = str(value)
            if len(shown) > 60:
                shown = shown[:57] + "..."
        parts.append(f"{key}={shown}")
    return " ".join(parts)


def _resolve(value: Any, ws: str, bound: dict, where: str) -> Any:
    """Substitute $ws and {"$": name} references through an argument tree."""
    if isinstance(value, str):
        return value.replace("$ws", ws)
    if isinstance(value, list):
        return [_resolve(v, ws, bound, where) for v in value]
    if isinstance(value, dict):
        if set(value) == {"$"}:
            key = value["$"]
            if key not in bound:
                raise ToolError(f"{where} references {key!r}, which nothing has bound "
                                f"(available: {sorted(bound)})")
            return bound[key]
        return {k: _resolve(v, ws, bound, where) for k, v in value.items()}
    return value


def _decode(text: str, how: str, where: str) -> Any:
    if how == "text":
        return text
    if how == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolError(f"{where}: result is not JSON: {text[:200]!r}") from exc
    if how == "repr":
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            raise ToolError(f"{where}: result is not a Python literal: {text[:200]!r}") from exc
    raise ToolError(f"{where}: unknown parse {how!r}; use text, json or repr")


_SOLVE = None


def _solve_fn(name: str, step_no: int):
    """The function a solve step runs, from solution/solve.py."""
    global _SOLVE
    if _SOLVE is None:
        import importlib.util

        path = pathlib.Path(__file__).resolve().parent / "solve.py"
        if not path.is_file():
            raise ToolError(f"step {step_no} solves, but there is no {path}")
        spec = importlib.util.spec_from_file_location("solve", path)
        _SOLVE = importlib.util.module_from_spec(spec)
        sys.modules["solve"] = _SOLVE
        spec.loader.exec_module(_SOLVE)

    fn = getattr(_SOLVE, name, None)
    if not callable(fn):
        offered = sorted(
            k for k, v in vars(_SOLVE).items()
            if inspect.isfunction(v) and v.__module__ == "solve" and not k.startswith("_")
        )
        raise ToolError(f"step {step_no} asks for solve function {name!r}; solve.py defines {offered}")
    return fn


def _taken(step: dict, key: str, i: int):
    try:
        return step[key]
    except KeyError:
        raise ToolError(f"step {i} ({step.get('do')}) needs {key!r}") from None


@asynccontextmanager
async def _connect(url: str = GATEWAY_URL):
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            servers = sorted({n.partition("-")[0] for n in names if "-" in n})
            print(f"gateway published {len(names)} tools from {len(servers)} "
                  f"servers: {', '.join(servers)}", file=sys.stderr)
            # A server that failed to connect is not otherwise detectable here:
            # the gateway's /health answers ok whatever came up, and a task whose
            # oracle happens not to call the missing one would still pass.
            declared = [s.strip() for s in os.environ.get("MCP_SERVERS", "").split(",") if s.strip()]
            missing = [s for s in declared if s not in servers]
            if missing:
                raise ToolError(
                    f"task declares MCP_SERVERS={','.join(declared)} but the gateway "
                    f"published only {', '.join(servers)}; missing {', '.join(missing)}")
            yield Gateway(session, names)


async def _run(manifest: dict, ws: str) -> None:
    async with _connect() as gw:
        bound: dict = {}
        for i, step in enumerate(manifest["steps"], 1):
            do = step.get("do")
            if do == "call":
                tool = _taken(step, "tool", i)
                args = _resolve(step.get("args", {}), ws, bound, f"step {i} ({tool})")
                if not isinstance(args, dict):
                    raise ToolError(f"step {i} ({tool}): args must be an object")
                text = await gw.call(tool, args)
                if "name" in step:
                    bound[step["name"]] = _decode(
                        text, step.get("parse", "text"), f"step {i} ({tool})")
            elif do == "solve":
                name = _taken(step, "name", i)
                fn = _solve_fn(name, i)
                out = fn(bound)
                if not isinstance(out, dict):
                    raise ToolError(
                        f"step {i}: {fn.__name__}() must return a dict, got {type(out).__name__}")
                clash = sorted(set(out) & set(bound))
                if clash:
                    raise ToolError(f"step {i} re-binds {clash}, already bound")
                bound.update(out)
            else:
                raise ToolError(f"step {i} has unknown action {do!r}; use call or solve")
        print(f"{len(gw.calls)} tool calls", file=sys.stderr)


def load_manifest() -> dict:
    """solution/manifest.json, which ships beside this module at /solution."""
    path = pathlib.Path(__file__).resolve().parent / "manifest.json"
    if not path.is_file():
        raise ToolError(f"no manifest at {path}")
    manifest = json.loads(path.read_text())
    if not isinstance(manifest.get("steps"), list) or not manifest["steps"]:
        raise ToolError(f"{path} has no non-empty 'steps' list")
    return manifest


def main() -> None:
    """Entry point: solve.sh runs this module directly."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    asyncio.run(_run(load_manifest(), ap.parse_args().workspace.rstrip("/")))


if __name__ == "__main__":
    main()
