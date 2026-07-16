"""Run restricted pre/post scripts in a disposable child process."""
from __future__ import annotations

import ast
import io
import multiprocessing
import re
from contextlib import redirect_stdout, suppress
from multiprocessing.connection import Connection, wait
from multiprocessing.process import BaseProcess
from typing import Any

_BLOCKED_PATTERNS = [
    r"\bimport\s+os\b",
    r"\bimport\s+subprocess\b",
    r"\bimport\s+sys\b",
    r"\bimport\s+shutil\b",
    r"\bfrom\s+os\b",
    r"\bfrom\s+subprocess\b",
    r"\bfrom\s+sys\b",
    r"\b__import__\b",
    r"\b__class__\b",
    r"\b__bases__\b",
    r"\b__subclasses__\b",
    r"\b__globals__\b",
    r"\b__builtins__\b",
    r"\b__mro__\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bopen\s*\(",
    r"\bcompile\s*\(",
    r"\bglobals\s*\(",
    r"\blocals\s*\(",
    r"\bgetattr\s*\(",
    r"\bsetattr\s*\(",
    r"\bdelattr\s*\(",
]
_BLOCKED_REGEX = re.compile("|".join(_BLOCKED_PATTERNS))

_SAFE_BUILTINS = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "any": any,
    "all": all,
    "type": type,
    "isinstance": isinstance,
    "print": print,
    "True": True,
    "False": False,
    "None": None,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
}


def _has_blocked_ast(script: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        return True, f"Script syntax error: {exc.msg} (line {exc.lineno})"

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return True, f"Script cannot access dunder attribute: {node.attr}"
    return False, ""


def _script_worker(
    script: str,
    context: dict[str, Any],
    result_connection: Connection,
) -> None:
    """Execute one script inside the child and send a single result payload."""
    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    namespace.update(context)
    output = io.StringIO()

    try:
        with redirect_stdout(output):
            exec(compile(script, "<pre_post_script>", "exec"), namespace)
        result = {
            "success": True,
            "output": output.getvalue(),
            "error": None,
            "variables": namespace.get(
                "variables",
                context.get("variables", {}),
            ),
        }
    except Exception as exc:  # noqa: BLE001
        result = {
            "success": False,
            "output": output.getvalue(),
            "error": f"{type(exc).__name__}: {exc}",
            "variables": namespace.get(
                "variables",
                context.get("variables", {}),
            ),
        }

    try:
        result_connection.send(result)
    except Exception as exc:  # noqa: BLE001
        fallback = {
            "success": False,
            "output": output.getvalue(),
            "error": f"Script result serialization failed: {type(exc).__name__}: {exc}",
            "variables": {},
        }
        with suppress(Exception):
            result_connection.send(fallback)
    finally:
        result_connection.close()


def _stop_process(process: BaseProcess) -> None:
    if process.is_alive():
        process.terminate()
        process.join(timeout=1)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1)


def run_script_in_subprocess(
    script: str,
    context: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Validate and execute a user script in a terminable spawned process."""
    if not script or not script.strip():
        return {"success": True, "output": "", "error": None}

    blocked, reason = _has_blocked_ast(script)
    if blocked:
        return {
            "success": False,
            "output": "",
            "error": f"Script security check failed: {reason}",
        }
    if _BLOCKED_REGEX.search(script):
        return {
            "success": False,
            "output": "",
            "error": "Script contains a blocked import, builtin, or attribute",
        }

    process_context = multiprocessing.get_context("spawn")
    result_connection, child_connection = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_script_worker,
        args=(script, context, child_connection),
        name="airetest-script",
        daemon=True,
    )

    try:
        process.start()
        child_connection.close()
    except Exception as exc:  # noqa: BLE001
        result_connection.close()
        child_connection.close()
        return {
            "success": False,
            "output": "",
            "error": f"Script process failed to start: {type(exc).__name__}: {exc}",
        }

    try:
        ready = wait(
            [result_connection, process.sentinel],
            timeout=max(float(timeout_seconds), 0.0),
        )
        if not ready:
            _stop_process(process)
            return {
                "success": False,
                "output": "",
                "error": f"Script execution timed out after {timeout_seconds} seconds",
                "variables": context.get("variables", {}),
            }

        if result_connection.poll():
            try:
                result = result_connection.recv()
            except EOFError:
                result = None
            process.join(timeout=1)
            if process.is_alive():
                _stop_process(process)
            if isinstance(result, dict):
                return result

        process.join(timeout=1)
        return {
            "success": False,
            "output": "",
            "error": (
                "Script process exited without a result"
                f" (exit code: {process.exitcode})"
            ),
            "variables": context.get("variables", {}),
        }
    finally:
        _stop_process(process)
        result_connection.close()
        process.close()
