#!/usr/bin/env python

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from almos.cluster import cluster
from almos.argument_parser import var_dict


def write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def test_cluster_rejects_existing_assigned_batch_without_evaluate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "preselected.csv"
    write_csv(
        csv_path,
        {
            "Code_Name": ["a", "b", "c", "d"],
            "descp1": [1.0, 2.0, 3.0, 4.0],
            "descp2": [4.0, 3.0, 2.0, 1.0],
            "descp3": [1.5, 1.7, 2.1, 3.9],
            "batch": [0, None, None, 1],
        },
    )

    with pytest.raises(SystemExit) as excinfo:
        cluster(input=str(csv_path), name="Code_Name")

    assert excinfo.value.code == 1
    dat_text = read_text(tmp_path / "CLUSTER_data.dat")
    assert "already contains assigned batch values" in dat_text
    assert "rerun with --evaluate" in dat_text


def test_cluster_evaluate_requires_batch_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "no_batch_zero.csv"
    write_csv(
        csv_path,
        {
            "Code_Name": ["a", "b", "c"],
            "descp1": [1.0, 2.0, 3.0],
            "descp2": [3.0, 2.0, 1.0],
            "descp3": [1.2, 1.4, 1.6],
            "batch": [1, None, 2],
        },
    )

    with pytest.raises(SystemExit) as excinfo:
        cluster(input=str(csv_path), name="Code_Name", evaluate=True)

    assert excinfo.value.code == 1
    dat_text = read_text(tmp_path / "CLUSTER_data.dat")
    assert "does not contain any rows with batch = 0" in dat_text


def test_cluster_end_to_end_generates_current_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target_csv = tmp_path / "test_cluster14.csv"
    write_csv(
        target_csv,
        {
            "Code_Name": ["a", "b", "c", "d", "e", "f"],
            "descp1": [0.0, 0.3, 4.8, 5.4, 9.7, 10.5],
            "descp2": [1.2, 3.8, 0.6, 4.1, 2.4, 5.0],
            "descp3": [7.1, 2.5, 8.0, 1.4, 6.2, 3.3],
        },
    )

    cluster(input=str(target_csv), name="Code_Name")

    batch_dir = tmp_path / "batch_0"
    assert (batch_dir / "CLUSTER_data.dat").exists()
    assert (batch_dir / "chemical_space_viewer.html").exists()
    assert (batch_dir / "coverage_descriptor_importance.csv").exists()
    assert (batch_dir / "test_cluster14_b0.csv").exists()

    output_df = pd.read_csv(batch_dir / "test_cluster14_b0.csv")
    assert "batch" in output_df.columns
    assert int(output_df["batch"].fillna(-1).eq(0).sum()) == 3

    dat_text = read_text(batch_dir / "CLUSTER_data.dat")
    assert "Coverage selection input preparation" in dat_text
    assert "2D chemical space visualization" in dat_text
    assert "Saved batch_0/chemical_space_viewer.html" in dat_text
    assert "Descriptors most associated with selection regions" in dat_text


def test_cluster_evaluate_mode_reuses_existing_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "evaluate_selection.csv"
    write_csv(
        csv_path,
        {
            "Code_Name": ["a", "b", "c", "d"],
            "descp1": [54, 65, 0, 6],
            "descp2": [76, 7, 876, 578],
            "descp3": [576, 6, 5, 8],
            "batch": [0, None, 0, 1],
        },
    )

    cluster(input=str(csv_path), name="Code_Name", evaluate=True)

    batch_dir = tmp_path / "batch_0"
    output_df = pd.read_csv(batch_dir / "evaluate_selection_b0.csv")
    normalized_batch = pd.to_numeric(output_df["batch"], errors="coerce")
    assert int((normalized_batch == 0).sum()) == 2
    assert int((normalized_batch == 1).sum()) == 1

    dat_text = read_text(batch_dir / "CLUSTER_data.dat")
    assert "Running CLUSTER in evaluation-only mode" in dat_text
    assert "Representative reselection: skipped (--evaluate)" in dat_text
    assert "Rows selected by the user (batch = 0): 2" in dat_text
    assert "Saved batch_0/chemical_space_viewer.html" in dat_text


