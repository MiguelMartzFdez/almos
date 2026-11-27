#!/usr/bin/env python

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QProgressBar, QTextEdit

import almos.easyalmos as easyalmos_pkg
import almos.easyalmos.easyalmos as easyalmos_module


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def write_gui_csv(path: Path, with_batch: bool = False):
    data = {
        "Name": ["a", "b", "c", "d"],
        "feat1": [0.0, 1.0, 2.0, 3.0],
        "feat2": [3.0, 1.0, 4.0, 2.0],
        "target": [1.1, 2.2, 3.3, 4.4],
    }
    if with_batch:
        data["batch"] = [0, 0, None, None]
    pd.DataFrame(data).to_csv(path, index=False)


def build_tabs():
    progress = QProgressBar()
    console = QTextEdit()
    cluster_tab = easyalmos_module.ClusteringTab(progress, console)
    al_tab = easyalmos_module.ActiveLearningTab(progress, console)
    return progress, console, cluster_tab, al_tab


def test_easyalmos_package_exports_and_main(monkeypatch):
    assert hasattr(easyalmos_pkg, "main")
    assert hasattr(easyalmos_pkg, "ALMOSApp")

    created = {"app": 0, "window": 0, "shown": 0}

    class FakeApp:
        def __init__(self, _args):
            created["app"] += 1

        def exec(self):
            return 37

    class FakeWindow:
        def __init__(self):
            created["window"] += 1

        def show(self):
            created["shown"] += 1

    monkeypatch.setattr(easyalmos_module, "QApplication", FakeApp)
    monkeypatch.setattr(easyalmos_module, "ALMOSApp", FakeWindow)

    assert easyalmos_module.main() == 37
    assert created == {"app": 1, "window": 1, "shown": 1}


def test_easyalmos_app_construction_headless(qapp):
    window = easyalmos_module.ALMOSApp()
    assert window.windowTitle() == "EasyALMOS"
    assert window.tabs.count() == 2
    assert window.tabs.tabText(0) == "Clustering"
    assert window.tabs.tabText(1) == "Active Learning"
    window.close()


def test_clustering_tab_select_file_and_build_commands(qapp, tmp_path, monkeypatch):
    _, _, cluster_tab, _ = build_tabs()
    csv_path = tmp_path / "cluster.csv"
    write_gui_csv(csv_path, with_batch=False)

    monkeypatch.setattr(
        easyalmos_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(csv_path), "CSV Files (*.csv)"),
    )
    cluster_tab.select_file()

    assert cluster_tab.file_path == str(csv_path)
    assert cluster_tab.file_chip.text() == "cluster.csv"
    assert cluster_tab.name_dropdown.count() == 5
    assert cluster_tab.y_dropdown.count() == 5
    assert "feat1" in cluster_tab.all_columns

    cluster_tab.name_dropdown.setCurrentText("Name")
    cluster_tab.y_dropdown.setCurrentText("target")
    cluster_tab.n_points_entry.setText("20")
    cluster_tab.ignore_selector.selected_list.addItem("feat2")

    command = cluster_tab.build_command()
    assert "--cluster" in command
    assert "--n_points" in command and "20" in command
    assert "--name" in command and "Name" in command
    assert "--y" in command and "target" in command
    assert "--ignore" in command and "[feat2]" in command

    cluster_tab.evaluate_checkbox.setChecked(True)
    cluster_tab.update_option_states()
    assert cluster_tab.n_points_entry.isEnabled() is False
    assert cluster_tab.aqme_checkbox.isEnabled() is False
    eval_command = cluster_tab.build_command()
    assert "--evaluate" in eval_command
    assert "--n_points" not in eval_command

    cluster_tab.evaluate_checkbox.setChecked(False)
    cluster_tab.aqme_checkbox.setChecked(True)
    cluster_tab.update_option_states()
    assert cluster_tab.descp_combo.isEnabled() is True
    aqme_command = cluster_tab.build_command()
    assert "--aqme" in aqme_command
    assert aqme_command[aqme_command.index("--name") + 1] == "Name"
    assert "--descp_level" in aqme_command and "interpret" in aqme_command


