#!/usr/bin/env python

from pathlib import Path

import pandas as pd
import pytest

from almos.al_utils import (
    EarlyStopping,
    _assign_prediction_quartiles,
    _rank_model_candidates_with_quartile_diversity,
    assign_values,
    build_selected_candidates_preview,
    check_missing_outputs,
    describe_metric_transition,
    extract_points_from_csv,
    extract_rmse_and_score_from_column,
    extract_sd_from_column,
    get_metrics_from_batches,
    get_scores_from_robert_report,
    format_score_explanation,
    format_score_interpretation,
    format_strategy_label,
    format_strategy_reason,
    format_text_table,
    generate_quartile_medians_df,
    get_quartile,
    plot_metrics_subplots,
    process_batch,
    rank_active_learning_candidates,
    resolve_active_learning_strategy,
)


def build_candidate_df():
    return pd.DataFrame(
        {
            "name": ["mol_a", "mol_b", "mol_c", "mol_d"],
            "target_pred": [8.0, 9.0, 10.0, 7.5],
            "target_pred_sd": [0.5, 1.2, 0.8, 1.5],
        }
    )


def test_resolve_active_learning_strategy_auto_bands():
    weak = resolve_active_learning_strategy(score=3, objective="max")
    balanced = resolve_active_learning_strategy(score=7, objective="min")
    strong = resolve_active_learning_strategy(score=9, objective="max")

    assert weak["strategy"] == "model"
    assert weak["score_band"] == "<=6"
    assert weak["alpha"] is None

    assert balanced["strategy"] == "hit"
    assert balanced["score_band"] == "7-8"
    assert balanced["alpha"] == 1.0
    assert balanced["objective"] == "min"

    assert strong["strategy"] == "hit"
    assert strong["score_band"] == ">8"
    assert strong["alpha"] == 0.5


def test_resolve_active_learning_strategy_manual_modes():
    manual_model = resolve_active_learning_strategy(
        score=8,
        objective=None,
        mode="model",
    )
    manual_hit = resolve_active_learning_strategy(
        score=2,
        objective="max",
        mode="hit",
        alpha_override=0.25,
    )

    assert manual_model == {
        "strategy": "model",
        "objective": None,
        "alpha": None,
        "score": 8,
        "score_band": "manual_model",
        "score_source": "manual_override",
    }
    assert manual_hit["strategy"] == "hit"
    assert manual_hit["objective"] == "max"
    assert manual_hit["alpha"] == 0.25
    assert manual_hit["score_band"] == "manual_hit"


def test_rank_active_learning_candidates_model_uses_max_sd_only():
    df = build_candidate_df()
    strategy = resolve_active_learning_strategy(score=2, objective="max", mode="model")

    ranked = rank_active_learning_candidates(
        df,
        strategy,
        "target_pred",
        "target_pred_sd",
        selection_size=2,
    )

    assert list(ranked["name"]) == ["mol_d", "mol_b", "mol_c", "mol_a"]
    assert ranked["_acquisition_label"].iloc[0] == "uncertainty"
    assert ranked["_ranking_metric"].tolist() == [1.5, 1.2, 0.8, 0.5]
    assert ranked["_selection_penalty"].tolist() == [0.0, 0.0, 0.0, 0.0]


def test_rank_active_learning_candidates_hit_max_and_min():
    df = build_candidate_df()

    max_strategy = resolve_active_learning_strategy(
        score=8,
        objective="max",
        mode="hit",
        alpha_override=0.5,
    )
    min_strategy = resolve_active_learning_strategy(
        score=8,
        objective="min",
        mode="hit",
        alpha_override=0.5,
    )

    ranked_max = rank_active_learning_candidates(
        df,
        max_strategy,
        "target_pred",
        "target_pred_sd",
    )
    ranked_min = rank_active_learning_candidates(
        df,
        min_strategy,
        "target_pred",
        "target_pred_sd",
    )

    assert list(ranked_max["name"]) == ["mol_c", "mol_b", "mol_a", "mol_d"]
    assert list(ranked_min["name"]) == ["mol_d", "mol_a", "mol_b", "mol_c"]
    assert ranked_max["_acquisition_label"].iloc[0] == "prediction + alpha*uncertainty"
    assert ranked_min["_acquisition_label"].iloc[0] == "prediction - alpha*uncertainty"


