"""Unit tests for app/services/workflow_ast.py."""

from __future__ import annotations

import pytest

from app.services.workflow_ast import validate_workflow_code

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_VALID_CODE = """\
async def run(ctx):
    return ctx
"""


def _has_error_containing(errors: list[str], fragment: str) -> bool:
    return any(fragment in e for e in errors)


# ---------------------------------------------------------------------------
# Valid code
# ---------------------------------------------------------------------------


def test_valid_minimal_code_passes() -> None:
    errors = validate_workflow_code(_VALID_CODE)
    assert errors == []


def test_valid_code_with_allowed_imports_passes() -> None:
    code = """\
import json
import re
from datetime import datetime
from typing import Any

async def run(ctx):
    data = json.dumps({"ts": str(datetime.now())})
    return data
"""
    errors = validate_workflow_code(code)
    assert errors == []


def test_valid_code_with_calseta_import_passes() -> None:
    code = """\
from calseta.workflows import WorkflowResult

async def run(ctx):
    return WorkflowResult(success=True, message="ok", data={})
"""
    errors = validate_workflow_code(code)
    assert errors == []


# ---------------------------------------------------------------------------
# Missing async def run
# ---------------------------------------------------------------------------


def test_missing_run_function_returns_error() -> None:
    code = """\
def not_run(ctx):
    return ctx
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "async function named 'run'")


def test_sync_run_is_not_valid() -> None:
    code = """\
def run(ctx):
    return ctx
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "async function named 'run'")


def test_empty_code_returns_error() -> None:
    errors = validate_workflow_code("")
    assert _has_error_containing(errors, "async function named 'run'")


# ---------------------------------------------------------------------------
# Blocked imports
# ---------------------------------------------------------------------------


def test_import_os_returns_error() -> None:
    code = """\
import os

async def run(ctx):
    return os.getcwd()
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'os'")


def test_import_subprocess_returns_error() -> None:
    code = """\
import subprocess

async def run(ctx):
    return subprocess.run(["ls"])
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'subprocess'")


def test_import_sys_returns_error() -> None:
    code = """\
import sys

async def run(ctx):
    return sys.argv
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'sys'")


def test_import_importlib_returns_error() -> None:
    code = """\
import importlib

async def run(ctx):
    return importlib.import_module("os")
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'importlib'")


def test_import_socket_returns_error() -> None:
    code = """\
import socket

async def run(ctx):
    return socket.gethostname()
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'socket'")


def test_from_os_import_returns_error() -> None:
    code = """\
from os import path

async def run(ctx):
    return path.exists("/tmp")
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'os'")


def test_unknown_import_returns_error() -> None:
    code = """\
import requests

async def run(ctx):
    return requests.get("https://example.com")
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'requests'")


# ---------------------------------------------------------------------------
# Blocked builtins
# ---------------------------------------------------------------------------


def test_exec_call_returns_error() -> None:
    code = """\
async def run(ctx):
    exec("import os")
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'exec'")


def test_eval_call_returns_error() -> None:
    code = """\
async def run(ctx):
    result = eval("1 + 1")
    return result
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'eval'")


def test_open_call_returns_error() -> None:
    code = """\
async def run(ctx):
    with open("/etc/passwd") as f:
        return f.read()
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'open'")


def test_compile_call_returns_error() -> None:
    code = """\
async def run(ctx):
    code = compile("1+1", "<string>", "eval")
    return code
"""
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "'compile'")


# ---------------------------------------------------------------------------
# Syntax errors
# ---------------------------------------------------------------------------


def test_syntax_error_returns_error() -> None:
    code = "def run(ctx\n    return ctx"
    errors = validate_workflow_code(code)
    assert _has_error_containing(errors, "Syntax error")


# ---------------------------------------------------------------------------
# Multiple errors
# ---------------------------------------------------------------------------


def test_multiple_violations_all_reported() -> None:
    code = """\
import os
import sys

async def run(ctx):
    exec("bad")
    return os.getcwd()
"""
    errors = validate_workflow_code(code)
    # Should have at least: import os error, import sys error, exec error
    assert len(errors) >= 3
