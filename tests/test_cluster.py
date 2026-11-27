#!/usr/bin/env python

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from rdkit import Chem

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


def test_cluster_rejects_ambiguous_batch_columns(tmp_path, monkeypatch):
    instance = build_full_cluster_stub()
    csv_path = tmp_path / "ambiguous.csv"
    write_csv(csv_path, {"code_name": ["a", "b"], "batch": [None, None], "Batch": [0, 1]})
    instance.args.input = str(csv_path)
    log_lines = []
    monkeypatch.setattr(instance.args.log, "write", log_lines.append)

    with pytest.raises(SystemExit) as excinfo:
        instance.checking_cluster()

    assert excinfo.value.code == 1
    assert any("multiple 'batch' columns" in line for line in log_lines)


def test_cluster_end_to_end_generates_current_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target_csv = tmp_path / "test_cluster14.csv"
    sibling_csv = tmp_path / "test_cluster14_b0.csv"
    sibling_bytes = b"existing,data\n"
    sibling_csv.write_bytes(sibling_bytes)
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

    assert sibling_csv.read_bytes() == sibling_bytes
    batch_dir = tmp_path / "batch_0"
    assert (batch_dir / "CLUSTER_data.dat").exists()
    assert (batch_dir / "chemical_space" / "chemical_space_viewer.html").exists()
    assert (batch_dir / "chemical_space" / "coverage_descriptor_importance.csv").exists()
    assert (batch_dir / "test_cluster14_b0.csv").exists()

    output_df = pd.read_csv(batch_dir / "test_cluster14_b0.csv")
    assert "batch" in output_df.columns
    assert int(output_df["batch"].fillna(-1).eq(0).sum()) == 3

    dat_text = read_text(batch_dir / "CLUSTER_data.dat")
    assert "Coverage selection input preparation" in dat_text
    assert "2D chemical space visualization" in dat_text
    assert "Saved batch_0/chemical_space/chemical_space_viewer.html" in dat_text
    assert "Descriptors most associated with selection regions" in dat_text
    output_count = 2 + len(list((batch_dir / "chemical_space").iterdir()))
    assert f"Primary CLUSTER output files written: {output_count}" in dat_text
    manifest = json.loads(read_text(batch_dir / "run.json"))
    assert manifest["module"] == "cluster"
    assert manifest["summary"]["mode"] == "representative"
    assert manifest["summary"]["selected_count"] == 3
    assert len(manifest["artifacts"]) == output_count
    assert "CLUSTER_data.dat" in manifest["artifacts"]
    assert "chemical_space/chemical_space_viewer.html" in manifest["artifacts"]
    assert all((batch_dir / artifact).is_file() for artifact in manifest["artifacts"])


@pytest.mark.parametrize("batch_column", ["batch", "BaTcH"])
def test_cluster_evaluate_mode_reuses_existing_selection(tmp_path, monkeypatch, batch_column):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "evaluate_selection.csv"
    write_csv(
        csv_path,
        {
            "Code_Name": ["a", "b", "c", "d"],
            "descp1": [54, 65, 0, 6],
            "descp2": [76, 7, 876, 578],
            "descp3": [576, 6, 5, 8],
            batch_column: [0, None, 0, 1],
        },
    )

    cluster(input=str(csv_path), name="Code_Name", evaluate=True)

    batch_dir = tmp_path / "batch_0"
    output_df = pd.read_csv(batch_dir / "evaluate_selection_b0.csv")
    assert [column for column in output_df if column.lower() == "batch"] == ["batch"]
    normalized_batch = pd.to_numeric(output_df["batch"], errors="coerce")
    assert int((normalized_batch == 0).sum()) == 2
    assert int((normalized_batch == 1).sum()) == 1

    dat_text = read_text(batch_dir / "CLUSTER_data.dat")
    assert "Running CLUSTER in evaluation-only mode" in dat_text
    assert "Representative reselection: skipped (--evaluate)" in dat_text
    assert "Rows selected by the user (batch = 0): 2" in dat_text
    assert "Saved batch_0/chemical_space/chemical_space_viewer.html" in dat_text