def test_clustering_tab_validation_and_run_handler(qapp, tmp_path, monkeypatch):
    _, _, cluster_tab, _ = build_tabs()

    warnings = []
    monkeypatch.setattr(
        easyalmos_module.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args[2]),
    )
    started = []
    monkeypatch.setattr(cluster_tab, "start_command", lambda command, working_dir: started.append((command, working_dir)))

    cluster_tab.run_clustering()
    assert warnings[-1] == "Please select a CSV file."
    assert started == []

    csv_path = tmp_path / "cluster.csv"
    write_gui_csv(csv_path, with_batch=False)
    cluster_tab.file_path = str(csv_path)
    cluster_tab.name_dropdown.clear()
    cluster_tab.name_dropdown.addItems(["Select a name column", "Name"])
    cluster_tab.y_dropdown.clear()
    cluster_tab.y_dropdown.addItems(["Optional target column", "target"])
    cluster_tab.run_clustering()
    assert warnings[-1] == "Please select an identifier column."

    cluster_tab.name_dropdown.setCurrentText("Name")
    cluster_tab.run_clustering()
    assert len(started) == 1
    assert started[0][1] == str(csv_path.parent)


def test_active_learning_tab_select_file_and_build_commands(qapp, tmp_path, monkeypatch):
    _, _, _, al_tab = build_tabs()
    csv_path = tmp_path / "al.csv"
    write_gui_csv(csv_path, with_batch=True)

    monkeypatch.setattr(
        easyalmos_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(csv_path), "CSV Files (*.csv)"),
    )
    al_tab.select_file()

    assert al_tab.file_path == str(csv_path)
    assert al_tab.file_chip.text() == "al.csv"
    assert "batch" in al_tab.all_columns

    al_tab.name_dropdown.setCurrentText("Name")
    al_tab.y_dropdown.setCurrentText("target")
    al_tab.n_exps_entry.setText("3")
    al_tab.ignore_selector.selected_list.addItem("feat1")

    auto_command = al_tab.build_command()
    assert "--al" in auto_command
    assert "--objective" in auto_command and "max" in auto_command
    assert "--n_exps" in auto_command and "3" in auto_command
    assert "--ignore" in auto_command and "[feat1]" in auto_command

    al_tab.mode_combo.setCurrentText("Model mode (highest uncertainty)")
    al_tab.update_strategy_ui()
    assert al_tab.objective_combo.isEnabled() is False
    assert al_tab.alpha_entry.isEnabled() is False
    model_command = al_tab.build_command()
    assert "--mode" in model_command and "model" in model_command
    assert "--objective" not in model_command
    assert "predictive uncertainty" in al_tab.strategy_hint.text().lower()

    al_tab.mode_combo.setCurrentText("Hit mode (objective-driven)")
    al_tab.objective_combo.setCurrentText("Minimize target")
    al_tab.alpha_entry.setText("0.5")
    al_tab.update_strategy_ui()
    assert al_tab.objective_combo.isEnabled() is True
    assert al_tab.alpha_entry.isEnabled() is True
    hit_command = al_tab.build_command()
    assert "--mode" in hit_command and "hit" in hit_command
    assert "--objective" in hit_command and "min" in hit_command
    assert "--alpha" in hit_command and "0.5" in hit_command


def test_active_learning_validation_and_run_handler(qapp, tmp_path, monkeypatch):
    _, _, _, al_tab = build_tabs()

    warnings = []
    monkeypatch.setattr(
        easyalmos_module.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args[2]),
    )
    started = []
    monkeypatch.setattr(al_tab, "start_command", lambda command, working_dir: started.append((command, working_dir)))

    al_tab.run_active_learning()
    assert warnings[-1] == "Please select a CSV file."

    csv_path = tmp_path / "al.csv"
    write_gui_csv(csv_path, with_batch=True)
    al_tab.file_path = str(csv_path)
    al_tab.name_dropdown.clear()
    al_tab.name_dropdown.addItems(["Select a name column", "Name"])
    al_tab.y_dropdown.clear()
    al_tab.y_dropdown.addItems(["Select a target column", "target"])

    al_tab.run_active_learning()
    assert warnings[-1] == "Please select both identifier and target columns."

    al_tab.name_dropdown.setCurrentText("Name")
    al_tab.y_dropdown.setCurrentText("target")
    al_tab.mode_combo.setCurrentText("Find hits")
    al_tab.alpha_entry.setText("2")
    al_tab.run_active_learning()
    assert warnings[-1] == "Alpha must be a number between 0 and 1."

    al_tab.alpha_entry.setText("0.4")
    al_tab.run_active_learning()
    assert len(started) == 1
    assert started[0][1] == str(csv_path.parent)


