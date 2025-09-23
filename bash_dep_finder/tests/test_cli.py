from __future__ import annotations

import subprocess as sub
import sys

import pytest
from conftest import __project_root__


def call(*args: str) -> tuple[str, int]:
    PYTHON = sys.executable
    cmd: list[str] = [PYTHON, str(__project_root__ / "src" / "bash_dep_finder.py"), *args]
    output = sub.run(cmd, check=False, capture_output=True, text=True)
    res = output.stdout.strip()
    code = output.returncode
    return res, code


def test_help() -> None:
    result, code = call("--help")
    assert code == 0
    assert "usage: bash_dep_finder.py" in result


def test_version() -> None:
    try:
        from bash_dep_finder import __version__  # noqa: PLC0415
    except ImportError:
        pytest.fail("Could not import __version__ from bash_dep_finder", pytrace=False)
    result, code = call("--version")
    assert code == 0

    assert __version__ in result
