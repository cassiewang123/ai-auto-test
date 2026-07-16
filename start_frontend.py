"""Start only the local Vite frontend without Docker."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def resolve_node() -> Path:
    configured = os.getenv("AIRETEST_NODE")
    candidates = [
        Path(configured) if configured else None,
        Path(shutil.which("node") or ""),
        Path(r"E:\wxlsoft\node22\node-v22.12.0-win-x64\node.exe"),
    ]

    try:
        import playwright

        candidates.append(
            Path(playwright.__file__).resolve().parent / "driver" / "node.exe"
        )
    except ImportError:
        pass

    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise SystemExit(
        "Node.js was not found. Install Node.js 22+ or set AIRETEST_NODE."
    )


def main() -> None:
    project_root = Path(__file__).resolve().parent
    frontend_dir = project_root / "frontend"
    vite_entry = frontend_dir / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite_entry.is_file():
        raise SystemExit(
            "frontend/node_modules is missing. Run npm ci in frontend first."
        )

    subprocess.run(
        [
            str(resolve_node()),
            str(vite_entry),
            "--host",
            "127.0.0.1",
            "--port",
            "5173",
            "--strictPort",
        ],
        cwd=frontend_dir,
        check=True,
    )


if __name__ == "__main__":
    main()