def test_cluster_preserves_literal_csv_identifiers_in_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    input_csv = tmp_path / "literal_ids.csv"
    identifiers = ["001", "1", "NA", "NULL"]
    write_csv(
        input_csv,
        {
            "Sample_ID": identifiers,
            "descp1": [54, 65, 0, 6],
            "descp2": [76, 7, 876, 578],
            "descp3": [576, 6, 5, 8],
            "batch": [0, None, 0, 1],
        },
    )

    cluster(input=str(input_csv), name="sample_id", evaluate=True)

    output_dir = tmp_path / "batch_0"
    output_df = pd.read_csv(output_dir / "literal_ids_b0.csv", keep_default_na=False)
    pca_df = pd.read_csv(
        output_dir / "chemical_space" / "chemical_space_pca.csv", keep_default_na=False
    )
    assert output_df["Sample_ID"].tolist() == ["001", "NA", "NULL", "1"]
    assert pca_df["Sample_ID"].tolist() == identifiers


@pytest.mark.parametrize("suffix", [".sdf", ".SDF"])
def test_checking_cluster_keeps_sdf_and_existing_csv_unchanged(tmp_path, monkeypatch, suffix):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / f"molecules{suffix}"
    molecule = Chem.MolFromSmiles("CC")
    molecule.SetProp("_Name", "001")
    with Chem.SDWriter(str(source_path)) as writer:
        writer.write(molecule)
    source_bytes = source_path.read_bytes()
    sidecar_path = source_path.with_suffix(".csv")
    sidecar_bytes = b"this,already,exists\n"
    sidecar_path.write_bytes(sidecar_bytes)
    instance = build_full_cluster_stub()
    instance.args.input = str(source_path)
    instance.args.aqme = True
    instance.args.ignore = []

    _, molecule_df, _ = instance.checking_cluster()

    assert molecule_df.to_dict("records") == [{"code_name": "001", "SMILES": "CC"}]
    assert source_path.read_bytes() == source_bytes
    assert sidecar_path.read_bytes() == sidecar_bytes


def test_cluster_natural_report_uses_the_order_fitted_by_the_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    input_csv = tmp_path / "natural_report.csv"
    write_csv(
        input_csv,
        {
            "code_name": ["a", "b", "c", "d"],
            "separation": [0.0, 0.0, 1.0, 1.0],
            "unrelated": [0.0, 1.0, 0.0, 1.0],
            "batch": [None, 0, None, 0],
        },
    )
    candidate = SimpleNamespace(algorithm="kmeans", params={"k": 2}, labels=np.array([0, 0, 1, 1]))
    model_result = SimpleNamespace(
        best_candidate=candidate,
        best_by_algorithm={},
        dimensionality_reduction_info={},
    )
    monkeypatch.setattr(cluster, "run_natural_clustering_analysis", lambda *_args: model_result)

    cluster(input=str(input_csv), evaluate=True, cluster_natural_report=True)

    ranked = pd.read_csv(tmp_path / "batch_0" / "cluster_descriptor_importance.csv")
    assert ranked["descriptor"].tolist() == ["separation", "unrelated"]
    assert ranked["eta_squared"].tolist() == [1.0, 0.0]


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


def prepare_aqme_cleanup(tmp_path, monkeypatch, aqme_rows):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "batch_0").mkdir()
    staging_directory = tmp_path / "staging"
    staging_directory.mkdir()
    instance = build_full_cluster_stub()
    instance.args.aqme = True
    instance.args.name = "code_name"
    instance.args.ignore = ["code_name", "SMILES", "batch"]
    original_input_path = staging_directory / "example_b0.csv"
    write_csv(
        original_input_path,
        {
            "code_name": ["001", "1", "NA", "004"],
            "SMILES": ["CC", "CO", "CN", "CCC"],
            "batch": [None, None, 0, None],
        },
    )
    descriptor_csv = tmp_path / "aqme.csv"
    write_csv(descriptor_csv, aqme_rows)
    return instance, descriptor_csv, original_input_path