@pytest.mark.parametrize(
    ("folder", "filename", "uses_parent"),
    [
        ("batch_0", "dataset_b0.csv", True),
        ("batch_23", "dataset_b23.csv", True),
        ("batch_1", "pool.csv", False),
        ("batch_23", "dataset_b0.csv", False),
        ("batch_plots", "dataset_b0.csv", False),
        ("batch_2_exports", "dataset_b2.csv", False),
        ("batch_1/exports", "dataset_b1.csv", False),
    ],
)
def test_working_directory_uses_parent_only_for_an_almos_batch_file(qapp, tmp_path, folder, filename, uses_parent):
    _, _, cluster_tab, al_tab = build_tabs()
    campaign = tmp_path / "campaign"
    source_dir = campaign / folder
    source_dir.mkdir(parents=True)
    csv_path = source_dir / filename
    write_gui_csv(csv_path, with_batch=True)
    expected = campaign if uses_parent else source_dir

    for tab in (cluster_tab, al_tab):
        tab.file_path = str(csv_path)
        assert tab.working_directory() == str(expected)


def test_invalid_csv_preserves_previous_selection(qapp, tmp_path, monkeypatch):
    _, _, cluster_tab, al_tab = build_tabs()
    valid_csv = tmp_path / "valid.csv"
    write_gui_csv(valid_csv, with_batch=True)
    empty_csv = tmp_path / "empty.csv"
    empty_csv.touch()
    malformed_csv = tmp_path / "malformed.csv"
    malformed_csv.write_text('Name,target\n"unclosed,2\n', encoding="utf-8")
    header_only_csv = tmp_path / "header-only.csv"
    header_only_csv.write_text("Name,target\n", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    for tab in (cluster_tab, al_tab):
        choices = iter((valid_csv, empty_csv, malformed_csv, header_only_csv))
        monkeypatch.setattr(easyalmos_module.QFileDialog, "getOpenFileName", lambda *args: (str(next(choices)), ""))
        tab.select_file()
        tab.name_dropdown.setCurrentText("Name")
        tab.y_dropdown.setCurrentText("target")
        tab.ignore_selector.available_list.item(1).setSelected(True)
        tab.ignore_selector.move_to_selected()

        for invalid_csv in (empty_csv, malformed_csv, header_only_csv):
            tab.select_file()
            assert invalid_csv.name in warnings[-1]
            assert tab.file_path == str(valid_csv)
            assert tab.file_chip.text() == valid_csv.name
            assert tab.name_dropdown.currentText() == "Name"
            assert tab.y_dropdown.currentText() == "target"
            assert tab.ignore_selector.values() == ["feat1"]


@pytest.mark.parametrize("invalid_budget", ["0", "-2", "1.5", "many"])
def test_budget_fields_require_positive_integers(qapp, invalid_budget):
    _, _, cluster_tab, al_tab = build_tabs()
    for tab, entry, flag in (
        (cluster_tab, cluster_tab.n_points_entry, "--n_points"),
        (al_tab, al_tab.n_exps_entry, "--n_exps"),
    ):
        tab.file_path = "dataset.csv"
        tab.name_dropdown.addItem("Name")
        tab.name_dropdown.setCurrentText("Name")
        tab.y_dropdown.addItem("target")
        tab.y_dropdown.setCurrentText("target")
        assert flag not in tab.build_command()

        entry.setText(invalid_budget)
        with pytest.raises(ValueError, match="positive integer"):
            tab.build_command()


def test_evaluation_requires_identifier_even_if_aqme_was_checked(qapp):
    _, _, cluster_tab, _ = build_tabs()
    cluster_tab.file_path = "dataset.csv"
    cluster_tab.aqme_checkbox.setChecked(True)
    cluster_tab.evaluate_checkbox.setChecked(True)

    with pytest.raises(ValueError, match="identifier"):
        cluster_tab.build_command()


def test_worker_emits_one_failed_terminal_event_on_launch_error(qapp, tmp_path):
    worker = easyalmos_module.WorkerThread([str(tmp_path / "missing-executable")], str(tmp_path))
    terminal = QSignalSpy(worker.process_finished)
    worker.start()
    assert worker.wait(5000)
    qapp.processEvents()

    assert terminal.count() == 1
    assert terminal.at(0)[0] != 0


def test_worker_reports_launch_failure_and_restores_controls(qapp, tmp_path, monkeypatch):
    window = easyalmos_module.ALMOSApp()
    tab = window.clustering_tab
    warnings = []
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    tab.start_command([str(tmp_path / "missing-executable")], str(tmp_path))
    worker = tab.worker
    assert worker.wait(5000)
    qapp.processEvents()

    assert tab.worker is None
    assert tab.run_button.isEnabled()
    assert window.active_learning_tab.run_button.isEnabled()
    assert not tab.stop_button.isEnabled()
    assert window.progress.maximum() == 100
    assert warnings == [tab.failure_message]
    assert "Process did not complete correctly." in window.console_output.toPlainText()
    window.close()


def test_worker_thread_start_error_restores_controls(qapp, tmp_path, monkeypatch):
    window = easyalmos_module.ALMOSApp()
    tab = window.clustering_tab
    warnings = []
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    def fail_to_start(_worker):
        raise RuntimeError("Thread could not start")

    monkeypatch.setattr(easyalmos_module.WorkerThread, "start", fail_to_start)
    tab.start_command([sys.executable, "-c", "pass"], str(tmp_path))

    assert tab.worker is None
    assert tab.run_button.isEnabled()
    assert window.active_learning_tab.run_button.isEnabled()
    assert not tab.stop_button.isEnabled()
    assert window.progress.maximum() == 100
    assert warnings == [tab.failure_message]
    assert "Thread could not start" in window.console_output.toPlainText()
    window.close()


def test_invalid_active_learning_batch_fails_in_gui_and_campaign_log(qapp, tmp_path, monkeypatch):
    window = easyalmos_module.ALMOSApp()
    tab = window.active_learning_tab
    campaign = tmp_path / "campaign"
    source = campaign / "batch_0" / "dataset_b0.csv"
    source.parent.mkdir(parents=True)
    contents = b"Name,target,batch\na,,0\nb,2.0,0\nc,,\n"
    source.write_bytes(contents)

    repo_path = str(Path(easyalmos_module.__file__).resolve().parents[2])
    env_paths = [repo_path, os.environ.get("PYTHONPATH", "")]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, env_paths)))
    monkeypatch.setattr(easyalmos_module, "get_almos_python_executable", lambda: sys.executable)
    monkeypatch.setattr(easyalmos_module.QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    results = []
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args: results.append("warning"))
    monkeypatch.setattr(easyalmos_module.QMessageBox, "information", lambda *args: results.append("success"))
    tab.select_file()
    tab.name_dropdown.setCurrentText("Name")
    tab.y_dropdown.setCurrentText("target")

    tab.run_active_learning()
    assert tab.worker.wait(30000)
    qapp.processEvents()

    assert results == ["warning"]
    assert "missing target" in window.console_output.toPlainText()
    assert "missing target" in (campaign / "AL_data.dat").read_text(encoding="utf-8")
    assert not (source.parent / "AL_data.dat").exists()
    assert not (campaign / "batch_1").exists()
    assert source.read_bytes() == contents
    window.close()