def build_cluster_stub(tmp_path):
    instance = object.__new__(cluster)
    instance.args = SimpleNamespace(
        seed_clustered=7,
        cluster_auto_budget_max_points=700,
        cluster_auto_budget_sqrt_factor=10,
        cluster_auto_budget_min_points=5,
        log=SimpleNamespace(write=lambda *_args, **_kwargs: None),
    )
    return instance


def build_full_cluster_stub():
    instance = object.__new__(cluster)
    args = deepcopy(var_dict)
    args["log"] = SimpleNamespace(write=lambda *_args, **_kwargs: None, finalize=lambda: None)
    instance.args = SimpleNamespace(**args)
    return instance


def test_get_auto_budget_candidates_scales_with_dataset_size(tmp_path):
    instance = build_cluster_stub(tmp_path)

    small = instance.get_auto_budget_candidates(40)
    medium = instance.get_auto_budget_candidates(800)
    large = instance.get_auto_budget_candidates(20000)

    assert small[0] == 1
    assert small[-1] <= 20
    assert medium[0] == 5
    assert medium == sorted(set(medium))
    assert large[0] == 5
    assert large[-1] <= 500


def test_compute_pca_2d_embedding_handles_one_and_many_dimensions(tmp_path):
    instance = build_cluster_stub(tmp_path)

    one_dim = np.array([[1.0], [2.0], [3.0]])
    many_dim = np.array([[1.0, 0.0, 2.0], [2.0, 1.0, 1.0], [3.0, 1.5, 0.5]])

    embedded_one = instance.compute_pca_2d_embedding(one_dim)
    embedded_many = instance.compute_pca_2d_embedding(many_dim)

    assert embedded_one.shape == (3, 2)
    assert np.allclose(embedded_one[:, 1], 0.0)
    assert embedded_many.shape == (3, 2)


def test_render_chemical_space_viewer_html_includes_color_controls(tmp_path):
    instance = build_cluster_stub(tmp_path)
    payload = {
        "targetColumn": "solubility",
        "targetIsNumeric": True,
        "descriptorColorColumns": ["TPSA", "MolWt"],
        "embeddings": {
            "PCA": {"x": [0.0, 1.0], "y": [1.0, 0.0]},
            "UMAP": {"x": [0.2, 0.8], "y": [0.9, 0.1]},
        },
        "records": [
            {"name": "a", "selected": True, "smiles": "CC", "target": 1.2, "svg": "<svg></svg>"},
            {"name": "b", "selected": False, "smiles": "CO", "target": 0.8, "svg": ""},
        ],
        "colors": {
            "target": [1.2, 0.8],
            "descriptors": {"TPSA": [10.0, 20.0], "MolWt": [100.0, 120.0]},
        },
        "hasSmiles": True,
    }

    html = instance.render_chemical_space_viewer_html(payload, "", "demo.csv")

    assert "Color by" in html
    assert 'value="selected"' in html
    assert 'value="target"' in html
    assert 'value="descriptor::TPSA"' in html
    assert 'value="descriptor::MolWt"' in html
    assert "PCA" in html
    assert "UMAP" in html


def test_validate_cluster_threshold_options_resets_invalid_values():
    instance = build_full_cluster_stub()
    instance.args.hdbscan_enabled = "yes"
    instance.args.cluster_auto_budget_min_points = 0
    instance.args.cluster_auto_budget_sqrt_factor = -1.0
    instance.args.cluster_hdbscan_standard_min_cluster_ratios = [0.5, 1.5]
    instance.args.cluster_hdbscan_standard_min_samples = [1, 0]
    instance.args.algorithms = ["kmeans", "bad"]
    instance.args.mode = "bad-mode"
    instance.args.cluster_standard_dataset_threshold = 5000
    instance.args.cluster_very_large_dataset_threshold = 4000
    instance.args.cluster_ultra_large_dataset_threshold = 3000

    instance.validate_cluster_threshold_options()

    assert instance.args.hdbscan_enabled is True
    assert instance.args.cluster_auto_budget_min_points == var_dict["cluster_auto_budget_min_points"]
    assert instance.args.cluster_auto_budget_sqrt_factor == var_dict["cluster_auto_budget_sqrt_factor"]
    assert (
        instance.args.cluster_hdbscan_standard_min_cluster_ratios
        == var_dict["cluster_hdbscan_standard_min_cluster_ratios"]
    )
    assert (
        instance.args.cluster_hdbscan_standard_min_samples
        == var_dict["cluster_hdbscan_standard_min_samples"]
    )
    assert instance.args.algorithms == var_dict["algorithms"]
    assert instance.args.mode == var_dict["mode"]
    assert instance.args.cluster_standard_dataset_threshold == var_dict["cluster_standard_dataset_threshold"]