def test_aqme_cleanup_reorders_descriptors_by_literal_code_name(tmp_path, monkeypatch):
    instance, descriptor_csv, original_input_path = prepare_aqme_cleanup(
        tmp_path,
        monkeypatch,
        {
            "code_name": ["NA", "004", "001", "1"],
            "descp1": [0, 6, 54, 65],
            "descp2": [50, 58, 80, 7],
            "descp3": [5, 8, 576, 6],
        },
    )

    _, descriptor_df, output_file = instance.clean_up_cluster(
        descriptor_csv, ["example"], "example.csv", original_input_path
    )

    output_df = pd.read_csv(output_file, keep_default_na=False)
    assert output_df["code_name"].tolist() == ["001", "1", "NA", "004"]
    assert descriptor_df["descp1"].tolist() == [54, 65, 0, 6]
    assert output_df["descp1"].tolist() == [54, 65, 0, 6]
    assert output_df.loc[2, "batch"] == "0.0"


def test_aqme_run_protects_ids_from_type_inference(tmp_path, monkeypatch):
    instance, _, input_path = prepare_aqme_cleanup(tmp_path, monkeypatch, {})
    (tmp_path / "aqme").mkdir()
    instance.args.descp_level = "denovo"
    input_bytes = input_path.read_bytes()
    aqme_output_name = "AQME-ROBERT_denovo_example_b0.csv"
    sibling_file = tmp_path / aqme_output_name
    sibling_file.write_text("existing AQME output", encoding="utf-8")

    def emulate_aqme(command, cwd):
        aqme_input = pd.read_csv(command[command.index("--input") + 1])
        assert aqme_input["code_name"].notna().all()
        assert aqme_input["code_name"].is_unique
        aqme_input["descp1"] = [54, 65, 0, 6]
        aqme_input["descp2"] = [80, 7, 50, 58]
        aqme_input["descp3"] = [576, 6, 5, 8]
        aqme_input.iloc[::-1].to_csv(cwd / aqme_output_name, index=False)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("almos.cluster.subprocess.run", emulate_aqme)

    _, aqme_path = instance.run_aqme(["example"], str(input_path))
    assert input_path.read_bytes() == input_bytes
    assert read_text(sibling_file) == "existing AQME output"
    _, descriptor_df, output_path = instance.clean_up_cluster(
        aqme_path, ["example"], "example.csv", input_path
    )

    output_df = pd.read_csv(output_path, keep_default_na=False)
    assert output_df["code_name"].tolist() == ["001", "1", "NA", "004"]
    assert descriptor_df["descp1"].tolist() == [54, 65, 0, 6]


