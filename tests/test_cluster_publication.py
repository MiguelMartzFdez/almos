import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from almos.cluster import cluster
from almos.utils import write_run_manifest


def snapshot(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def seed_previous_run(directory):
    for name, contents in {
        "run.json": '{"run_id":"prior","status":"completed"}',
        "run.previous.json": '{"run_id":"earlier","status":"completed"}',
        "selection_b0.csv": "code_name,measurement\na,42\n",
        "CLUSTER_data.dat": "previous successful log",
        "chemical_space/chemical_space_viewer.html": "previous viewer",
        "chemical_space/manual_measurements.csv": "code_name,measurement\na,42\n",
        "selection_diagnostics/PCA/pca_area_coverage.png": "previous diagnostic",
    }.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cluster, "prepare_auto_budget_umap_area_context", lambda *_: {})
    monkeypatch.setattr(cluster, "compute_umap_2d_embedding", lambda *_: (None, None, "UMAP disabled"))
    return tmp_path


def write_input(path, *, evaluate):
    contents = (
        "code_name,descp1,descp2,descp3,batch\n"
        "a,54,76,576,{batch}\nb,65,7,6,\nc,0,876,5,\n"
    )
    path.write_text(contents.format(batch="0" if evaluate else ""), encoding="utf-8")
    return path.read_bytes()


@pytest.mark.parametrize("evaluate, has_previous_run", [(True, True), (False, True), (False, False)])
def test_cluster_failed_manifest_preserves_the_previous_batch(campaign, monkeypatch, evaluate, has_previous_run):
    source = campaign / "selection.csv"
    input_bytes = write_input(source, evaluate=evaluate)
    batch = campaign / "batch_0"
    if has_previous_run:
        seed_previous_run(batch)
    before = snapshot(batch)

    def fail_after_manifest(*args, **kwargs):
        write_run_manifest(*args, **kwargs)
        assert batch.exists() is has_previous_run
        assert snapshot(batch) == before
        raise OSError("manifest publication interrupted")

    monkeypatch.setattr("almos.cluster.write_run_manifest", fail_after_manifest)

    with pytest.raises(OSError, match="manifest publication interrupted"):
        cluster(input=str(source), evaluate=evaluate, n_points=1)

    assert source.read_bytes() == input_bytes
    assert batch.exists() is has_previous_run
    assert snapshot(batch) == before
    failure_log = (campaign / "CLUSTER_data.dat").read_text(encoding="utf-8")
    assert "manifest publication interrupted" in failure_log
    assert list(campaign.glob(".almos-cluster-*")) == []


def test_cluster_failed_directory_rename_restores_batch_and_aqme(campaign, monkeypatch):
    source = campaign / "selection.csv"
    source.write_text("code_name,SMILES,batch\na,CC,0\nb,CO,\nc,CN,\n", encoding="utf-8")
    input_bytes = source.read_bytes()
    batch = campaign / "batch_0"
    seed_previous_run(batch)
    aqme = campaign / "aqme"
    aqme.mkdir()
    old_aqme_descriptors = aqme / "AQME-ROBERT_denovo_selection_b0.csv"
    old_aqme_descriptors.write_bytes(b"previous AQME output")
    (aqme / "notes.txt").write_bytes(b"lab notes")
    before_batch = snapshot(batch)
    before_aqme = snapshot(aqme)

    def emulate_aqme(_command, cwd):
        (cwd / old_aqme_descriptors.name).write_text(
            "code_name,descp1,descp2,descp3\na,54,76,576\nb,65,7,6\nc,0,876,5\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    rename = Path.rename

    def fail_on_new_batch(path, destination):
        if path.name == "batch_0" and Path(destination) == batch and snapshot(path) != before_batch:
            raise OSError("batch directory is blocked")
        return rename(path, destination)

    monkeypatch.setattr("almos.cluster.check_dependencies", lambda *_: None)
    monkeypatch.setattr("almos.cluster.subprocess.run", emulate_aqme)
    monkeypatch.setattr(Path, "rename", fail_on_new_batch)

    with pytest.raises(OSError, match="batch directory is blocked"):
        cluster(input=str(source), evaluate=True, aqme=True, descp_level="denovo")

    assert source.read_bytes() == input_bytes
    assert snapshot(batch) == before_batch
    assert snapshot(aqme) == before_aqme
    assert list(campaign.glob(".almos-cluster-*")) == []

    monkeypatch.setattr(Path, "rename", rename)
    cluster(input=str(source), evaluate=True, aqme=True, descp_level="denovo")

    assert old_aqme_descriptors.read_bytes() != before_aqme[old_aqme_descriptors.name]
    assert (aqme / "notes.txt").read_bytes() == before_aqme["notes.txt"]
    assert json.loads((batch / "run.json").read_text(encoding="utf-8"))["status"] == "completed"


def test_cluster_success_publishes_new_outputs_and_preserves_experimental_files(campaign):
    batch = campaign / "batch_0"
    seed_previous_run(batch)
    source = batch / "selection_b0.csv"
    source.write_text(
        "code_name,descp1,descp2,descp3,measurement,batch\n"
        "a,54,76,576,42,0\nb,65,7,6,,\nc,0,876,5,,\n",
        encoding="utf-8",
    )
    before = snapshot(batch)

    cluster(input=str(source), evaluate=True, y="measurement")

    assert source.read_bytes() == before[source.name]
    assert (batch / "run.previous.json").read_bytes() == before["run.json"]
    notes = "chemical_space/manual_measurements.csv"
    assert (batch / notes).read_bytes() == before[notes]
    manifest = json.loads((batch / "run.json").read_text(encoding="utf-8"))
    assert manifest["summary"] == {"mode": "evaluate", "selected_count": 1}
    assert all((batch / artifact).is_file() for artifact in manifest["artifacts"])
    viewer = "chemical_space/chemical_space_viewer.html"
    assert (batch / viewer).read_bytes() != before[viewer]
