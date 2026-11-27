"""Read completed campaign outputs and import experimental measurements."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RunResult:
    directory: Path
    module: str
    batch: int
    selected_count: int | None
    input_path: Path | None
    dataset: Path | None
    viewer: Path | None
    ranking: Path | None
    options: dict


def read_run_result(manifest_path):
    """Read a completed manifest and resolve its existing local artifacts."""
    manifest_path = Path(manifest_path).resolve()
    if manifest_path.name == "run.previous.json":
        raise ValueError("The previous manifest is a provenance record. Open the current run.json to browse results.")
    directory = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported ALMOS run manifest.")
    module = manifest.get("module")
    if manifest.get("status") != "completed" or module not in ("cluster", "al"):
        raise ValueError("Select the manifest of a completed ALMOS run.")

    summary = manifest.get("summary")
    options = manifest.get("effective_options")
    entries = manifest.get("artifacts")
    if not isinstance(summary, dict) or not isinstance(options, dict) or not isinstance(entries, list):
        raise ValueError("The run manifest is missing its summary, settings, or artifacts.")
    batch = 0 if module == "cluster" else summary.get("batch")
    if type(batch) is not int or batch < 0:
        raise ValueError("The run manifest has an invalid batch number.")

    artifacts = {}
    for entry in entries:
        if not isinstance(entry, str):
            continue
        artifact = (directory / entry).resolve()
        if artifact.is_relative_to(directory) and artifact.is_file():
            artifacts[artifact.name] = artifact

    input_info = manifest.get("input")
    source = input_info.get("path") if isinstance(input_info, dict) else None
    selected = summary.get("selected_count")
    datasets = [path for name, path in artifacts.items() if name.endswith(f"_b{batch}.csv")]
    return RunResult(
        directory=directory,
        module=module,
        batch=batch,
        selected_count=selected if type(selected) is int else None,
        input_path=Path(source).resolve() if isinstance(source, str) else None,
        dataset=datasets[0] if len(datasets) == 1 else None,
        viewer=artifacts.get("chemical_space_viewer.html"),
        ranking=artifacts.get("candidate_ranking.csv"),
        options=options,
    )


def import_measurements(dataset_path, measurements_path, output_path, identifier, target):
    """Fill empty measurements on assigned rows by ID and save a new dataset."""
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"The output file already exists: {output_path.name}")
    if identifier == target:
        raise ValueError("Select two different columns for the identifier and target.")

    dataset = pd.read_csv(dataset_path, dtype=str, keep_default_na=False)
    measurements = pd.read_csv(measurements_path, dtype=str, keep_default_na=False)
    if target not in measurements.columns:
        raise ValueError(f"Measurements must include '{target}'.")
    for label, frame in (("Dataset", dataset), ("Measurements", measurements)):
        if identifier not in frame.columns:
            raise ValueError(f"{label} must include '{identifier}'.")
        ids = frame[identifier]
        if ids.str.strip().eq("").any() or ids.duplicated().any():
            raise ValueError(f"{label} must have unique, non-empty identifiers.")
    if measurements.empty:
        raise ValueError("The measurements CSV has no data rows.")

    batch_columns = [column for column in dataset.columns if column.lower() == "batch"]
    if len(batch_columns) != 1 or identifier == batch_columns[0] or target.lower() == "batch":
        raise ValueError("The dataset must include a separate batch column.")
    if target not in dataset.columns:
        dataset[target] = ""
    table = dataset.set_index(identifier, drop=False)
    incoming = measurements.set_index(identifier)[target]
    unknown = incoming.index.difference(table.index)
    if len(unknown):
        raise ValueError(f"Unknown candidate IDs: {', '.join(unknown[:5])}.")

    batch = pd.to_numeric(table.loc[incoming.index, batch_columns[0]], errors="coerce")
    assigned = np.isfinite(batch) & batch.ge(0) & batch.mod(1).eq(0)
    if not assigned.all():
        raise ValueError(f"Candidates not assigned to a batch: {', '.join(batch.index[~assigned][:5])}.")

    numeric = pd.to_numeric(incoming, errors="coerce")
    if not np.isfinite(numeric).all():
        raise ValueError("Each imported target must be a finite number.")
    previous = table.loc[incoming.index, target]
    missing_values = {"", "na", "n/a", "#n/a", "nan", "-nan", "null", "none", "<na>"}
    measured = ~previous.str.strip().str.casefold().isin(missing_values)
    if (measured & pd.to_numeric(previous, errors="coerce").ne(numeric)).any():
        raise ValueError("At least one imported value conflicts with an existing measurement.")
    new_values = incoming.loc[~measured]
    if new_values.empty:
        raise ValueError("The measurements CSV contains no new values.")
    table.loc[new_values.index, target] = new_values

    file = NamedTemporaryFile(
        dir=output_path.parent, prefix=".almos-measurements-", mode="w",
        encoding="utf-8", newline="", delete=False,
    )
    temporary_path = Path(file.name)
    try:
        with file:
            table.to_csv(file, index=False)
        # Publish the complete file without replacing a destination created concurrently.
        if os.name == "nt":
            temporary_path.rename(output_path)
        else:
            os.link(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return len(new_values)
