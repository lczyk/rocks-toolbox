from pathlib import Path

from conftest import __project_root__
from packaging.version import Version

MAIN_FILE = __project_root__ / "src" / "multi_apt_cache.py"
PYPORJECT_FILE = __project_root__ / "pyproject.toml"


def get_version_from_main_file(file: Path) -> Version:
    lines = file.read_text().splitlines()
    for line in lines:
        if line.startswith("__version__"):
            version_str = line.split("=")[1].strip().strip('"').strip("'")
            return Version(version_str)
    raise ValueError(f"Version not found in {file}")


def get_version_from_pyproject(file: Path) -> Version:
    # Ideally we would parse the toml, but python backporting support for
    # tomli or other toml parsers is a but meh, so we will just read the file
    lines = file.read_text().splitlines()
    for line in lines:
        if line.startswith("version ="):
            version_str = line.split("=")[1].strip().strip('"').strip("'")
            return Version(version_str)
    raise ValueError(f"Version not found in {file}")


def test_version() -> None:
    main_version = get_version_from_main_file(MAIN_FILE)
    pyproject_version = get_version_from_pyproject(PYPORJECT_FILE)

    assert main_version == pyproject_version, (
        f"Version mismatch: {main_version} in '{MAIN_FILE.name}' "
        f"and {pyproject_version} in '{PYPORJECT_FILE.name}'. If in doubt, "
        "the version in the main file is the source of truth."
    )