def test_score_interpretation_and_explanation_messages():
    assert format_score_interpretation(2) == "very weak model (0-3)"
    assert format_score_interpretation(5) == "weak-to-moderate model (4-6)"
    assert format_score_interpretation(8) == "good model (7-8)"
    assert format_score_interpretation(9) == "strong model (>8)"
    assert format_score_interpretation(None) == "score unavailable"

    auto_weak = resolve_active_learning_strategy(score=3, objective="max")
    auto_strong = resolve_active_learning_strategy(score=9, objective="min")
    manual_model = resolve_active_learning_strategy(score=8, objective=None, mode="model")
    manual_hit = resolve_active_learning_strategy(
        score=4,
        objective="max",
        mode="hit",
        alpha_override=0.4,
    )

    assert "focus on learning" in format_score_explanation(auto_weak)
    assert "more weight to promising candidates" in format_score_explanation(auto_strong)
    assert "uncertainty-based model-improvement mode" in format_score_explanation(manual_model)
    assert "hit-focused selection" in format_score_explanation(manual_hit)


def test_strategy_labels_and_reasons_match_current_model_mode():
    auto_model = resolve_active_learning_strategy(score=6, objective="max")
    manual_model = resolve_active_learning_strategy(score=8, objective=None, mode="model")

    assert format_strategy_label("model") == "model improvement (highest uncertainty)"
    assert format_strategy_label("hit") == "hit discovery (prediction weighted by uncertainty)"
    assert format_strategy_reason(auto_model) == "model score 6 is 6 or lower, so uncertainty was prioritized"
    assert format_strategy_reason(manual_model) == "manual mode forced uncertainty-based selection"


def test_selected_candidates_preview_and_text_table_render_cleanly():
    df = build_candidate_df()
    strategy = resolve_active_learning_strategy(score=2, objective="max", mode="model")
    ranked = rank_active_learning_candidates(
        df,
        strategy,
        "target_pred",
        "target_pred_sd",
    )
    preview = build_selected_candidates_preview(
        ranked.head(3),
        "name",
        "target_pred",
        "target_pred_sd",
    )

    assert list(preview.columns) == [
        "rank",
        "candidate",
        "prediction",
        "uncertainty",
        "ranking_score",
    ]
    assert preview.iloc[0]["candidate"] == "mol_d"
    assert preview.iloc[0]["ranking_score"] == 1.5

    table = format_text_table(preview, max_widths={"candidate": 8})
    assert table.startswith("+")
    assert "candidate" in table
    assert "ranking_score" in table
    assert "mol_d" in table


def test_describe_metric_transition_for_score_and_rmse():
    improved_score = describe_metric_transition("score", 4, 6, 0.05, True)
    worsened_rmse = describe_metric_transition("rmse", 0.5, 0.6, 0.05, False)

    assert improved_score == "score: 4 -> 6 | improved | converged"
    assert (
        worsened_rmse
        == "rmse: 0.5000 -> 0.6000 | worsened | change = 20.00% | tolerance = 5.00% | not converged"
    )


def test_generate_quartiles_and_get_quartile():
    df_total = pd.DataFrame({"target_pred": [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]})
    df_exp = pd.DataFrame({"target_pred": [2.0, 4.0, 6.0, 8.0]})

    quartiled_df, quartile_medians, boundaries = generate_quartile_medians_df(
        df_total,
        df_exp.copy(),
        "target_pred",
    )

    assert list(quartiled_df["quartile"]) == ["q1", "q2", "q3", "q4"]
    assert quartile_medians == {
        "q1": 1.25,
        "q2": 3.75,
        "q3": 6.25,
        "q4": 8.75,
    }
    assert boundaries == [0.0, 2.5, 5.0, 7.5, 10.0]
    assert get_quartile(2.0, boundaries) == "q1"
    assert get_quartile(4.0, boundaries) == "q2"
    assert get_quartile(5.5, boundaries) == "q3"
    assert get_quartile(9.0, boundaries) == "q4"