def test_clustering_result_opens_viewer_and_prefills_active_learning(qapp, tmp_path, monkeypatch):
    window = easyalmos_module.ALMOSApp()
    source = tmp_path / "campaign.csv"
    write_gui_csv(source)
    output = tmp_path / "batch_0"
    output.mkdir()
    dataset = output / "campaign_b0.csv"
    write_gui_csv(dataset, with_batch=True)
    viewer = output / "chemical_space_viewer.html"
    viewer.write_text("<html></html>", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "run_id": "test-run",
        "status": "completed",
        "module": "cluster",
        "input": {"path": str(source)},
        "effective_options": {"name": "Name", "y": "target", "ignore": ["feat2"]},
        "summary": {"selected_count": 2},
        "artifacts": [dataset.name, viewer.name, "../campaign.csv"],
    }
    command = [
        sys.executable, "-c",
        "from pathlib import Path; import sys; Path('batch_0/run.json').write_text(sys.argv[1], encoding='utf-8')",
        json.dumps(manifest),
    ]
    tab = window.clustering_tab
    tab.file_path = str(source)
    monkeypatch.setattr(easyalmos_module.QMessageBox, "information", lambda *args: None)
    opened = []
    monkeypatch.setattr(easyalmos_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)

    tab.start_command(command, str(tmp_path))
    assert tab.worker.wait(5000)
    qapp.processEvents()

    assert "Batch 0" in window.results_summary.text()
    window.open_viewer_button.click()
    assert Path(opened[-1]) == viewer
    window.continue_al_button.click()
    al_tab = window.active_learning_tab
    assert window.tabs.currentWidget() is al_tab
    assert Path(al_tab.file_path) == dataset
    assert al_tab.name_dropdown.currentText() == "Name"
    assert al_tab.y_dropdown.currentText() == "target"
    assert al_tab.ignore_selector.values() == ["feat2"]
    assert al_tab.working_directory() == str(tmp_path)
    assert al_tab.campaign_directory == tmp_path
    window.close()


