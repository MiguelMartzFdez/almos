#!/usr/bin/env python

import importlib
import io
import math
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import almos.al as al_public_module
import almos.almos as almos_main_module
import almos.cluster_utils as cluster_utils
import almos.utils as utils_module
from almos.argument_parser import var_dict
from almos.cluster_utils import (
    ClusteringCandidate,
    compute_cluster_descriptor_importance,
    get_descriptor_variability_stats,
    log_descriptor_cleanup_summary,
    remove_correlated_descriptors,
    remove_duplicate_descriptors,
    remove_low_information_descriptors,
    remove_low_variance_descriptors,
)
from almos.al import al as ALClass


class CaptureLog:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(str(message))

    def finalize(self):
        return None


def test_public_entry_modules_and_dispatch(monkeypatch, capsys):
    imported_public = importlib.reload(al_public_module)
    assert imported_public.al.__module__ == "almos.al"
    assert imported_public.al.__name__ == ALClass.__name__

    calls = []
    monkeypatch.setattr(
        almos_main_module,
        "command_line_args",
        lambda: SimpleNamespace(cluster=False, al=False),
    )
    monkeypatch.setattr(almos_main_module, "cluster", lambda **kwargs: calls.append(("cluster", kwargs)))
    monkeypatch.setattr(almos_main_module, "al", lambda **kwargs: calls.append(("al", kwargs)))
    almos_main_module.main()
    out = capsys.readouterr().out
    assert "No module was specified" in out
    assert calls == []

    monkeypatch.setattr(
        almos_main_module,
        "command_line_args",
        lambda: SimpleNamespace(cluster=True, al=True, evaluate=False),
    )
    almos_main_module.main()
    assert any(name == "cluster" for name, _ in calls)
    assert any(name == "al" for name, _ in calls)


def test___main___runs_main_and_exits(monkeypatch):
    called = {"main": 0, "exit": 0}
    monkeypatch.setattr("almos.almos.main", lambda: called.__setitem__("main", called["main"] + 1))

    def fake_exit(*_args, **_kwargs):
        called["exit"] += 1
        raise SystemExit()

    monkeypatch.setattr(sys, "exit", fake_exit)
    with pytest.raises(SystemExit):
        runpy.run_module("almos.__main__", run_name="__main__")

    assert called == {"main": 1, "exit": 1}


def test_command_line_args_and_load_variables(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "al", "--csv_name", "A.csv", "--mode", "model", "--alfa", "0.5"],
    )
    args = utils_module.command_line_args()
    assert args.al is True
    assert args.csv_name == "A.csv"
    assert args.al_mode == "model"
    assert args.alpha == 0.5

    cluster_args = utils_module.load_variables(
        {
            "command_line": True,
            "cluster": True,
            "_normalized_command_line_args": ["--cluster", "--input", "B.csv"],
        },
        "cluster",
    )
    cluster_args.log.finalize()
    log_text = (tmp_path / "CLUSTER_data.dat").read_text(encoding="utf-8")
    assert "Command line used in ALMOS: python -m almos --cluster --input \"B.csv\"" in log_text


def test_format_lists_logger_and_check_dependencies(monkeypatch, tmp_path):
    assert utils_module.format_lists("['a', 'b']") == ["a", "b"]
    assert utils_module.format_lists("[a,b]") == ["a", "b"]

    logger = utils_module.Logger(tmp_path / "demo", "log", verbose=True)
    logger.write("hello")
    logger.finalize()
    assert (tmp_path / "demo_log.dat").read_text(encoding="utf-8").strip() == "hello"

    fake_self = SimpleNamespace(args=SimpleNamespace(log=CaptureLog()))

    conda_commands = {"conda", "conda.bat"}
    monkeypatch.setattr(utils_module.shutil, "which", lambda name: name in conda_commands)

    def fake_run_success(cmd, **kwargs):
        if cmd == ["obabel", "-H"]:
            return SimpleNamespace()
        if cmd[:3] == ["python", "-m", "aqme"]:
            return SimpleNamespace(stdout="")
        if cmd[0] in conda_commands:
            return SimpleNamespace(stdout="# packages\nglib 1\ngtk3 1\npango 1\nmscorefonts 1\n")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(utils_module.subprocess, "run", fake_run_success)
    utils_module.check_dependencies(fake_self, "cluster_aqme")
    utils_module.check_dependencies(fake_self, "al")

    monkeypatch.setattr(
        utils_module.subprocess,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(stdout="# packages\nglib 1\n") if cmd[0] in conda_commands else SimpleNamespace(),
    )
    with pytest.raises(SystemExit):
        utils_module.check_dependencies(fake_self, "al")