def test_prepare_coverage_selection_space_covers_direct_disabled_and_applied_paths():
    instance = build_full_cluster_stub()
    scaled_data = np.array(
        [
            [1.0, 0.0, 2.0, 0.5],
            [0.5, 1.0, 1.5, 0.2],
            [0.2, 0.5, 0.1, 1.0],
            [1.5, 1.2, 0.2, 0.7],
            [1.1, 0.2, 0.6, 1.3],
        ]
    )

    instance.args.cluster_high_dimensionality_threshold = 10
    direct_data, direct_info = instance.prepare_coverage_selection_space(scaled_data, 4)
    assert np.array_equal(direct_data, scaled_data)
    assert direct_info["applied"] is False

    instance.args.cluster_high_dimensionality_threshold = 2
    instance.args.enable_pca = False
    disabled_data, disabled_info = instance.prepare_coverage_selection_space(scaled_data, 4)
    assert np.array_equal(disabled_data, scaled_data)
    assert disabled_info["disabled_by_user"] is True

    instance.args.enable_pca = True
    instance.args.cluster_pca_explained_variance_threshold = 0.7
    instance.args.cluster_pca_min_acceptable_variance = 0.1
    instance.args.cluster_pca_min_components = 2
    instance.args.pca_max_components_fraction = 0.75
    instance.args.pca_max_components = 5
    reduced_data, reduced_info = instance.prepare_coverage_selection_space(scaled_data, 4)
    assert reduced_info["applied"] is True
    assert reduced_info["method"] == "PCA"
    assert reduced_data.shape[1] == reduced_info["output_dimension"]


def test_prepare_coverage_selection_space_can_discard_low_variance_pca():
    instance = build_full_cluster_stub()
    scaled_data = np.array(
        [
            [1.0, 0.0, 2.0, 0.5],
            [0.5, 1.0, 1.5, 0.2],
            [0.2, 0.5, 0.1, 1.0],
            [1.5, 1.2, 0.2, 0.7],
            [1.1, 0.2, 0.6, 1.3],
        ]
    )
    instance.args.cluster_high_dimensionality_threshold = 2
    instance.args.enable_pca = True
    instance.args.cluster_pca_explained_variance_threshold = 0.7
    instance.args.cluster_pca_min_acceptable_variance = 0.99
    instance.args.cluster_pca_min_components = 2
    instance.args.pca_max_components_fraction = 0.75
    instance.args.pca_max_components = 5

    returned_data, returned_info = instance.prepare_coverage_selection_space(scaled_data, 4)

    assert np.array_equal(returned_data, scaled_data)
    assert returned_info["applied"] is False
    assert returned_info["discarded_due_to_low_variance"] is True


def test_select_coverage_representatives_representative_and_exploratory_modes():
    instance = build_full_cluster_stub()
    selection_data = np.array(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [5.0, 5.0],
            [5.1, 5.0],
            [10.0, 10.0],
            [10.2, 10.1],
        ]
    )
    selectable_indices = np.arange(len(selection_data))

    instance.args.mode = "representative"
    selected_representative = instance.select_coverage_representatives(
        selection_data,
        selectable_indices,
        3,
        log_selection=False,
    )
    assert len(selected_representative) == 3
    assert len(set(selected_representative)) == 3

    instance.args.mode = "exploratory"
    selected_exploratory = instance.select_coverage_representatives(
        selection_data,
        selectable_indices,
        3,
        log_selection=False,
    )
    assert len(selected_exploratory) == 3
    assert len(set(selected_exploratory)) == 3


def test_select_coverage_representatives_handles_empty_full_and_invalid_requests():
    instance = build_full_cluster_stub()
    selection_data = np.array([[0.0, 0.0], [1.0, 1.0]])
    selectable_indices = np.array([0, 1])

    assert instance.select_coverage_representatives(selection_data, selectable_indices, 0) == []
    assert instance.select_coverage_representatives(selection_data, selectable_indices, 2) == [0, 1]
    with pytest.raises(SystemExit):
        instance.select_coverage_representatives(selection_data, selectable_indices, 3)


