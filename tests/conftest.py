from __future__ import annotations

import shutil
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

GENERATED_FILE_NAMES = {
    "AL_data.dat",
    "CLUSTER_data.dat",
    "ROBERT_report.pdf",
    "A_b1.csv",
    "demo_log.dat",
}

GENERATED_DIR_PREFIXES = (
    "batch_",
    "PREDICT",
    "ROBERT_b",
)


def _safe_remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _cleanup_generated_artifacts(base_dir: Path) -> None:
    if not base_dir.exists():
        return

    for name in GENERATED_FILE_NAMES:
        _safe_remove_path(base_dir / name)

    for child in base_dir.iterdir():
        if any(child.name.startswith(prefix) for prefix in GENERATED_DIR_PREFIXES):
            _safe_remove_path(child)


@pytest.fixture(autouse=True)
def cleanup_generated_test_artifacts():
    yield
    _cleanup_generated_artifacts(Path.cwd())
    _cleanup_generated_artifacts(REPO_ROOT)
