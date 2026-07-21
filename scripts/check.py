#!/usr/bin/env python3
"""Run the repository's offline verification gates."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
from collections.abc import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(name: str, command: Sequence[str], *, env: dict[str, str]) -> None:
    print(f"\n==> {name}", flush=True)
    print("$ " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    if result.returncode:
        print(
            f"FAILED: {name} (exit code {result.returncode})",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(result.returncode)
    print(f"PASS: {name}", flush=True)


def git_output(*args: str, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        print(
            f"FAILED: git {' '.join(args)} (exit code {result.returncode})",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def verify_repository_root(env: dict[str, str]) -> None:
    print("\n==> Git repository root", flush=True)
    reported_root = Path(git_output("rev-parse", "--show-toplevel", env=env)).resolve()
    if reported_root != REPO_ROOT.resolve():
        raise SystemExit(
            f"FAILED: expected repository root {REPO_ROOT}, got {reported_root}"
        )
    print(f"PASS: repository root is {reported_root}", flush=True)


def tracked_python_files(env: dict[str, str]) -> list[Path]:
    output = git_output("ls-files", "--", "*.py", env=env)
    paths = [REPO_ROOT / line for line in output.splitlines() if line]
    this_script = Path(__file__).resolve()
    if this_script not in {path.resolve() for path in paths}:
        paths.append(this_script)
    return sorted(paths)


def verify_python_syntax(env: dict[str, str]) -> None:
    print("\n==> Tracked Python syntax", flush=True)
    paths = tracked_python_files(env)
    if not paths:
        raise SystemExit("FAILED: no Python files were found by git ls-files")
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8-sig")
            ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise SystemExit(f"FAILED: Python syntax check for {path}: {exc}") from exc
    print(f"PASS: parsed {len(paths)} Python files", flush=True)


def main() -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    print(f"Python: {sys.version.splitlines()[0]}", flush=True)
    verify_repository_root(env)
    verify_python_syntax(env)

    run_command(
        "Full test suite (includes the standard suite)",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests",
            "image-to-description/test_image_description.py",
        ],
        env=env,
    )
    run_command(
        "Installed dependency consistency",
        [sys.executable, "-m", "pip", "check"],
        env=env,
    )
    run_command("Working-tree whitespace", ["git", "diff", "--check"], env=env)
    run_command(
        "Staged whitespace", ["git", "diff", "--cached", "--check"], env=env
    )
    run_command(
        "HEAD delta whitespace",
        ["git", "diff", "--check", "HEAD^", "HEAD"],
        env=env,
    )

    print("\nAll repository checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