def test_utils_additional_cli_and_dependency_branches(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "argv", ["prog", "--help"])
    with pytest.raises(SystemExit):
        utils_module.command_line_args()
    help_output = capsys.readouterr().out
    assert "ALMOS v" in help_output
    assert "Usage" in help_output
    assert "easyalmos" in help_output

    monkeypatch.setattr(sys, "argv", ["prog", "help"])
    with pytest.raises(SystemExit):
        utils_module.command_line_args()
    assert "ALMOS v" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["prog", "help", "cluster"])
    with pytest.raises(SystemExit):
        utils_module.command_line_args()
    assert "ALMOS v" in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "cluster",
            "--missing_threshold",
            "bad-float",
            "--cluster_natural_report",
            "--no_pca",
            "--input",
            "B.csv",
        ],
    )
    args = utils_module.command_line_args()
    assert args.cluster is True
    assert args.cluster_natural_report is True
    assert args.enable_pca is False
    assert args.missing_threshold == var_dict["missing_threshold"]

    monkeypatch.setattr(sys, "argv", ["prog", "--definitely-unknown-option"])
    with pytest.raises(SystemExit):
        utils_module.command_line_args()
    assert "not recognized" in capsys.readouterr().out

    options = utils_module.set_options({"definitely_unknown_key": 123})
    assert not hasattr(options, "definitely_unknown_key")
    assert "no option exists" in capsys.readouterr().out

    fake_self = SimpleNamespace(args=SimpleNamespace(log=CaptureLog()))
    monkeypatch.setattr(utils_module.shutil, "which", lambda name: True if name == "pip" else False)
    monkeypatch.setattr(
        utils_module.subprocess,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(stdout="Package Version\n-------------\nglib 1\ngtk3 1\npango 1\nmscorefonts 1\n"),
    )
    utils_module.check_dependencies(fake_self, "al")

    monkeypatch.setattr(utils_module.shutil, "which", lambda name: False)
    with pytest.raises(SystemExit):
        utils_module.check_dependencies(SimpleNamespace(args=SimpleNamespace(log=CaptureLog())), "al")


def build_al_args(tmp_path):
    return SimpleNamespace(
        csv_name="A_b0.csv",
        base_name_raw="A_b0",
        base_name="A",
        df_raw=pd.DataFrame(
            {
                "Name": ["a", "b", "c"],
                "ee": [1.0, 2.0, np.nan],
                "batch": [0.0, 0.0, np.nan],
            }
        ),
        path_csv_name=tmp_path / "A_b0.csv",
        batch_column="batch",
        name="Name",
        y="ee",
        ignore=["batch"],
        current_number_batch=1,
        robert_keywords="",
        n_exps=1,
        tolerance="medium",
        levels_tolerance={"medium": 0.05},
        objective="max",
        al_mode="hit",
        alpha=0.5,
        log=CaptureLog(),
    )


