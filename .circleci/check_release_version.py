"""Require ALMOS_VERSION to advance before merging or publishing."""

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.version import Version


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = "almos/package_versions.py"
PYPI_URL = "https://pypi.org/simple/almos-kit/"


def parse_version(source):
    """Read the version assignment without importing the package."""
    assignments = [
        statement.value
        for statement in ast.parse(source, filename=VERSION_FILE).body
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ALMOS_VERSION"
            for target in statement.targets
        )
    ]
    if len(assignments) != 1:
        raise ValueError(f"Assign ALMOS_VERSION exactly once in {VERSION_FILE}.")
    value = ast.literal_eval(assignments[0])
    if not isinstance(value, str):
        raise ValueError(f"Expected a string for ALMOS_VERSION in {VERSION_FILE}.")
    return Version(value)


def master_version(repository_root):
    source = subprocess.check_output(
        ["git", "show", f"origin/master:{VERSION_FILE}"],
        cwd=repository_root,
        encoding="utf-8",
    )
    return parse_version(source)


def latest_pypi_version():
    request = Request(
        PYPI_URL,
        headers={
            "Accept": "application/vnd.pypi.simple.v1+json",
            "User-Agent": "almos-release-ci",
        },
    )
    with urlopen(request, timeout=30) as response:
        versions = json.load(response)["versions"]
    if not isinstance(versions, list) or not versions:
        raise ValueError("PyPI returned no release history for almos-kit.")
    return max(Version(version) for version in versions)


def main(target, repository_root=REPOSITORY_ROOT):
    reference = "origin/master" if target == "master" else "PyPI (almos-kit)"
    try:
        version_file = repository_root / VERSION_FILE
        source_version = parse_version(version_file.read_text(encoding="utf-8"))
        if source_version.local is not None:
            raise ValueError("PyPI requires a public ALMOS_VERSION without a local suffix.")
        reference_version = (
            master_version(repository_root) if target == "master" else latest_pypi_version()
        )
    except (OSError, KeyError, TypeError, SyntaxError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Cannot verify ALMOS_VERSION against {reference}: {error}", file=sys.stderr)
        return 1

    if source_version <= reference_version:
        print(
            f"ALMOS_VERSION {source_version} must be higher than {reference_version} "
            f"on {reference}. Increase ALMOS_VERSION in {VERSION_FILE}.",
            file=sys.stderr,
        )
        return 1

    print(f"ALMOS_VERSION {source_version} is higher than {reference_version} on {reference}.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("master", "pypi"))
    sys.exit(main(parser.parse_args().target))