def test_assign_values_prefers_high_sd_within_least_populated_quartiles():
    df = pd.DataFrame(
        {
            "quartile": ["q1", "q1", "q2", "q3", "q4"],
            "target_pred": [1.0, 1.5, 3.0, 5.0, 7.0],
            "target_pred_sd": [0.2, 0.9, 0.5, 0.8, 0.4],
        }
    )

    assigned_points, min_size_quartiles = assign_values(
        df,
        exploit_points=1,
        explore_points=3,
        quartile_medians={"q1": 1.25, "q2": 3.0, "q3": 5.0, "q4": 7.0},
        size_counters={"q1": 0, "q2": 0, "q3": 0, "q4": 0},
        predictions_column="target_pred",
        sd_column="target_pred_sd",
        reverse=False,
    )

    assert min_size_quartiles == ["q1", "q2", "q3"]
    assert assigned_points["q1"] == [1.5]
    assert assigned_points["q2"] == [3.0]
    assert assigned_points["q3"] == [5.0]
    assert assigned_points["q4"] == []


class DummyPage:
    def __init__(self, text):
        self.text = text

    def within_bbox(self, _bbox):
        return self

    def extract_text(self):
        return self.text


def test_extract_metrics_from_pdf_like_text():
    test_text = "Test : R² = 0.85, MAE = 0.12, RMSE = 0.34\nScore 8"
    valid_text = "Valid. : R² = 0.75, MAE = 0.22, RMSE = 0.44\nScore 6"
    sd_text = "Prediction variation, 4*SD = 1.20"

    assert extract_rmse_and_score_from_column(DummyPage(test_text), (0, 0, 1, 1)) == (0.34, 8)
    assert extract_rmse_and_score_from_column(DummyPage(valid_text), (0, 0, 1, 1)) == (0.44, 6)
    assert extract_rmse_and_score_from_column(DummyPage("nothing useful"), (0, 0, 1, 1)) == (None, None)
    assert extract_sd_from_column(DummyPage(sd_text), (0, 0, 1, 1)) == 0.3
    assert extract_sd_from_column(DummyPage("nothing useful"), (0, 0, 1, 1)) is None


def test_extract_points_from_csv_reads_pfi_and_no_pfi_batches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base_dir = tmp_path / "batch_3" / "ROBERT_b3" / "GENERATE" / "Best_model"
    no_pfi_dir = base_dir / "No_PFI"
    pfi_dir = base_dir / "PFI"
    no_pfi_dir.mkdir(parents=True)
    pfi_dir.mkdir(parents=True)

    pd.DataFrame({"Set": ["Training", "Training", "Test"]}).to_csv(
        no_pfi_dir / "model_db.csv",
        index=False,
    )
    pd.DataFrame({"Set": ["Training", "Test", "Test"]}).to_csv(
        pfi_dir / "model_db.csv",
        index=False,
    )

    points = extract_points_from_csv(3)

    assert points == {
        "No_PFI_Training_points": 2,
        "No_PFI_test_points": 1,
        "PFI_Training_points": 1,
        "PFI_test_points": 2,
    }


class DummyLogger:
    def write(self, *_args, **_kwargs):
        return None

    def finalize(self):
        return None


class DummyALConfig:
    pass


def test_check_missing_outputs_accepts_current_model_mode_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "A_b0.csv"
    pd.DataFrame(
        {
            "Name": ["a", "b", "c"],
            "SMILES": ["CC", "CO", "CN"],
            "ee": [1.0, 2.0, None],
            "batch": [0, 0, None],
        }
    ).to_csv(csv_path, index=False)

    self = DummyALConfig()
    self.csv_name = "A_b0.csv"
    self.extra_cmd = ""
    self.ignore = []
    self.batch_column = "batch"
    self.name = "Name"
    self.y = "ee"
    self.al_mode = "model"
    self.alpha = None
    self.objective = None
    self.n_exps = 2
    self.tolerance = "medium"
    self.levels_tolerance = ["tight", "medium", "wide"]
    self.log = DummyLogger()

    result = check_missing_outputs(self)

    assert result.path_csv_name == csv_path
    assert result.base_name == "A"
    assert result.current_number_batch == 1
    assert "batch" in result.ignore
    assert "SMILES" in result.ignore
    assert result.df_raw["batch"].iloc[0] == 0.0
    assert result.df_raw["batch"].iloc[1] == 0.0
    assert pd.isna(result.df_raw["batch"].iloc[2])