def test_al_methods_cover_workflow_blocks(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    args = build_al_args(tmp_path)
    args.df_raw.to_csv(args.path_csv_name, index=False)

    al_instance = object.__new__(ALClass)
    al_instance.args = args

    def fake_system(command):
        cwd = Path.cwd()
        pred_df = pd.DataFrame({"ee_pred": [1.5, 2.5, 3.5], "ee_pred_sd": [0.1, 0.2, 0.3]})
        (cwd / "ROBERT_report.pdf").write_text("report", encoding="utf-8")
        (cwd / "PREDICT" / "csv_test").mkdir(parents=True, exist_ok=True)
        pred_df.to_csv(cwd / "PREDICT" / "csv_test" / "A_b0_No_PFI.csv", index=False)
        pred_df.to_csv(cwd / "PREDICT" / "csv_test" / "A_b0_PFI.csv", index=False)
        return 0

    monkeypatch.setattr("almos.al.os.system", fake_system)
    monkeypatch.setattr("almos.al.get_scores_from_robert_report", lambda _pdf_path: (6, 8))
    al_instance.run_robert_process()

    assert al_instance.selected_model_type == "PFI"
    assert al_instance.selected_model_score == 8
    assert al_instance.path_predictions.name.endswith("_PFI.csv")

    monkeypatch.setattr(
        "almos.al.shutil.move",
        lambda src, dst: Path(dst).parent.mkdir(parents=True, exist_ok=True),
    )
    (tmp_path / al_instance.robert_folder).mkdir(exist_ok=True)
    al_instance.active_learning_process()
    assert (tmp_path / "A_b1.csv").exists() or (tmp_path / "batch_1").exists()

    called_models = []
    monkeypatch.setattr("almos.al.plot_metrics_subplots", lambda df, model_type, **kwargs: called_models.append(model_type))
    al_instance.generate_plots(
        pd.DataFrame({"batch": [1], "score_no_PFI": [1], "rmse_no_PFI": [1.0], "SD_no_PFI": [0.1], "Training_points_no_PFI": [1], "test_points_no_PFI": [1], "rmse_converged": [0], "SD_converged": [0], "score_converged": [0]}),
        pd.DataFrame({"batch": [1], "score_PFI": [1], "rmse_PFI": [1.0], "SD_PFI": [0.1], "Training_points_PFI": [1], "test_points_PFI": [1], "rmse_converged": [0], "SD_converged": [0], "score_converged": [0]}),
    )
    assert called_models == ["no_PFI", "PFI"]

    al_instance.data_path = tmp_path / "batch_1"
    al_instance.data_path.mkdir(exist_ok=True)
    (tmp_path / "AL_data.dat").write_text("log", encoding="utf-8")
    monkeypatch.setattr(
        "almos.al.shutil.move",
        lambda src, dst: Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8"),
    )
    al_instance.finalize_process(0.0)
    assert (al_instance.data_path / "AL_data.dat").exists()


def test_cluster_utils_cleanup_helpers_and_importance():
    log = CaptureLog()
    df = pd.DataFrame(
        {
            "constant": [1, 1, 1, 1],
            "near_constant": [1, 1, 1, 0],
            "dup_a": [1, 2, 3, 4],
            "dup_b": [1, 2, 3, 4],
            "binary": [0, 1, 0, 1],
            "cont1": [1.0, 2.0, 3.0, 4.0],
            "cont2": [2.0, 4.0, 6.0, 8.0],
        }
    )

    cleaned_df, constant_cols, near_constant_cols = remove_low_information_descriptors(df.copy(), log=log, top_freq_threshold=0.74)
    assert "constant" in constant_cols
    assert "near_constant" in near_constant_cols

    dedup_df, duplicated_cols = remove_duplicate_descriptors(cleaned_df.copy(), log=log)
    assert "dup_b" in duplicated_cols

    binary_stats = get_descriptor_variability_stats(pd.Series([0, 1, 0, 1]))
    cont_stats = get_descriptor_variability_stats(pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert binary_stats["type"] == "binary"
    assert cont_stats["type"] == "continuous"

    varied_df, low_variance_cols = remove_low_variance_descriptors(
        pd.DataFrame({"flat": [1.0, 1.0, 1.0, 1.0], "useful": [1.0, 2.0, 3.0, 4.0], "binary_bad": [1, 1, 1, 0]}),
        log=log,
        iqr_threshold=0.1,
        rel_threshold=0.2,
        binary_threshold=0.3,
    )
    assert "flat" in low_variance_cols
    assert "binary_bad" in low_variance_cols
    assert "useful" in varied_df.columns

    corr_df, corr_cols = remove_correlated_descriptors(
        pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [4, 3, 2, 1]}),
        log=log,
        corr_threshold=0.9,
    )
    assert len(corr_cols) >= 1
    assert len(corr_df.columns) <= 2

    log_descriptor_cleanup_summary(log, ["a", "b", "c"], list(corr_df.columns), {"constant descriptors": ["x"], "duplicates": ["y"]})
    assert any("Descriptor cleanup summary" in message for message in log.messages)

    importance = compute_cluster_descriptor_importance(
        pd.DataFrame({"d1": [1, 1, 5, 5], "d2": [1, 2, 3, 4]}),
        np.array([0, 0, 1, 1]),
    )
    assert list(importance.columns) == ["rank", "descriptor", "f_score", "eta_squared", "n_samples_used", "n_clusters_used"]
    assert not importance.empty