def test_choose_natural_selection_candidate_prefers_interpretable_near_best_model():
    instance = build_full_cluster_stub()
    best_candidate = SimpleNamespace(
        final_score=0.80,
        passed_filters=True,
        algorithm="kmeans",
        params={"k": 4},
        raw_metrics={"n_clusters": 4},
    )
    near_best_candidate = SimpleNamespace(
        final_score=0.77,
        passed_filters=True,
        algorithm="gmm",
        params={"k": 3},
        raw_metrics={"n_clusters": 3},
    )
    natural_result = SimpleNamespace(
        best_by_algorithm={"kmeans": best_candidate, "gmm": near_best_candidate},
        best_candidate=best_candidate,
    )

    selected_candidate, reason = instance.choose_natural_selection_candidate(natural_result)

    assert selected_candidate is near_best_candidate
    assert "more interpretable" in reason


def test_select_natural_cluster_representatives_uses_allocation_and_fallback():
    instance = build_full_cluster_stub()
    instance.args.mode = "natural"
    selection_data = np.array([[0.0, 0.0], [0.1, 0.0], [5.0, 5.0], [5.1, 5.0], [10.0, 10.0]])
    labels = np.array([0, 0, 1, 1, -1])
    natural_candidate = SimpleNamespace(
        algorithm="gmm",
        params={"k": 2},
        labels=labels,
        raw_metrics={"n_clusters": 2},
    )
    coverage_result = {
        "selection_data": selection_data,
        "natural_selection_result": SimpleNamespace(best_by_algorithm={"gmm": natural_candidate}, best_candidate=natural_candidate),
    }
    monkeypatch_allocate = {0: 1, 1: 1}
    instance.choose_natural_selection_candidate = lambda _result: (natural_candidate, "close to best")
    instance.allocate_points_by_group_population = lambda _labels, _n: monkeypatch_allocate
    instance.select_points_within_natural_group = lambda _data, group_indices, n: group_indices[:n]
    instance.select_coverage_representatives = lambda _data, remaining_indices, n, log_selection=False: list(remaining_indices)[:n]

    selected = instance.select_natural_cluster_representatives(
        coverage_result,
        np.arange(len(selection_data)),
        3,
    )

    assert len(selected) == 3
    assert set(selected[:2]) == {0, 2}


def test_save_cluster_outputs_writes_files_for_new_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "batch_0").mkdir()
    instance = build_full_cluster_stub()
    instance.args.name = "Code_Name"
    instance.args.y = "target"
    instance.args.evaluate = False
    instance.args.ignore = []
    instance.select_representative_points = lambda _coverage_result: ([0, 2], {0: 1, 2: 2}, {})
    instance.build_chemical_space_viewer = lambda **_kwargs: "batch_0/chemical_space_viewer.html"
    instance.args.log = SimpleNamespace(write=lambda *_args, **_kwargs: None)

    monkeypatch.setattr(
        "almos.cluster.compute_cluster_descriptor_importance",
        lambda *_args, **_kwargs: pd.DataFrame(
            {"rank": [1], "descriptor": ["descp1"], "f_score": [2.0], "eta_squared": [0.4]}
        ),
    )

    descp_file = tmp_path / "descp.csv"
    pd.DataFrame(
        {
            "Code_Name": ["a", "b", "c"],
            "target": [1.0, 2.0, 3.0],
            "descp1": [0.1, 0.2, 0.3],
        }
    ).to_csv(descp_file, index=False)
    coverage_result = {
        "descriptor_df": pd.DataFrame({"descp1": [0.1, 0.2, 0.3]}),
        "selection_region_labels": np.array([0, 1, 1]),
    }

    instance.save_cluster_outputs(str(descp_file), ["demo"], "demo.csv", coverage_result)

    saved_df = pd.read_csv(tmp_path / "batch_0" / "demo_b0.csv")
    assert int(pd.to_numeric(saved_df["batch"], errors="coerce").eq(0).sum()) == 2
    assert (tmp_path / "batch_0" / "coverage_descriptor_importance.csv").exists()