@pytest.mark.parametrize(
    "identifiers",
    [
        None,
        ["001", "1", "NA"],
        ["001", "1", "NA", "004", "extra"],
        ["001", "1", "NA", "extra"],
        ["001", "1", "NA", "NA"],
        ["001", "1", "NA", ""],
    ],
    ids=["no-column", "missing", "extra", "replacement", "duplicate", "blank"],
)
def test_aqme_cleanup_rejects_mismatched_code_names(tmp_path, monkeypatch, identifiers):
    values = [54, 65, 0, 6, 33]
    num_rows = len(identifiers) if identifiers is not None else 4
    aqme_rows = {
        "descp1": values[:num_rows],
        "descp2": [80, 7, 50, 58, 23][:num_rows],
        "descp3": [576, 6, 5, 8, 20][:num_rows],
    }
    if identifiers is not None:
        aqme_rows["code_name"] = identifiers
    instance, descriptor_csv, original_input_path = prepare_aqme_cleanup(
        tmp_path, monkeypatch, aqme_rows
    )
    log_lines = []
    instance.args.log.write = log_lines.append
    existing_output = tmp_path / "batch_0" / "example_b0.csv"
    existing_output.write_text("previous output", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        instance.clean_up_cluster(descriptor_csv, ["example"], "example.csv", original_input_path)

    assert excinfo.value.code == 18
    assert any("code_name" in line for line in log_lines)
    assert read_text(existing_output) == "previous output"


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


def build_chemical_space_viewer_payload():
    return {
        "targetColumn": "solubility",
        "targetIsNumeric": True,
        "descriptorColorColumns": ["TPSA", "MolWt"],
        "embeddings": {
            "PCA 2D": {"dims": 2, "x": [0.0, 1.0], "y": [1.0, 0.0], "trustworthiness": 0.91, "varianceRetained": 0.73, "areaCoverage": 0.84, "dispersion": 0.61},
            "PCA 3D": {"dims": 3, "x": [0.0, 1.0], "y": [1.0, 0.0], "z": [0.5, -0.5], "trustworthiness": 0.91, "varianceRetained": 0.73, "areaCoverage": None, "dispersion": None},
            "UMAP": {"dims": 2, "x": [0.2, 0.8], "y": [0.9, 0.1], "trustworthiness": 0.88, "varianceRetained": None, "areaCoverage": 0.79, "dispersion": 0.58},
        },
        "records": [
            {"name": "a", "selected": True, "selectionRegion": 0, "smiles": "CC", "target": 1.2, "svg": "<svg></svg>"},
            {"name": "b", "selected": False, "selectionRegion": 0, "smiles": "CO", "target": 0.8, "svg": ""},
        ],
        "colors": {
            "target": [1.2, 0.8],
            "descriptors": {"TPSA": [10.0, 20.0], "MolWt": [100.0, 120.0]},
        },
        "hasSmiles": True,
    }


def test_render_chemical_space_viewer_html_includes_color_controls(tmp_path):
    instance = build_cluster_stub(tmp_path)
    payload = build_chemical_space_viewer_payload()

    html = instance.render_chemical_space_viewer_html(payload, "", "demo.csv")

    assert "Color by" in html
    assert 'value="selected"' in html
    assert '<option value="clusters">clusters</option>' in html
    assert 'value="target"' in html
    assert 'value="descriptor::TPSA"' in html
    assert 'value="descriptor::MolWt"' in html
    assert '<option value="tanimoto">' not in html
    assert "PCA 2D" in html
    assert "PCA 3D" in html
    assert "UMAP" in html
    assert 'type: is3D ? "scatter3d" : "scattergl"' in html
    assert 'const errorBanner = document.getElementById("errorBanner");' in html
    assert '<input id="candidateSearch" type="search">' in html
    assert '<select id="batchFilter">' in html
    assert '<select id="selectionFilter">' in html
    assert '<select id="targetFilter">' in html
    assert 'id="resetFiltersButton"' in html
    assert 'id="exportCsvButton"' in html
    assert 'id="visibleCount" role="status"' in html
    assert "Hover over any point to preview its molecule, SMILES, and metadata." in html
    assert 'function axisBaseLabel(embedding)' in html
    assert "async function draw()" in html
    assert 'function plotTitle(embedding, coords)' in html
    assert 'area coverage: ${percentLabel(coords.areaCoverage)}' in html
    assert 'dispersion: ${percentLabel(coords.dispersion)}' in html
    assert '? visibleIndices.filter(i => gradientValues[i] !== null && gradientValues[i] !== undefined)' in html
    assert 'traces.push(makeTrace("All molecules", visibleIndices, {' in html
    assert 'const plotIndices = showLegend && indices.length === 0 ? [null] : indices;' in html
    assert 'if (!isClusterMode && hasSelectedCandidates)' in html
    assert 'showlegend: true,' in html
    assert 'margin: { l: 50, r: 20, t: 88, b: 45 },' in html
    assert 'y: 1.035,' in html
    assert 'await Plotly.react(plot, traces, layout, plotConfig);' in html
    assert 'await Plotly.newPlot(plot, traces, layout, plotConfig);' in html
    assert 'plot.on("plotly_click", event => {' in html
    assert 'plot.on("plotly_hover", event => {' in html
    assert "restorePinnedRecord();" in html
    assert "if (is3D) {" in html
    assert "layout.scene = {" in html
    assert "layout.xaxis = {" in html
    assert "layout.yaxis = {" in html
    assert "Plotly.purge(plot);" in html
    assert "Plotly.react(plot, traces, layout, plotConfig);" in html
    assert "Plotly.newPlot(plot, traces, layout, plotConfig);" in html


def test_render_chemical_space_viewer_colors_regions_and_highlights_representatives(
    tmp_path,
):
    instance = build_cluster_stub(tmp_path)
    payload = build_chemical_space_viewer_payload()

    html = instance.render_chemical_space_viewer_html(payload, "", "demo.csv")

    assert 'const isClusterMode = colorMode === "clusters";' in html
    assert "const selectionRegions = [...new Set(" in html
    assert 'makeTrace(`Cluster ${region + 1}`, clusterIndices' in html
    assert 'showLegend: false' in html
    assert 'symbol: "circle"' in html
    assert 'makeTrace("Selected representatives", selectedIndices' in html
    assert 'symbol: "diamond"' in html
    assert "colorValues: payload.records.map(record => clusterColor(record.selectionRegion))" in html


def test_render_chemical_space_viewer_uses_one_2d_renderer_and_selected_last(tmp_path):
    instance = build_cluster_stub(tmp_path)
    payload = build_chemical_space_viewer_payload()

    html = instance.render_chemical_space_viewer_html(payload, "", "demo.csv")

    assert 'type: is3D ? "scatter3d" : "scattergl"' in html
    assert "useGL" not in html
    assert 'width: is3D ? 0 : 0.6, color: "#64748b"' in html
    assert 'line: { width: 1, color: "#1f2937" }' in html
    assert 'line: { width: 1.5, color: "#064e3b" }' in html
    assert html.rindex('makeTrace("All molecules"') < html.rindex(
        'makeTrace("Selected"'
    )


def test_render_chemical_space_viewer_keeps_3d_ranges_and_disables_gradient_edges(
    tmp_path,
):
    instance = build_cluster_stub(tmp_path)
    payload = build_chemical_space_viewer_payload()

    html = instance.render_chemical_space_viewer_html(payload, "", "demo.csv")

    assert (
        'const backgroundMarkerLine = { width: is3D ? 0 : 0.6, color: "#64748b" };'
        in html
    )
    assert html.count("line: backgroundMarkerLine") == 2
    assert "const [zMin, zMax] = is3D ? axisBounds(coords.z) : [null, null];" in html
    assert "Math.min(...coords." not in html
    assert "Math.max(...coords." not in html
    assert (
        "const zPad = is3D ? Math.max((zMax - zMin) * 0.05, 1e-9) : null;"
        in html
    )
    assert 'autorange: false, range: [xMin - xPad, xMax + xPad]' in html
    assert 'autorange: false, range: [yMin - yPad, yMax + yPad]' in html
    assert 'autorange: false, range: [zMin - zPad, zMax + zPad]' in html


def test_render_chemical_space_viewer_supports_hover_preview_and_pinning(tmp_path):
    instance = build_cluster_stub(tmp_path)
    payload = build_chemical_space_viewer_payload()

    html = instance.render_chemical_space_viewer_html(payload, "", "demo.csv")

    assert 'id="unpinButton"' in html
    assert "function previewRecord(pointIndex)" in html
    assert "function pinRecord(pointIndex)" in html
    assert "function restorePinnedRecord()" in html
    assert "function clearPinnedRecord()" in html
    assert 'plot.on("plotly_hover", event => {' in html
    assert "previewRecord(hoveredPointIndex);" in html
    assert 'plot.on("plotly_unhover", () => {' in html
    assert "restorePinnedRecord();" in html
    assert "pinRecord(event.points[0].customdata);" in html
    assert 'unpinButton.addEventListener("click", clearPinnedRecord);' in html
    assert "record.selected" in html
    assert "Molecule drawings are included only for selected molecules." in html
    assert 'SMILES: ${escapeHtml(record.smiles || "NA")}' in html
    assert 'const PINNED_TRACE_NAME = "Pinned molecule";' in html
    assert "let pinnedTraceIndex = null;" in html
    assert "showlegend: showLegend" in html
    assert "traces.push(makeTrace(PINNED_TRACE_NAME, pinnedIndices, {" in html
    assert 'symbol: "circle-open"' in html
    assert 'color: "#047857"' in html
    assert 'line: { width: 3, color: "#064e3b" }' in html
    assert html.rindex('makeTrace("Selected"') < html.index(
        "makeTrace(PINNED_TRACE_NAME"
    )
    assert "function updatePinnedMarker(pointIndex)" in html
    assert "if (coords.dims === 3) return;" in html
    assert "Plotly.restyle(plot, update, [pinnedTraceIndex]);" in html
    assert "updatePinnedMarker(pointIndex);" in html
    assert "updatePinnedMarker(null);" in html
    assert 'plot.style.cursor = "crosshair";' in html
    assert 'plot.style.cursor = "";' in html
    assert "let hoveredPointIndex = null;" in html
    assert "hoveredPointIndex = event.points[0].customdata;" in html
    assert "hoveredPointIndex = null;" in html
    assert 'plot.addEventListener("click", () => {' in html
    assert "pinRecord(hoveredPointIndex);" in html
    assert "let native3DClickMoved = false;" in html
    assert 'plot.addEventListener("pointerdown", event => {' in html
    assert "native3DClickMoved = false;" in html
    assert 'plot.addEventListener("pointermove", event => {' in html
    assert "native3DClickMoved = true;" in html
    assert "if (coords.dims === 3 && !native3DClickMoved && hoveredPointIndex !== null)" in html


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
    instance.build_chemical_space_viewer = lambda **_kwargs: "batch_0/chemical_space/chemical_space_viewer.html"
    instance.export_chemical_space_csvs = lambda *_args, **_kwargs: [
        "batch_0/chemical_space/chemical_space_pca.csv",
        "batch_0/chemical_space/chemical_space_umap.csv",
    ]
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
    assert (tmp_path / "batch_0" / "chemical_space" / "coverage_descriptor_importance.csv").exists()


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
    assert fidelity["evaluated_points"] == 4
    assert fidelity["total_points"] == 4
    assert fidelity["error"] is None
    assert instance.compute_pca_2d_variance(np.array([[1.0], [2.0], [3.0]])) == 1.0
    assert instance.classify_visualization_local_quality(0.96) == "EXCELLENT"
    assert instance.classify_visualization_local_quality(0.85) == "ACCEPTABLE"
    assert instance.classify_visualization_local_quality(None) == "NOT COMPUTED"
    assert "rough visual guides" in instance.interpret_combined_2d_visualization_quality(0.7, 0.4, None)
    assert "local neighborhoods well" in instance.interpret_combined_2d_visualization_quality(0.92, 0.8, 0.93)
    assert "not computed" in instance.interpret_combined_2d_visualization_quality(None, 0.8, None).lower()


def test_embedding_fidelity_sampling_is_deterministic_and_keeps_selected_points(tmp_path):
    instance = build_cluster_stub(tmp_path)
    selected_mask = np.zeros(5000, dtype=bool)
    selected_mask[[3, 2500, 4999]] = True

    first_indices = instance.select_embedding_fidelity_indices(
        len(selected_mask), selected_mask
    )
    second_indices = instance.select_embedding_fidelity_indices(
        len(selected_mask), selected_mask
    )

    assert len(first_indices) == 2000
    assert len(np.unique(first_indices)) == 2000
    assert {3, 2500, 4999}.issubset(set(first_indices.tolist()))
    assert np.array_equal(first_indices, second_indices)


def test_compute_embedding_fidelity_reports_sampling_errors(tmp_path, monkeypatch):
    instance = build_cluster_stub(tmp_path)
    original_data = np.arange(40, dtype=float).reshape(20, 2)
    embedding = original_data.copy()
    selected_mask = np.zeros(20, dtype=bool)

    def fail_trustworthiness(*_args, **_kwargs):
        raise MemoryError("pairwise matrix is too large")

    monkeypatch.setattr("almos.cluster.trustworthiness", fail_trustworthiness)

    fidelity = instance.compute_embedding_fidelity(
        original_data,
        embedding,
        selected_mask,
    )

    assert fidelity["trustworthiness"] is None
    assert fidelity["evaluated_points"] == 20
    assert fidelity["total_points"] == 20
    assert fidelity["error"] == "pairwise matrix is too large"


def test_build_chemical_space_viewer_generates_html_and_payload_options(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "batch_0").mkdir()
    instance = build_cluster_stub(tmp_path)
    instance.args.name = "Code_Name"
    instance.args.y = "target"
    log_lines = []
    instance.args.log = SimpleNamespace(write=log_lines.append)
    instance.compute_umap_2d_embedding = lambda *_args, **_kwargs: (None, None, "UMAP is not installed")
    instance.molecule_svg_from_smiles = lambda smiles: f"<svg>{smiles}</svg>"
    fidelity_dimensions = []

    def record_fidelity_dimensions(original_data, embedding, selected_mask):
        fidelity_dimensions.append(embedding.shape[1])
        return {
            "trustworthiness": 0.9,
            "evaluated_points": len(original_data),
            "total_points": len(original_data),
            "error": None,
        }

    instance.compute_embedding_fidelity = record_fidelity_dimensions

    descp_df = pd.DataFrame(
        {
            "Code_Name": ["a", "b", "c"],
            "SMILES": ["CC", "CO", "CN"],
            "target": [1.0, 2.5, None],
            "batch": [0.0, 2.0, pd.NA],
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
    assert viewer_path == "batch_0/chemical_space/chemical_space_viewer.html"
    assert "* plotly.js v" in html
    assert '<script src="https://cdn.plot.ly/' not in html
    assert "descriptor::descp2" in html
    assert "descriptor::descp1" in html
    assert "target" in html
    assert "Selected" in html
    assert '"selectionRegion": 1' in html
    payload, _ = json.JSONDecoder().raw_decode(html.split("const payload = ", 1)[1])
    assert [record["batch"] for record in payload["records"]] == [0, 2, None]
    assert [record["target"] for record in payload["records"]] == ["1.0", "2.5", None]
    assert "PCA 3D" in html
    assert "No valid numeric value" in html or "Color by" in html
    assert fidelity_dimensions == [2, 3]
    assert any("3/3" in line for line in log_lines)


def test_build_chemical_space_viewer_draws_svg_only_for_selected_molecules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "batch_0").mkdir()
    instance = build_cluster_stub(tmp_path)
    instance.args.name = "Code_Name"
    instance.args.y = "target"
    instance.args.log = SimpleNamespace(write=lambda *_args, **_kwargs: None)
    instance.compute_umap_2d_embedding = lambda *_args, **_kwargs: (None, None, "UMAP is not installed")
    svg_calls = []
    instance.molecule_svg_from_smiles = lambda smiles: svg_calls.append(smiles) or f"<svg>{smiles}</svg>"

    descp_df = pd.DataFrame(
        {
            "Code_Name": ["a", "b", "c"],
            "SMILES": ["CC", "CO", "CN"],
            "target": [1.0, 2.5, 3.5],
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

    instance.build_chemical_space_viewer(
        descp_df=descp_df,
        selected_indices=[1],
        coverage_result=coverage_result,
        file_name="demo.csv",
    )

    assert svg_calls == ["CO"]


def test_export_chemical_space_csvs_writes_pca_and_umap_files(tmp_path):
    instance = build_full_cluster_stub()
    instance.args.name = "Code_Name"
    instance.args.y = "target"
    instance.args.log = SimpleNamespace(write=lambda *_args, **_kwargs: None)
    descp_df = pd.DataFrame(
        {
            "Code_Name": ["a", "b", "c"],
            "SMILES": ["CC", "CO", "CN"],
            "target": [1.0, 2.0, 3.0],
            "batch": [0, None, 1],
        }
    )
    embeddings = {
        "PCA 3D": {
            "dims": 3,
            "x": [0.0, 1.0, 2.0],
            "y": [0.1, 1.1, 2.1],
            "z": [0.2, 1.2, 2.2],
        },
        "UMAP": {
            "dims": 2,
            "x": [3.0, 4.0, 5.0],
            "y": [3.1, 4.1, 5.1],
        },
    }
    output_paths = instance.export_chemical_space_csvs(
        descp_df,
        np.array([0, 1, 2]),
        embeddings,
    )

    assert "batch_0/chemical_space/chemical_space_pca.csv" in output_paths
    assert "batch_0/chemical_space/chemical_space_umap.csv" in output_paths

    pca_df = pd.read_csv("batch_0/chemical_space/chemical_space_pca.csv")
    umap_df = pd.read_csv("batch_0/chemical_space/chemical_space_umap.csv")
    assert list(pca_df.columns) == ["Code_Name", "batch", "pc1", "pc2", "pc3", "smiles"]
    assert list(umap_df.columns) == ["Code_Name", "batch", "umap_1", "umap_2", "smiles"]
    assert pca_df.loc[1, "Code_Name"] == "b"
    assert pd.isna(pca_df.loc[1, "batch"])
    assert pca_df.loc[1, "smiles"] == "CO"
    assert umap_df.loc[2, "umap_2"] == 5.1