@pytest.mark.parametrize("has_target", [True, False])
def test_import_measurements_loads_a_new_dataset_for_al(qapp, tmp_path, monkeypatch, has_target):
    window = easyalmos_module.ALMOSApp()
    tab = window.active_learning_tab
    original = tmp_path / "pool_b0.csv"
    if has_target:
        original.write_bytes(b"Name,target,batch\n0001,,0\n0002,,0\n0003,,\n")
    else:
        original.write_bytes(b"Name,batch\n0001,0\n0002,0\n0003,\n")
    measurements = tmp_path / "measurements.csv"
    measurements.write_bytes(b"Name,target\n0002,9.5\n0001,1.5\n")
    destination = tmp_path / "pool_measured_b0.csv"
    originals = [path.read_bytes() for path in (original, measurements)]
    assert tab.load_dataset(str(original))
    tab.name_dropdown.setCurrentText("Name")
    if has_target:
        tab.y_dropdown.setCurrentText("target")
    monkeypatch.setattr(easyalmos_module.QFileDialog, "getOpenFileName", lambda *args: (str(measurements), ""))
    monkeypatch.setattr(easyalmos_module.QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
    monkeypatch.setattr(easyalmos_module.QMessageBox, "information", lambda *args: None)
    warnings = []
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    tab.import_measurements_button.click()

    assert not warnings
    assert Path(tab.file_path) == destination
    assert tab.name_dropdown.currentText() == "Name"
    assert tab.y_dropdown.currentText() == "target"
    table = pd.read_csv(destination, converters={"Name": str})
    assert table["Name"].tolist() == ["0001", "0002", "0003"]
    assert table["target"].iloc[:2].tolist() == [1.5, 9.5]
    assert pd.isna(table["target"].iloc[2])
    assert [path.read_bytes() for path in (original, measurements)] == originals
    window.close()


def test_only_one_workflow_can_run_with_shared_console(qapp, tmp_path, monkeypatch):
    window = easyalmos_module.ALMOSApp()
    cluster_tab = window.clustering_tab
    al_tab = window.active_learning_tab
    monkeypatch.setattr(easyalmos_module.QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args: None)

    cluster_tab.start_command([sys.executable, "-c", "print('clustering output')"], str(tmp_path))
    first_worker = cluster_tab.worker
    window.console_output.append("existing output")
    al_was_disabled = not al_tab.run_button.isEnabled()
    al_tab.start_command([sys.executable, "-c", "print('learning output')"], str(tmp_path))
    competing_worker = al_tab.worker
    console_before_finish = window.console_output.toPlainText()
    assert first_worker.wait(5000)
    if competing_worker is not None:
        assert competing_worker.wait(5000)
    qapp.processEvents()

    assert al_was_disabled
    assert competing_worker is None
    assert "existing output" in console_before_finish
    assert "clustering output" in window.console_output.toPlainText()
    assert al_tab.run_button.isEnabled()
    assert cluster_tab.run_button.isEnabled()
    window.close()


def test_stop_process_and_finish_handlers(qapp, monkeypatch):
    _, console, cluster_tab, _ = build_tabs()

    monkeypatch.setattr(easyalmos_module.QMessageBox, "question", lambda *args, **kwargs: easyalmos_module.QMessageBox.No)
    cluster_tab.worker = SimpleNamespace(isRunning=lambda: True)
    stop_calls = []
    monkeypatch.setattr(easyalmos_module.QTimer, "singleShot", lambda _delay, callback: stop_calls.append(callback))
    easyalmos_module.stop_process(cluster_tab)
    assert stop_calls == []

    monkeypatch.setattr(easyalmos_module.QMessageBox, "question", lambda *args, **kwargs: easyalmos_module.QMessageBox.Yes)
    fake_worker = SimpleNamespace(isRunning=lambda: True, stop=lambda: stop_calls.append("stopped"))
    cluster_tab.worker = fake_worker
    easyalmos_module.stop_process(cluster_tab)
    assert cluster_tab.manual_stop is True
    assert cluster_tab.stop_button.isEnabled() is False

    infos = []
    warns = []
    monkeypatch.setattr(easyalmos_module.QMessageBox, "information", lambda *args, **kwargs: infos.append(args[2]))
    monkeypatch.setattr(easyalmos_module.QMessageBox, "warning", lambda *args, **kwargs: warns.append(args[2]))

    cluster_tab.worker = SimpleNamespace(process=None)
    cluster_tab.manual_stop = True
    cluster_tab.console_output.setPlainText("to be cleared")
    cluster_tab.on_process_finished(-1)
    assert cluster_tab.console_output.toPlainText() == ""
    assert infos[-1] == "ALMOS has been successfully stopped."

    cluster_tab.worker = SimpleNamespace(process=None)
    cluster_tab.on_process_finished(0)
    assert infos[-1] == cluster_tab.success_message
    assert "successfully" in console.toPlainText().lower()

    cluster_tab.worker = SimpleNamespace(process=None)
    cluster_tab.on_process_finished(1)
    assert warns[-1] == cluster_tab.failure_message


def test_close_event_stops_running_workers(qapp, monkeypatch):
    window = easyalmos_module.ALMOSApp()

    class FakeEvent:
        def __init__(self):
            self.accepted = False
            self.ignored = False

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    event = FakeEvent()
    monkeypatch.setattr(easyalmos_module.QMessageBox, "question", lambda *args, **kwargs: easyalmos_module.QMessageBox.No)
    window.closeEvent(event)
    assert event.accepted is True

    stop_calls = []
    wait_calls = []
    fake_worker = SimpleNamespace(
        isRunning=lambda: True,
        stop=lambda: stop_calls.append(True),
        wait=lambda: wait_calls.append(True),
    )
    window.clustering_tab.worker = fake_worker
    event = FakeEvent()
    monkeypatch.setattr(easyalmos_module.QMessageBox, "question", lambda *args, **kwargs: easyalmos_module.QMessageBox.Yes)
    window.closeEvent(event)
    assert event.accepted is True
    assert stop_calls and wait_calls
    window.close()


def test_easyalmos_pkg_reexport_survives_reload():
    reloaded_pkg = importlib.reload(easyalmos_pkg)
    assert reloaded_pkg.main is not None
    assert reloaded_pkg.ALMOSApp is not None