def build_engine():
    return cluster_utils.ClusteringSelectionEngine(
        log=CaptureLog(),
        random_state=0,
        config={"algorithms": ["kmeans", "gmm", "hdbscan"]},
    )


def test_cluster_utils_engine_prepare_mode_and_select(monkeypatch):
    engine = build_engine()
    scaled = np.array([[1.0, 0.0, 2.0], [0.5, 1.0, 1.5], [0.2, 0.5, 0.1], [1.5, 1.2, 0.2]])

    model_input, info = engine._prepare_model_input(scaled, descriptor_count=3)
    assert info["applied"] is False
    assert np.array_equal(model_input, scaled)

    engine.config.update(
        {
            "high_dimensionality_threshold": 2,
            "enable_pca_safeguard": True,
            "pca_explained_variance_threshold": 0.7,
            "pca_min_acceptable_variance": 0.1,
            "pca_min_components": 2,
            "pca_max_components_fraction": 0.75,
            "pca_max_components_absolute": 5,
        }
    )
    reduced, reduced_info = engine._prepare_model_input(scaled, descriptor_count=3)
    assert reduced_info["applied"] is True
    assert reduced.shape[1] == reduced_info["output_dimension"]

    assert engine._determine_dataset_mode(100) == "standard"
    assert engine._determine_dataset_mode(5000) == "large"

    dummy = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0]})
    candidate = ClusteringCandidate(
        algorithm="KMeans",
        params={"n_clusters": 2},
        labels=np.array([0, 0, 1]),
        raw_metrics={"n_clusters": 2},
        filter_reasons=[],
        passed_filters=True,
        final_score=0.8,
    )
    monkeypatch.setattr(engine, "_log_search_space_overview", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(engine, "_evaluate_kmeans_candidates", lambda _data: [candidate])
    monkeypatch.setattr(engine, "_evaluate_gmm_candidates", lambda _data: [candidate])
    monkeypatch.setattr(engine, "_evaluate_hdbscan_candidates", lambda _data: [candidate])
    monkeypatch.setattr(engine, "_pick_best_candidate", lambda _name, candidates: candidates[0] if candidates else None)
    monkeypatch.setattr(engine, "_pick_best_gmm_candidate", lambda candidates: candidates[0] if candidates else None)
    monkeypatch.setattr(engine, "_assign_final_scores", lambda best: None)
    monkeypatch.setattr(engine, "_build_summary_dataframe", lambda candidates: pd.DataFrame({"algorithm": [c.algorithm for c in candidates]}))
    monkeypatch.setattr(engine, "_assess_winner_quality", lambda best: {"status": "ok"})
    monkeypatch.setattr(engine, "_log_algorithm_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(engine, "_log_quality_assessment", lambda *_args, **_kwargs: None)

    result = engine.select_best_model(dummy)
    assert result.best_candidate.algorithm == "KMeans"
    assert not result.summary_df.empty


def test_cluster_utils_engine_real_small_workflow_runs_kmeans_and_gmm():
    log = CaptureLog()
    engine = cluster_utils.ClusteringSelectionEngine(
        log=log,
        random_state=0,
        hdbscan_enabled=False,
        config={
            "algorithms": ["kmeans", "gmm"],
            "n_clusters_max": 4,
            "enable_large_dataset_mode": False,
            "enable_pca_safeguard": False,
        },
    )
    descriptor_df = pd.DataFrame(
        {
            "x1": [0.0, 0.1, 0.2, 5.0, 5.1, 5.2, 10.0, 10.1, 10.2],
            "x2": [0.0, 0.1, 0.2, 5.0, 5.1, 5.2, 10.0, 10.1, 10.2],
            "x3": [1.0, 1.1, 0.9, 4.9, 5.0, 5.1, 9.8, 10.0, 10.2],
        }
    )

    result = engine.select_best_model(descriptor_df)

    assert result.best_candidate is not None
    assert "KMeans" in result.best_by_algorithm
    assert "GMM" in result.best_by_algorithm
    assert not result.summary_df.empty
    assert result.quality_assessment is not None
    assert result.scaled_data.shape == descriptor_df.shape


def test_cluster_utils_engine_internal_scoring_and_quality_helpers():
    log = CaptureLog()
    engine = cluster_utils.ClusteringSelectionEngine(
        log=log,
        random_state=0,
        hdbscan_enabled=False,
        config={"algorithms": ["kmeans", "gmm"], "n_clusters_max": 12},
    )
    engine._dataset_mode = "large"

    assert engine._get_selected_algorithms() == {"kmeans", "gmm"}
    assert engine._get_algorithm_skip_reason("hdbscan", {"kmeans", "gmm"}) == "skipped by user selection"
    assert engine._format_dataset_mode_name("very_large") == "very-large"
    assert engine._get_dataset_mode_range_text() == f">{cluster_utils.STANDARD_DATASET_THRESHOLD} and <= {cluster_utils.VERY_LARGE_DATASET_THRESHOLD}"
    assert engine._kmeans_n_init() == 8
    assert engine._kmeans_max_iter() == 220
    assert engine._gmm_n_init() == 2
    assert engine._gmm_max_iter() == 150
    assert engine._get_silhouette_sample_size() == cluster_utils.LARGE_SILHOUETTE_SAMPLE_SIZE
    assert engine._compute_k_max(80, "KMeans") == 10
    assert engine._compute_k_max(400, "KMeans") == 12

    hdbscan_space = engine._build_hdbscan_search_space(200)
    assert set(hdbscan_space) == {"min_cluster_size", "min_samples"}
    assert all(value < 200 for value in hdbscan_space["min_cluster_size"])
    assert math.isclose(engine._compute_imbalance_penalty([10, 10]), 0.0, abs_tol=1e-6)
    assert engine._compute_imbalance_penalty([19, 1]) > 0.0
    assert engine._normalize_metric([5.0, 5.0]) == [1.0, 1.0]
    assert engine._normalize_metric([3.0, float("inf")], lower_is_better=True)[0] == 1.0

    km_a = ClusteringCandidate(
        algorithm="KMeans",
        params={"n_clusters": 3},
        labels=np.array([0, 0, 1]),
        raw_metrics={
            "silhouette": 0.4,
            "calinski_harabasz": 12.0,
            "davies_bouldin": 0.8,
            "stability": 0.7,
            "imbalance_penalty": 0.1,
            "n_clusters": 3,
            "cluster_sizes": [5, 5, 5],
        },
        passed_filters=True,
        filter_reasons=[],
    )
    km_b = ClusteringCandidate(
        algorithm="KMeans",
        params={"n_clusters": 4},
        labels=np.array([0, 1, 2]),
        raw_metrics={
            "silhouette": 0.39,
            "calinski_harabasz": 11.5,
            "davies_bouldin": 0.82,
            "stability": 0.69,
            "imbalance_penalty": 0.12,
            "n_clusters": 4,
            "cluster_sizes": [4, 4, 4, 3],
        },
        passed_filters=True,
        filter_reasons=[],
    )
    discarded = ClusteringCandidate(
        algorithm="KMeans",
        params={"n_clusters": 2},
        labels=np.array([0, 0, 1]),
        raw_metrics={
            "silhouette": 0.0,
            "calinski_harabasz": 0.0,
            "davies_bouldin": 10.0,
            "stability": 0.0,
            "imbalance_penalty": 1.0,
            "n_clusters": 2,
            "cluster_sizes": [10, 1],
        },
        passed_filters=False,
        filter_reasons=["bad silhouette"],
    )
    engine._assign_internal_scores([km_a, km_b, discarded], "KMeans")
    assert km_a.internal_score is not None
    assert km_b.internal_score is not None
    assert engine._pick_best_candidate("KMeans", [discarded]) is None
    assert engine._pick_best_candidate("KMeans", [km_a, km_b]) is km_a

    gmm_candidate = ClusteringCandidate(
        algorithm="GMM",
        params={"n_clusters": 3},
        labels=np.array([0, 0, 1]),
        raw_metrics={
            "silhouette": 0.41,
            "calinski_harabasz": 12.5,
            "davies_bouldin": 0.79,
            "stability": 0.72,
            "imbalance_penalty": 0.08,
            "n_clusters": 3,
            "cluster_sizes": [5, 5, 5],
            "bic": 101.0,
        },
        passed_filters=True,
        filter_reasons=[],
    )
    hdb_candidate = ClusteringCandidate(
        algorithm="HDBSCAN",
        params={"min_cluster_size": 5},
        labels=np.array([0, 0, 1]),
        raw_metrics={
            "silhouette": 0.32,
            "calinski_harabasz": 10.0,
            "davies_bouldin": 0.9,
            "stability": 0.65,
            "noise_fraction": 0.05,
            "imbalance_penalty": 0.07,
            "density_score": 0.6,
            "n_clusters": 3,
            "cluster_sizes": [6, 5, 4],
        },
        passed_filters=True,
        filter_reasons=[],
    )
    engine._assign_internal_scores([hdb_candidate], "HDBSCAN")
    assert hdb_candidate.internal_score is not None
    assert engine._pick_best_gmm_candidate([discarded]) is None
    gmm_candidate.internal_score = 0.9
    assert engine._pick_best_gmm_candidate([gmm_candidate]) is gmm_candidate

    best_by_algorithm = {"KMeans": km_a, "GMM": gmm_candidate, "HDBSCAN": hdb_candidate}
    engine._assign_final_scores(best_by_algorithm)
    assert all(candidate.final_score is not None for candidate in best_by_algorithm.values())
    summary_df = engine._build_summary_dataframe(list(best_by_algorithm.values()) + [discarded])
    assert {"algorithm", "params", "passed_filters", "final_score"}.issubset(summary_df.columns)

    engine._log_candidate_metrics(km_a.raw_metrics, True, [])
    engine._log_candidate_metrics(discarded.raw_metrics, False, discarded.filter_reasons)
    engine._log_algorithm_summary(best_by_algorithm, km_a)
    assert any("Best candidate per algorithm" in message for message in log.messages)

    assert engine._assess_winner_quality(None)["label"] == "UNAVAILABLE"
    km_a.final_score = 0.8
    km_a.raw_metrics.update({"silhouette": 0.3, "stability": 0.85, "noise_fraction": 0.02, "imbalance_penalty": 0.1})
    assert engine._assess_winner_quality(km_a)["label"] == "GOOD"
    poor_candidate = ClusteringCandidate(
        algorithm="KMeans",
        params={"n_clusters": 3},
        labels=np.array([0, 0, 1]),
        raw_metrics={
            "silhouette": 0.05,
            "stability": 0.3,
            "noise_fraction": 0.35,
            "imbalance_penalty": 0.5,
            "n_clusters": 3,
            "cluster_sizes": [10, 3, 2],
        },
        passed_filters=True,
        filter_reasons=[],
        final_score=0.2,
    )
    poor_quality = engine._assess_winner_quality(poor_candidate)
    assert poor_quality["label"] == "UNRELIABLE"
    engine._log_quality_assessment(poor_quality)
    assert any("WARNING" in message for message in log.messages)
