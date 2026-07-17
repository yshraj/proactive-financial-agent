#!/usr/bin/env python3
"""
CI guard: no interpolated SQL, no unscoped cache usage in product code.

Rules (backend/app only):

1. ``cursor.execute()`` / ``executemany()`` must not receive an f-string whose
   interpolations are anything other than UPPER_CASE module constants (e.g.
   ``ALERTS_WITH_CLIENT_SQL``). Dynamic fragments (joined column lists built
   from validated allowlists) must carry an explicit ``# sql-ok:`` comment
   explaining why they are safe.
2. Routers/services must use the tenant-scoped cache API. Direct calls to the
   unscoped primitives (``cache.get``/``set_``/``delete``/``delete_prefix``,
   or importing them under aliases) are only allowed inside services/cache.py
   and services/llm_extractor.py's scoped wrappers.

Exit code 1 with findings on violation.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# Files allowed to use the raw cache primitives.
_CACHE_PRIMITIVE_ALLOWLIST = {"services/cache.py"}
_UNSCOPED_CACHE_NAMES = {"get", "set_", "delete", "delete_prefix"}


def _is_constant_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id.isupper()


def _fstring_is_safe(node: ast.JoinedStr) -> bool:
    """f-string is safe when every interpolation is an UPPER_CASE constant."""
    for value in node.values:
        if isinstance(value, ast.FormattedValue) and not _is_constant_name(value.value):
            return False
    return True


def _line_has_sql_ok(source_lines: list[str], lineno: int) -> bool:
    """Look for a `# sql-ok` annotation on the call line or the two above."""
    for offset in (0, 1, 2):
        index = lineno - 1 - offset
        if 0 <= index < len(source_lines) and "# sql-ok" in source_lines[index]:
            return True
    return False


def check_file(path: Path) -> list[str]:
    source = path.read_text()
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - broken file fails elsewhere
        return [f"{path}: cannot parse: {exc}"]

    findings: list[str] = []
    rel = path.relative_to(APP_DIR).as_posix()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("execute", "executemany"):
            if node.args and isinstance(node.args[0], ast.JoinedStr):
                fstr = node.args[0]
                if not _fstring_is_safe(fstr) and not _line_has_sql_ok(
                    source_lines, node.lineno
                ):
                    findings.append(
                        f"{path}:{node.lineno}: f-string SQL with dynamic interpolation "
                        "(parameterize it, or annotate the call with `# sql-ok: <reason>`)"
                    )

    if rel not in _CACHE_PRIMITIVE_ALLOWLIST:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.services.cache":
                for alias in node.names:
                    if alias.name in _UNSCOPED_CACHE_NAMES:
                        findings.append(
                            f"{path}:{node.lineno}: imports unscoped cache primitive "
                            f"'{alias.name}' — use the *_scoped API (tenant isolation)"
                        )
    return findings


def main() -> int:
    findings: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        findings.extend(check_file(path))
    if findings:
        print("Tenancy/SQL guard failures:\n")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("SQL f-string + cache scoping guard: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
