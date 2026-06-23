#!/usr/bin/env python

from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