def test_allocate_points_by_group_population_handles_small_and_proportional_cases():
    instance = build_full_cluster_stub()
    labels = np.array([0, 0, 0, 1, 1, -1])

    tiny = instance.allocate_points_by_group_population(labels, 2)
    proportional = instance.allocate_points_by_group_population(labels, 4)

    assert sum(tiny.values()) == 2
    assert all(value >= 1 for value in tiny.values())
    assert proportional == {0: 2, 1: 1, -1: 1}


def test_select_points_within_natural_group_handles_edge_cases_and_farthest_selection():
    instance = build_full_cluster_stub()
    selection_data = np.array([[0.0, 0.0], [0.2, 0.0], [5.0, 5.0], [10.0, 10.0]])
    group_indices = [0, 1, 2, 3]

    assert instance.select_points_within_natural_group(selection_data, group_indices, 0) == []
    assert instance.select_points_within_natural_group(selection_data, group_indices, 5) == group_indices

    chosen = instance.select_points_within_natural_group(selection_data, group_indices, 2)
    assert len(chosen) == 2
    assert len(set(chosen)) == 2


def test_molecule_svg_from_smiles_and_visual_quality_helpers():
    instance = build_full_cluster_stub()

    assert instance.molecule_svg_from_smiles("") == ""
    assert instance.molecule_svg_from_smiles("not-a-smiles") == ""
    valid_svg = instance.molecule_svg_from_smiles("CCO")
    assert "<svg" in valid_svg

    fidelity = instance.compute_embedding_fidelity(
        np.array([[0.0, 0.0], [1.0, 1.0], [0.5, 0.5], [1.5, 1.5]]),
        np.array([[0.0, 0.0], [1.0, 1.0], [0.4, 0.6], [1.4, 1.6]]),
        np.array([True, False, True, False]),
    )
    assert fidelity["trustworthiness"] is not None
    assert instance.compute_pca_2d_variance(np.array([[1.0], [2.0], [3.0]])) == 1.0
    assert instance.classify_visualization_local_quality(0.96) == "EXCELLENT"
    assert instance.classify_visualization_local_quality(0.85) == "ACCEPTABLE"
    assert "rough visual guides" in instance.interpret_combined_2d_visualization_quality(0.7, 0.4, None)
    assert "local neighborhoods well" in instance.interpret_combined_2d_visualization_quality(0.92, 0.8, 0.93)


def test_build_chemical_space_viewer_generates_html_and_payload_options(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "batch_0").mkdir()
    instance = build_cluster_stub(tmp_path)
    instance.args.name = "Code_Name"
    instance.args.y = "target"
    instance.args.log = SimpleNamespace(write=lambda *_args, **_kwargs: None)
    instance.compute_umap_2d_embedding = lambda *_args, **_kwargs: (None, None, "UMAP is not installed")
    instance.molecule_svg_from_smiles = lambda smiles: f"<svg>{smiles}</svg>"

    descp_df = pd.DataFrame(
        {
            "Code_Name": ["a", "b", "c"],
            "SMILES": ["CC", "CO", "CN"],
            "target": [1.0, 2.5, None],
            "descp1": [0.1, 0.2, 0.3],
            "descp2": [1.1, 1.2, 1.3],
        }
    )
    coverage_result = {
        "selection_data": np.array([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]]),
        "descriptor_df": descp_df[["descp1", "descp2"]],
        "selection_region_labels": np.array([0, 1, 1]),
    }

    monkeypatch.setattr(
        "almos.cluster.compute_cluster_descriptor_importance",
        lambda *_args, **_kwargs: pd.DataFrame(
            {
                "descriptor": ["descp2", "descp1"],
                "rank": [1, 2],
                "f_score": [2.0, 1.0],
                "eta_squared": [0.4, 0.2],
            }
        ),
    )

    viewer_path = instance.build_chemical_space_viewer(
        descp_df=descp_df,
        selected_indices=[1],
        coverage_result=coverage_result,
        file_name="demo.csv",
    )

    html = read_text(tmp_path / viewer_path)
    assert viewer_path == "batch_0/chemical_space_viewer.html"
    assert "descriptor::descp2" in html
    assert "descriptor::descp1" in html
    assert "target" in html
    assert "Selected" in html
    assert "No valid numeric value" in html or "Color by" in html
