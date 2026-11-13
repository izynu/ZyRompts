"""Shared fixtures and path wiring.

The package lives in `core/` and is not installed, so the tests put it on the
path themselves. That keeps `pytest tests/` working from a fresh clone with no
setup step, which is the only way a contributor will actually run it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE = REPO_ROOT / "core"

if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def rules_dir(repo_root: Path) -> Path:
    return repo_root / "hooks" / "rules"


@pytest.fixture(scope="session")
def skills_dir(repo_root: Path) -> Path:
    return repo_root / "skills"


@pytest.fixture(scope="session")
def datasets_dir(repo_root: Path) -> Path:
    return repo_root / "evals" / "datasets"
