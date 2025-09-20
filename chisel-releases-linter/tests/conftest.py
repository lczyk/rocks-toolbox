import pytest
import sys
from pathlib import Path

__project_root__ = Path(__file__).resolve().parents[1]
sys.path.append(str(__project_root__))

PLUCKY_SLICES_SNAPSHOT = __project_root__ / "tests" / "testfiles" / "plucky_slices_snapshot"


@pytest.fixture
def plucky_slices() -> list[Path]:
    if not PLUCKY_SLICES_SNAPSHOT.exists():
        pytest.skip("Plucky slices snapshot not found, skipping tests.")
    return sorted(PLUCKY_SLICES_SNAPSHOT.glob("*.yaml"))