def test_check_missing_outputs_rejects_alpha_with_model_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "A_b0.csv"
    pd.DataFrame(
        {
            "Name": ["a", "b"],
            "ee": [1.0, 2.0],
            "batch": [0, 0],
        }
    ).to_csv(csv_path, index=False)

    self = DummyALConfig()
    self.csv_name = "A_b0.csv"
    self.extra_cmd = ""
    self.ignore = []
    self.batch_column = "batch"
    self.name = "Name"
    self.y = "ee"
    self.al_mode = "model"
    self.alpha = 0.5
    self.objective = None
    self.n_exps = 2
    self.tolerance = "medium"
    self.levels_tolerance = ["tight", "medium", "wide"]
    self.log = DummyLogger()

    with pytest.raises(SystemExit):
        check_missing_outputs(self)


class FakePDF:
    def __init__(self):
        self.pages = [
            SimplePage(height=500, width=600),
            SimplePage(height=500, width=600),
            SimplePage(height=500, width=600),
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class SimplePage:
    def __init__(self, height=500, width=600):
        self.height = height
        self.width = width


def test_process_batch_and_score_extraction_use_pdf_helpers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf_dir = tmp_path / "batch_2" / "ROBERT_b2"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "ROBERT_report.pdf").write_text("stub", encoding="utf-8")

    monkeypatch.setattr("almos.al_utils.pdfplumber.open", lambda _path: FakePDF())
    monkeypatch.setattr(
        "almos.al_utils.extract_rmse_and_score_from_column",
        lambda _page, bbox: (0.4, 6) if bbox[0] == 0 else (0.3, 8),
    )
    monkeypatch.setattr(
        "almos.al_utils.extract_sd_from_column",
        lambda _page, bbox: 0.2 if bbox[0] == 0 else 0.1,
    )
    monkeypatch.setattr(
        "almos.al_utils.extract_points_from_csv",
        lambda _batch: {
            "No_PFI_Training_points": 10,
            "No_PFI_test_points": 2,
            "PFI_Training_points": 11,
            "PFI_test_points": 3,
        },
    )

    no_pfi, pfi = process_batch(2)
    score_no_pfi, score_pfi = get_scores_from_robert_report(pdf_dir / "ROBERT_report.pdf")

    assert no_pfi["rmse_no_PFI"] == 0.4
    assert no_pfi["score_no_PFI"] == 6
    assert no_pfi["SD_no_PFI"] == 0.2
    assert pfi["rmse_PFI"] == 0.3
    assert pfi["score_PFI"] == 8
    assert pfi["SD_PFI"] == 0.1
    assert score_no_pfi == 6
    assert score_pfi == 8


def test_get_metrics_from_batches_ignores_non_numeric_batch_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for folder in ["batch_0", "batch_1", "batch_2", "batch_random", "batch_plots"]:
        (tmp_path / folder).mkdir()

    monkeypatch.setattr(
        "almos.al_utils.process_batch",
        lambda batch: (
            {"batch": int(batch), "rmse_no_PFI": 0.5},
            {"batch": int(batch), "rmse_PFI": 0.4},
        ),
    )

    results_no_pfi, results_pfi = get_metrics_from_batches()

    assert [row["batch"] for row in results_no_pfi] == [1, 2]
    assert [row["batch"] for row in results_pfi] == [1, 2]


