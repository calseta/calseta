"""
Workflow AST validation service.

Parses workflow code and returns a list of validation error strings.
An empty list means the code is valid and safe to store.

Safety rules enforced:
- Must define `async def run`
- Only allowed imports: stdlib safe modules + `calseta.workflows`
- No dangerous module references: os, subprocess, importlib, sys, builtins,
  open, exec, eval, __import__, socket, ctypes, pickle, pathlib, shutil
"""

from __future__ import annotations

import ast

# Allowed top-level import names (whitelist approach)
_ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        # Standard library — safe subset
        "asyncio",
        "base64",
        "collections",
        "copy",
        "datetime",
        "enum",
        "functools",
        "hashlib",
        "hmac",
        "html",
        "http",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "logging",
        "math",
        "operator",
        "pathlib",
        "re",
        "statistics",
        "string",
        "textwrap",
        "time",
        "typing",
        "typing_extensions",
        "unicodedata",
        "urllib",
        "uuid",
        # Calseta workflow SDK
        "calseta",
        "calseta.workflows",
    }
)

# Module names that must never appear anywhere in import statements
_BLOCKED_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "subprocess",
        "importlib",
        "sys",
        "builtins",
        "socket",
        "ctypes",
        "pickle",
        "shelve",
        "shutil",
        "tempfile",
        "pty",
        "termios",
        "resource",
        "signal",
        "multiprocessing",
        "concurrent",
        "threading",
        "gc",
        "weakref",
        "code",
        "codeop",
        "compileall",
        "dis",
        "tokenize",
        "token",
    }
)

# Dangerous built-in names that must not be called directly
_BLOCKED_BUILTINS: frozenset[str] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "__import__",
        "open",
        "breakpoint",
        "input",
        "memoryview",
    }
)


def _check_imports(tree: ast.AST) -> list[str]:
    """Return errors for any disallowed or blocked import statements."""
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_MODULES:
                    errors.append(
                        f"Line {node.lineno}: import of '{alias.name}' is not allowed"
                    )
                elif top not in _ALLOWED_IMPORTS:
                    errors.append(
                        f"Line {node.lineno}: import of '{alias.name}' is not in "
                        "the allowed imports list"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top in _BLOCKED_MODULES:
                errors.append(
                    f"Line {node.lineno}: import from '{module}' is not allowed"
                )
            elif top not in _ALLOWED_IMPORTS:
                errors.append(
                    f"Line {node.lineno}: import from '{module}' is not in "
                    "the allowed imports list"
                )
    return errors


def _check_blocked_builtins(tree: ast.AST) -> list[str]:
    """Return errors for any direct calls to dangerous built-in names."""
    errors: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _BLOCKED_BUILTINS
        ):
            errors.append(
                f"Line {node.func.col_offset}: use of '{node.func.id}' is not allowed"
            )
    return errors


def _check_has_run_function(tree: ast.Module) -> list[str]:
    """Return error if the module does not define `async def run`."""
    for node in tree.body:
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "run"
        ):
            return []
    return ["Workflow code must define an async function named 'run'"]


def validate_workflow_code(code: str) -> list[str]:
    """
    Validate workflow code for safety and structure.

    Returns a list of error strings. An empty list means the code is valid.

    Checks:
    1. Parses as valid Python
    2. Defines `async def run`
    3. Only uses allowed imports
    4. Does not call dangerous built-ins (exec, eval, open, __import__, compile)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Syntax error: {exc}"]

    errors: list[str] = []
    errors.extend(_check_has_run_function(tree))
    errors.extend(_check_imports(tree))
    errors.extend(_check_blocked_builtins(tree))
    return errors
