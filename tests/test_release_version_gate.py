"""Protect the ALMOS version checks used before merging and publishing."""

import io
import json
import runpy
import subprocess
from pathlib import Path
from urllib.error import URLError

import pytest


CHECKER = Path(__file__).resolve().parents[1] / ".circleci" / "check_release_version.py"


def check_version(target, repository_root):
    return runpy.run_path(str(CHECKER))["main"](target, repository_root)


def write_version(repository_root, version):
    version_file = repository_root / "almos" / "package_versions.py"
    version_file.parent.mkdir(exist_ok=True)
    version_file.write_text(f'ALMOS_VERSION = "{version}"\n', encoding="utf-8")


def run_git(repository_root, *args):
    return subprocess.check_output(["git", *args], cwd=repository_root, text=True).strip()


@pytest.mark.parametrize(
    ("source_version", "expected_result"),
    [("1.2.9", 1), ("1.2.10", 1), ("1.2.11", 0), ("1.2.11+local", 1)],
)
def test_pr_version_must_exceed_master(tmp_path, source_version, expected_result):
    run_git(tmp_path, "init", "-q")
    write_version(tmp_path, "1.2.10")
    run_git(tmp_path, "add", "almos/package_versions.py")
    master_tree = run_git(tmp_path, "write-tree")
    run_git(tmp_path, "update-ref", "refs/remotes/origin/master", master_tree)
    write_version(tmp_path, source_version)

    assert check_version("master", tmp_path) == expected_result


@pytest.mark.parametrize(
    ("source_version", "expected_result"),
    [("1.2.0", 1), ("1.2.4", 1), ("1.2.5.0", 1), ("1.2.6", 0)],
)
def test_release_version_must_exceed_every_pypi_release(
    tmp_path, monkeypatch, source_version, expected_result
):
    def open_project(request, *, timeout):
        assert request.full_url == "https://pypi.org/simple/almos-kit/"
        assert request.get_header("Accept") == "application/vnd.pypi.simple.v1+json"
        project = {"name": "almos-kit", "versions": ["1.2.5", "1.2.0"], "files": []}
        return io.BytesIO(json.dumps(project).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", open_project)
    write_version(tmp_path, source_version)

    assert check_version("pypi", tmp_path) == expected_result


def test_release_is_blocked_if_version_is_assigned_twice(tmp_path, monkeypatch):
    def open_project(*args, **kwargs):
        return io.BytesIO(b'{"versions": ["1.2.0"]}')

    monkeypatch.setattr("urllib.request.urlopen", open_project)
    write_version(tmp_path, "1.2.6")
    version_file = tmp_path / "almos" / "package_versions.py"
    with version_file.open("a", encoding="utf-8") as source:
        source.write('ALMOS_VERSION = "1.2.0"\n')

    assert check_version("pypi", tmp_path) == 1


def test_release_is_blocked_when_pypi_is_unavailable(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise URLError("PyPI is unavailable")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    write_version(tmp_path, "1.2.6")

    assert check_version("pypi", tmp_path) == 1
