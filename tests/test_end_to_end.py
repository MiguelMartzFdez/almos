#!/usr/bin/env python

from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

import almos.almos as almos_main_module


def write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def robert_runtime_available():
    result = subprocess.run(
        [sys.executable, "-m", "robert", "-h"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stderr.strip() or result.stdout.strip()


def test_cluster_cli_end_to_end_short_entrypoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "cluster_input.csv"
    write_csv(
        csv_path,
        {
            "Code_Name": ["a", "b", "c", "d", "e", "f"],
            "descp1": [0.0, 0.3, 4.8, 5.4, 9.7, 10.5],
            "descp2": [1.2, 3.8, 0.6, 4.1, 2.4, 5.0],
            "descp3": [7.1, 2.5, 8.0, 1.4, 6.2, 3.3],
            "batch": [None, None, None, None, None, None],
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["cluster", "--input", str(csv_path), "--name", "Code_Name"],
    )

    almos_main_module.main()

    batch_dir = tmp_path / "batch_0"
    assert (batch_dir / "CLUSTER_data.dat").exists()
    assert (batch_dir / "chemical_space_viewer.html").exists()
    assert (batch_dir / "coverage_descriptor_importance.csv").exists()
    assert (batch_dir / "cluster_input_b0.csv").exists()

    output_df = pd.read_csv(batch_dir / "cluster_input_b0.csv")
    assert "batch" in output_df.columns
    assert int(output_df["batch"].fillna(-1).eq(0).sum()) >= 1

    dat_text = read_text(batch_dir / "CLUSTER_data.dat")
    assert "Coverage selection input preparation" in dat_text
    assert "2D chemical space visualization" in dat_text
    assert "Saved batch_0/chemical_space_viewer.html" in dat_text


def test_al_cli_end_to_end_short_entrypoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "A_b0.csv"
    write_csv(
        csv_path,
        {
            "Name": ["mol_a", "mol_b", "mol_c", "mol_d"],
            "feat1": [0.1, 0.2, 0.8, 1.1],
            "feat2": [1.0, 1.1, 0.3, 0.2],
            "ee": [10.0, 20.0, None, None],
            "batch": [0, 0, None, None],
        },
    )

    monkeypatch.setattr("almos.al.check_dependencies", lambda *_args, **_kwargs: None)

    def fake_robert_system(command):
        cwd = Path.cwd()
        pred_dir = cwd / "PREDICT" / "csv_test"
        (cwd / "ROBERT_report.pdf").write_text("fake report", encoding="utf-8")
        pred_dir.mkdir(parents=True, exist_ok=True)
        pred_df = pd.DataFrame(
            {
                "ee_pred": [10.1, 19.9, 15.0, 22.0],
                "ee_pred_sd": [0.05, 0.08, 0.40, 0.25],
            }
        )
        pred_df.to_csv(pred_dir / "A_b0_No_PFI.csv", index=False)
        pred_df.to_csv(pred_dir / "A_b0_PFI.csv", index=False)
        return 0

    class FakeEarlyStopping:
        def __init__(self, *args, **kwargs):
            return None

        def check_convergence(self, *_args, **_kwargs):
            df = pd.DataFrame({"batch": [1], "score_converged": [0], "rmse_converged": [0], "SD_converged": [0]})
            return df.copy(), df.copy()

    def fake_plot_metrics_subplots(data, model_type, output_dir="batch_plots", batch_count=0):
        plot_dir = Path(output_dir) / f"{model_type}_plots"
        plot_dir.mkdir(parents=True, exist_ok=True)
        (plot_dir / f"{model_type}_subplots_vertical.png").write_text("plot", encoding="utf-8")

    monkeypatch.setattr("almos.al.os.system", fake_robert_system)
    monkeypatch.setattr("almos.al.get_scores_from_robert_report", lambda _path: (8, 6))
    monkeypatch.setattr("almos.al.EarlyStopping", FakeEarlyStopping)
    monkeypatch.setattr("almos.al.plot_metrics_subplots", fake_plot_metrics_subplots)
    monkeypatch.setattr("almos.al.get_metrics_from_batches", lambda: ([{"batch": 1}], [{"batch": 1}]))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "al",
            "--csv_name",
            str(csv_path),
            "--name",
            "Name",
            "--y",
            "ee",
            "--n_exps",
            "1",
            "--mode",
            "model",
        ],
    )

    almos_main_module.main()

    batch_dir = tmp_path / "batch_1"
    assert (batch_dir / "AL_data.dat").exists()
    assert (batch_dir / "A_b1.csv").exists()
    assert (batch_dir / "ROBERT_b1").exists()
    assert (tmp_path / "batch_plots" / "no_PFI_plots" / "no_PFI_subplots_vertical.png").exists()
    assert (tmp_path / "batch_plots" / "PFI_plots" / "PFI_subplots_vertical.png").exists()

    output_df = pd.read_csv(batch_dir / "A_b1.csv")
    assert "batch" in output_df.columns
    assert int(pd.to_numeric(output_df["batch"], errors="coerce").eq(1).sum()) == 1

    dat_text = read_text(batch_dir / "AL_data.dat")
    assert "ROBERT Model Update" in dat_text
    assert "Prediction Generation" in dat_text
    assert "Batch 1 Selection" in dat_text
    assert "model improvement" in dat_text
    assert "Saved outputs" in dat_text


@pytest.mark.slow
def test_al_full_real_end_to_end_with_robert(tmp_path):
    available, diagnostic = robert_runtime_available()
    if not available:
        pytest.skip(f"ROBERT runtime not available in this environment: {diagnostic}")

    csv_path = tmp_path / "A_b0.csv"
    rows = {
        "Name": [f"mol_{i}" for i in range(16)],
        "feat1": [0.5, 0.7, 0.9, 1.1, 1.3, 1.6, 1.9, 2.1, 2.4, 2.6, 2.9, 3.2, 3.5, 3.8, 4.0, 4.3],
        "feat2": [1.2, 1.4, 1.0, 0.8, 1.7, 2.0, 1.5, 2.2, 2.5, 2.1, 2.8, 3.0, 3.4, 3.1, 3.6, 3.8],
        "feat3": [0.3, 0.5, 0.6, 0.8, 1.0, 1.1, 1.3, 1.5, 1.8, 1.9, 2.1, 2.2, 2.5, 2.7, 2.9, 3.0],
        "ee": [1.20, 1.55, 1.70, 2.00, 2.20, 2.55, 2.75, 3.10, 3.35, 3.55, 3.90, 4.15, None, None, None, None],
        "batch": [0] * 12 + [None] * 4,
    }
    write_csv(csv_path, rows)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "almos",
            "al",
            "--csv_name",
            str(csv_path),
            "--name",
            "Name",
            "--y",
            "ee",
            "--n_exps",
            "2",
            "--mode",
            "model",
            "--ignore",
            "[batch]",
            "--robert_keywords",
            "--model [RF] --kfold 2 --pfi_max 1 --corr_filter_x False",
        ],
        cwd=tmp_path,
        text=True,
    )
    assert result.returncode == 0

    batch_dir = tmp_path / "batch_1"
    assert (batch_dir / "AL_data.dat").exists()
    assert (batch_dir / "A_b1.csv").exists()
    assert (batch_dir / "ROBERT_b1").exists()
    assert (batch_dir / "ROBERT_b1" / "ROBERT_report.pdf").exists()

    output_df = pd.read_csv(batch_dir / "A_b1.csv")
    selected_count = int(pd.to_numeric(output_df["batch"], errors="coerce").eq(1).sum())
    assert selected_count == 2

    dat_text = read_text(batch_dir / "AL_data.dat")
    assert "ROBERT Model Update" in dat_text
    assert "Prediction Generation" in dat_text
    assert "Batch 1 Selection" in dat_text
    assert "Active Learning Process Completed" in dat_text