def test_early_stopping_convergence_and_csv_update(tmp_path):
    logger = DummyLogger()
    stopper = EarlyStopping(patience=2, score_tolerance=0, rmse_min_delta=0.05, sd_min_delta=0.05, logger=logger)
    stopper.output_folder = tmp_path / "batch_plots"
    stopper.output_folder.mkdir(exist_ok=True)
    stopper.output_folder_no_pfi = stopper.output_folder / "no_PFI_plots"
    stopper.output_folder_pfi = stopper.output_folder / "PFI_plots"
    stopper.output_folder_no_pfi.mkdir(exist_ok=True)
    stopper.output_folder_pfi.mkdir(exist_ok=True)

    no_pfi_data = [
        {"batch": 1, "rmse_no_PFI": 1.00, "SD_no_PFI": 0.50, "score_no_PFI": 7, "Training_points_no_PFI": 10, "test_points_no_PFI": 2},
        {"batch": 2, "rmse_no_PFI": 0.98, "SD_no_PFI": 0.49, "score_no_PFI": 8, "Training_points_no_PFI": 12, "test_points_no_PFI": 2},
        {"batch": 3, "rmse_no_PFI": 0.98, "SD_no_PFI": 0.49, "score_no_PFI": 8, "Training_points_no_PFI": 14, "test_points_no_PFI": 2},
    ]
    pfi_data = [
        {"batch": 1, "rmse_PFI": 0.90, "SD_PFI": 0.40, "score_PFI": 8, "Training_points_PFI": 10, "test_points_PFI": 2},
        {"batch": 2, "rmse_PFI": 0.89, "SD_PFI": 0.39, "score_PFI": 8, "Training_points_PFI": 12, "test_points_PFI": 2},
        {"batch": 3, "rmse_PFI": 0.89, "SD_PFI": 0.39, "score_PFI": 8, "Training_points_PFI": 14, "test_points_PFI": 2},
    ]

    updated_no_pfi, updated_pfi = stopper.check_convergence(no_pfi_data, pfi_data)

    assert "convergence" in updated_no_pfi.columns
    assert "convergence" in updated_pfi.columns
    assert (stopper.output_folder_no_pfi / "results_plot_no_PFI.csv").exists()
    assert (stopper.output_folder_pfi / "results_plot_PFI.csv").exists()
    assert updated_no_pfi["convergence"].iloc[-1] in {"yes", "no"}


def test_plot_metrics_subplots_creates_expected_png(tmp_path):
    df = pd.DataFrame(
        {
            "batch": [1, 2],
            "score_PFI": [7, 8],
            "rmse_PFI": [0.8, 0.7],
            "SD_PFI": [0.3, 0.25],
            "Training_points_PFI": [10, 12],
            "test_points_PFI": [2, 2],
            "rmse_converged": [0, 1],
            "SD_converged": [0, 1],
            "score_converged": [0, 1],
        }
    )

    plot_metrics_subplots(df, "PFI", output_dir=str(tmp_path), batch_count=2)

    assert (tmp_path / "PFI_plots" / "PFI_subplots_vertical.png").exists()


def test_prediction_quartile_helpers_cover_constant_and_ranked_cases():
    constant_df = pd.DataFrame({"target_pred": [5.0, 5.0], "target_pred_sd": [0.2, 0.1]})
    quartiled_constant = _assign_prediction_quartiles(constant_df, "target_pred")
    assert list(quartiled_constant["_prediction_quartile"]) == ["q1", "q1"]
    assert quartiled_constant.attrs["prediction_quartile_bounds"] == [5.0] * 5

    diverse_df = pd.DataFrame(
        {
            "target_pred": [1.0, 2.0, 3.0, 4.0],
            "target_pred_sd": [0.9, 0.8, 0.7, 0.6],
        }
    )
    ranked_diverse = _rank_model_candidates_with_quartile_diversity(
        diverse_df,
        "target_pred",
        "target_pred_sd",
        selection_size=2,
    )

    assert "_selection_penalty" in ranked_diverse.columns
    assert "_selection_rank" in ranked_diverse.columns
    assert ranked_diverse.attrs["model_diversity_lambda"] == 0.135
    assert ranked_diverse.attrs["model_diversity_target_per_quartile"] == 1.0
    assert sum(ranked_diverse.attrs["model_diversity_quartile_counts"].values()) == 4
