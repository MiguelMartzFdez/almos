from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
from importlib.resources import as_file, files
from pathlib import Path

import pandas as pd
import psutil
from ansi2html import Ansi2HTMLConverter
from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_STYLESHEET = """
QMainWindow {
    background: #f4f0e8;
}
QTabWidget::pane {
    border: 1px solid #d8d0c4;
    background: #fbfaf7;
    border-radius: 12px;
}
QScrollArea {
    background: #f4f0e8;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: #f4f0e8;
}
QTabBar::tab {
    background: #e7dece;
    color: #47382b;
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #fbfaf7;
    color: #2e241d;
}
QGroupBox {
    background: #fffdf8;
    border: 1px solid #ddd3c6;
    border-radius: 14px;
    margin-top: 12px;
    font-weight: 600;
    color: #2e241d;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}
QLabel {
    color: #3f3328;
}
QLineEdit, QComboBox, QListWidget, QTextEdit {
    background: white;
    border: 1px solid #cdbfae;
    border-radius: 8px;
    padding: 7px 9px;
    color: #2e241d;
}
QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTextEdit:focus {
    border: 1px solid #9f7a4f;
}
QPushButton {
    background: #8e6c48;
    color: white;
    border: none;
    border-radius: 9px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #775636;
}
QPushButton:disabled {
    background: #bdb4a7;
    color: #f4f4f4;
}
QCheckBox {
    color: #3f3328;
}
QProgressBar {
    border: 1px solid #d0c4b7;
    border-radius: 8px;
    background: #f0ebe3;
}
QProgressBar::chunk {
    background: #7e9f6e;
    border-radius: 8px;
}
"""

LIST_STYLE = """
QListWidget {
    border: 1px solid #d2c4b1;
    padding: 4px;
    font-family: Consolas;
    font-size: 12px;
    background: white;
}
QListWidget::item:selected {
    background: #9f7a4f;
    color: white;
}
"""

RUN_BUTTON_STYLE = """
QPushButton {
    background-color: #6b8e5f;
    color: white;
    font-size: 14px;
    padding: 10px 18px;
    border: none;
    border-radius: 10px;
    font-weight: 700;
}
QPushButton:hover {
    background-color: #58764f;
}
QPushButton:disabled {
    background-color: #b0b0b0;
    color: #eeeeee;
}
"""

STOP_BUTTON_STYLE = """
QPushButton {
    background-color: #b74a3d;
    color: white;
    font-size: 14px;
    padding: 10px 18px;
    border: none;
    border-radius: 10px;
    font-weight: 700;
}
QPushButton:hover {
    background-color: #98392d;
}
QPushButton:disabled {
    background-color: #b0b0b0;
    color: #eeeeee;
}
"""


class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


def list_values(list_widget: QListWidget) -> list[str]:
    return [list_widget.item(i).text() for i in range(list_widget.count())]


def get_almos_python_executable() -> str:
    candidates = []
    base_executable = getattr(sys, "_base_executable", None)
    if base_executable:
        candidates.append(Path(base_executable))
    candidates.append(Path(sys.executable))

    for candidate in candidates:
        if not candidate:
            continue
        candidate_name = candidate.name.lower()
        if candidate_name.startswith("python") and candidate.exists():
            if candidate_name == "pythonw.exe":
                python_console = candidate.with_name("python.exe")
                if python_console.exists():
                    return str(python_console)
            return str(candidate)

        python_console = candidate.parent / ("python.exe" if os.name == "nt" else "python")
        if python_console.exists():
            return str(python_console)

    return str(sys.executable)


class DualListSelector(QWidget):
    def __init__(self, available_title: str, selected_title: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        left_layout = QVBoxLayout()
        left_label = QLabel(available_title)
        left_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QListWidget.MultiSelection)
        self.available_list.setStyleSheet(LIST_STYLE)
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.available_list)

        button_layout = QVBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)
        self.add_button = QPushButton(">>")
        self.add_button.setFixedSize(44, 34)
        self.remove_button = QPushButton("<<")
        self.remove_button.setFixedSize(44, 34)
        button_layout.addStretch()
        button_layout.addWidget(self.add_button, alignment=Qt.AlignCenter)
        button_layout.addWidget(self.remove_button, alignment=Qt.AlignCenter)
        button_layout.addStretch()

        right_layout = QVBoxLayout()
        right_label = QLabel(selected_title)
        right_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QListWidget.MultiSelection)
        self.selected_list.setStyleSheet(LIST_STYLE)
        right_layout.addWidget(right_label)
        right_layout.addWidget(self.selected_list)

        layout.addLayout(left_layout)
        layout.addLayout(button_layout)
        layout.addLayout(right_layout)

        self.add_button.clicked.connect(self.move_to_selected)
        self.remove_button.clicked.connect(self.move_to_available)

    def set_available_items(self, items: list[str]):
        selected = set(self.values())
        self.available_list.clear()
        self.selected_list.clear()
        for item in items:
            if item in selected:
                self.selected_list.addItem(QListWidgetItem(item))
            else:
                self.available_list.addItem(QListWidgetItem(item))

    def values(self) -> list[str]:
        return list_values(self.selected_list)

    def move_to_selected(self):
        selected_items = self.available_list.selectedItems()
        existing = set(self.values())
        for item in selected_items:
            if item.text() not in existing:
                self.selected_list.addItem(QListWidgetItem(item.text()))
            self.available_list.takeItem(self.available_list.row(item))

    def move_to_available(self):
        selected_items = self.selected_list.selectedItems()
        existing = set(list_values(self.available_list))
        for item in selected_items:
            if item.text() not in existing:
                self.available_list.addItem(QListWidgetItem(item.text()))
            self.selected_list.takeItem(self.selected_list.row(item))


class WorkerThread(QThread):
    output_received = Signal(str)
    error_received = Signal(str)
    process_finished = Signal(int)
    request_stop = Signal()

    def __init__(self, command: list[str], working_dir: str | None = None):
        super().__init__()
        self.command = command
        self.working_dir = working_dir
        self.process = None
        self._stop_requested = False
        self.ansi_converter = Ansi2HTMLConverter(dark_bg=True)
        self.is_windows = platform.system() == "Windows"
        self.request_stop.connect(self._handle_stop)

    def run(self):
        try:
            if self.is_windows:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                self.process = subprocess.Popen(
                    self.command,
                    cwd=self.working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                    startupinfo=startupinfo,
                    shell=False,
                )
            else:
                self.process = subprocess.Popen(
                    self.command,
                    cwd=self.working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    preexec_fn=os.setsid,
                    shell=False,
                )

            def read_stdout():
                try:
                    for line in self.process.stdout:
                        if self._stop_requested:
                            break
                        formatted_line = self.ansi_converter.convert(line.rstrip(), full=False)
                        self.output_received.emit(formatted_line)
                except Exception as exc:
                    self.error_received.emit(f"Error reading stdout: {exc}")

            def read_stderr():
                try:
                    for line in self.process.stderr:
                        if self._stop_requested:
                            break
                        self.error_received.emit(line.rstrip())
                except Exception as exc:
                    self.error_received.emit(f"Error reading stderr: {exc}")

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            exit_code = self.process.wait() if self.process else -1
            stdout_thread.join()
            stderr_thread.join()

            self.process = None
            self.process_finished.emit(-1 if self._stop_requested else exit_code)

        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            self.error_received.emit(f"Error in run(): {exc}\n{tb}")

    def stop(self):
        self.request_stop.emit()

    def _handle_stop(self):
        self._stop_requested = True
        if not self.process:
            return
        try:
            parent = psutil.Process(self.process.pid)
            processes = parent.children(recursive=True)
            processes.append(parent)
            for proc in processes:
                try:
                    proc.terminate()
                except Exception:
                    pass
            _, alive = psutil.wait_procs(processes, timeout=2)
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception as exc:
            self.error_received.emit(f"Error stopping process: {exc}")


def stop_process(widget):
    confirmation = QMessageBox.question(
        widget,
        "Stop ALMOS",
        "Are you sure you want to stop the current run?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if confirmation == QMessageBox.No:
        return

    widget.manual_stop = True
    if hasattr(widget, "worker") and widget.worker is not None and widget.worker.isRunning():
        widget.console_output.append(
            "<br><b><span style='color:orangered;'>Stopping ALMOS...</span></b>"
        )
        widget.progress.setRange(0, 100)
        widget.stop_button.setDisabled(True)
        QTimer.singleShot(0, widget.worker.stop)


class BaseWorkflowTab(QWidget):
    success_title = "Success"
    success_message = "Process completed successfully."
    failure_message = "Process did not complete successfully."

    def __init__(self, progress_bar: QProgressBar, console_output: QTextEdit):
        super().__init__()
        self.progress = progress_bar
        self.console_output = console_output
        self.worker: WorkerThread | None = None
        self.manual_stop = False
        self.file_path = ""
        self.all_columns: list[str] = []

    def start_command(self, command: list[str], working_dir: str | None):
        self.console_output.clear()
        self.run_button.setDisabled(True)
        self.stop_button.setDisabled(False)
        self.progress.setRange(0, 0)

        self.worker = WorkerThread(command, working_dir=working_dir)
        self.worker.output_received.connect(
            lambda msg: self.console_output.append(f"<span style='color:white;'>{msg}</span>")
        )
        self.worker.error_received.connect(
            lambda msg: self.console_output.append(f"<span style='color:#ff8b8b;'>{msg}</span>")
        )
        self.worker.process_finished.connect(self.on_process_finished)
        self.worker.start()

    def working_directory(self) -> str | None:
        if not self.file_path:
            return None
        return str(Path(self.file_path).resolve().parent)

    def on_process_finished(self, exit_code: int):
        self.run_button.setDisabled(False)
        self.stop_button.setDisabled(True)
        self.progress.setRange(0, 100)

        if self.worker:
            if self.worker.process and self.worker.process.poll() is None:
                self.worker.stop()
            self.worker = None

        if self.manual_stop:
            self.console_output.clear()
            QMessageBox.information(self, "Stopped", "ALMOS has been successfully stopped.")
            self.manual_stop = False
            return

        if exit_code == 0:
            self.console_output.append("<span style='color:#92d36e;'>Process finished successfully.</span>")
            QMessageBox.information(self, self.success_title, self.success_message)
        else:
            self.console_output.append("<span style='color:#ffb366;'>Process did not complete correctly.</span>")
            QMessageBox.warning(self, "Warning", self.failure_message)

        self.manual_stop = False


class ClusteringTab(BaseWorkflowTab):
    success_title = "Clustering Completed"
    success_message = "Clustering completed successfully."
    failure_message = "Clustering did not complete successfully."

    def __init__(self, progress_bar: QProgressBar, console_output: QTextEdit):
        super().__init__(progress_bar, console_output)

        outer_layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        scroll_content.setAutoFillBackground(True)
        self.content_layout = QVBoxLayout(scroll_content)
        self.content_layout.setSpacing(14)
        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area)

        self._build_file_section()
        self._build_cluster_options_section()
        self._build_ignore_section()
        self._build_action_row("Run Clustering", self.run_clustering)

    def _build_file_section(self):
        group = QGroupBox("Input Dataset")
        layout = QVBoxLayout(group)

        self.file_summary = QLabel("Choose a CSV file to launch a clustering workflow.")
        self.file_summary.setWordWrap(True)
        self.file_summary.setStyleSheet("color: #6f5a45;")
        layout.addWidget(self.file_summary)

        row = QHBoxLayout()
        self.file_button = QPushButton("Select CSV File")
        self.file_button.clicked.connect(self.select_file)
        self.file_chip = QLabel("No file selected")
        self.file_chip.setStyleSheet(
            "background:#efe5d5; border:1px solid #d9c8af; border-radius:8px; padding:8px 10px;"
        )
        self.file_chip.setWordWrap(True)
        row.addWidget(self.file_button)
        row.addWidget(self.file_chip, stretch=1)
        layout.addLayout(row)

        self.content_layout.addWidget(group)

    def _build_cluster_options_section(self):
        group = QGroupBox("Workflow Options")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignLeft)
        layout.setFormAlignment(Qt.AlignTop)

        self.name_dropdown = NoScrollComboBox()
        self.name_dropdown.addItem("Select a name column")
        layout.addRow("Identifier column", self.name_dropdown)

        self.y_dropdown = NoScrollComboBox()
        self.y_dropdown.addItem("Optional target column")
        layout.addRow("Target column", self.y_dropdown)

        self.n_points_entry = QLineEdit()
        self.n_points_entry.setPlaceholderText("Optional. Leave blank to use ALMOS autobudget.")
        layout.addRow("Points to select", self.n_points_entry)

        self.evaluate_checkbox = QCheckBox("Evaluate an existing batch=0 selection instead of selecting new points")
        self.evaluate_checkbox.toggled.connect(self.update_option_states)
        layout.addRow("Evaluation mode", self.evaluate_checkbox)

        self.aqme_checkbox = QCheckBox("Enable AQME workflow")
        self.aqme_checkbox.toggled.connect(self.update_option_states)
        layout.addRow("AQME", self.aqme_checkbox)

        self.descp_combo = NoScrollComboBox()
        self.descp_combo.addItems(["interpret", "full", "denovo"])
        self.descp_combo.setCurrentText("interpret")
        layout.addRow("Descriptor level", self.descp_combo)

        self.cluster_hint = QLabel(
            "Use the default autobudget for most runs. `--evaluate` is useful when the CSV already contains `batch = 0` selections and you only want ALMOS to analyse them."
        )
        self.cluster_hint.setWordWrap(True)
        self.cluster_hint.setStyleSheet("color: #6f5a45;")
        layout.addRow("", self.cluster_hint)

        self.content_layout.addWidget(group)
        self.update_option_states()

    def _build_ignore_section(self):
        group = QGroupBox("Ignored Columns")
        layout = QVBoxLayout(group)
        self.ignore_selector = DualListSelector("Available columns", "Ignored columns")
        layout.addWidget(self.ignore_selector)
        self.content_layout.addWidget(group)

    def _build_action_row(self, run_label: str, run_handler):
        row = QHBoxLayout()
        self.run_button = QPushButton(run_label)
        self.run_button.setStyleSheet(RUN_BUTTON_STYLE)
        self.run_button.clicked.connect(run_handler)
        self.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.run_button, stretch=1)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet(STOP_BUTTON_STYLE)
        self.stop_button.clicked.connect(lambda: stop_process(self))
        self.stop_button.setDisabled(True)
        self.stop_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.stop_button, stretch=1)

        self.content_layout.addLayout(row)
        self.content_layout.addStretch()

    def update_option_states(self):
        evaluate_mode = self.evaluate_checkbox.isChecked()
        self.n_points_entry.setDisabled(evaluate_mode)
        self.aqme_checkbox.setDisabled(evaluate_mode)
        self.descp_combo.setDisabled(evaluate_mode or not self.aqme_checkbox.isChecked())

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if not file_path:
            return

        self.file_path = file_path
        self.file_chip.setText(Path(file_path).name)
        self.file_chip.setToolTip(file_path)

        df = pd.read_csv(file_path)
        self.all_columns = list(df.columns)
        self.name_dropdown.clear()
        self.y_dropdown.clear()
        self.name_dropdown.addItem("Select a name column")
        self.y_dropdown.addItem("Optional target column")
        self.name_dropdown.addItems(self.all_columns)
        self.y_dropdown.addItems(self.all_columns)
        self.ignore_selector.set_available_items(self.all_columns)

    def build_command(self) -> list[str]:
        if not self.file_path:
            raise ValueError("Please select a CSV file.")

        name_column = self.name_dropdown.currentText()
        if name_column == "Select a name column" and not self.aqme_checkbox.isChecked():
            raise ValueError("Please select an identifier column.")

        command = [
            get_almos_python_executable(),
            "-u",
            "-m",
            "almos",
            "--cluster",
            "--input",
            self.file_path,
        ]

        if self.evaluate_checkbox.isChecked():
            command.append("--evaluate")
        else:
            n_points = self.n_points_entry.text().strip()
            if n_points:
                command.extend(["--n_points", n_points])

        if self.aqme_checkbox.isChecked() and not self.evaluate_checkbox.isChecked():
            command.extend(["--aqme", "--descp_level", self.descp_combo.currentText()])
        elif name_column != "Select a name column":
            command.extend(["--name", name_column])

        y_column = self.y_dropdown.currentText()
        if y_column != "Optional target column":
            command.extend(["--y", y_column])

        ignored_columns = self.ignore_selector.values()
        if ignored_columns:
            command.extend(["--ignore", f"[{','.join(ignored_columns)}]"])

        return command

    def run_clustering(self):
        try:
            command = self.build_command()
        except ValueError as exc:
            QMessageBox.warning(self, "Warning", str(exc))
            return

        self.start_command(command, self.working_directory())


class ActiveLearningTab(BaseWorkflowTab):
    success_title = "Active Learning Completed"
    success_message = "Active Learning completed successfully."
    failure_message = "Active Learning did not complete successfully."

    def __init__(self, progress_bar: QProgressBar, console_output: QTextEdit):
        super().__init__(progress_bar, console_output)

        outer_layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        scroll_content.setAutoFillBackground(True)
        self.content_layout = QVBoxLayout(scroll_content)
        self.content_layout.setSpacing(14)
        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area)

        self._build_file_section()
        self._build_learning_options_section()
        self._build_ignore_section()
        self._build_action_row("Run Active Learning", self.run_active_learning)

    def _build_file_section(self):
        group = QGroupBox("Input Dataset")
        layout = QVBoxLayout(group)

        self.file_summary = QLabel("Choose the current AL dataset CSV (for example `A_b0.csv`).")
        self.file_summary.setWordWrap(True)
        self.file_summary.setStyleSheet("color: #6f5a45;")
        layout.addWidget(self.file_summary)

        row = QHBoxLayout()
        self.file_button = QPushButton("Select CSV File")
        self.file_button.clicked.connect(self.select_file)
        self.file_chip = QLabel("No file selected")
        self.file_chip.setStyleSheet(
            "background:#efe5d5; border:1px solid #d9c8af; border-radius:8px; padding:8px 10px;"
        )
        self.file_chip.setWordWrap(True)
        row.addWidget(self.file_button)
        row.addWidget(self.file_chip, stretch=1)
        layout.addLayout(row)

        self.content_layout.addWidget(group)

    def _build_learning_options_section(self):
        group = QGroupBox("Selection Strategy")
        layout = QFormLayout(group)

        self.n_exps_entry = QLineEdit()
        self.n_exps_entry.setPlaceholderText("Default: 1")
        layout.addRow("Experiments to propose", self.n_exps_entry)

        self.name_dropdown = NoScrollComboBox()
        self.name_dropdown.addItem("Select a name column")
        layout.addRow("Identifier column", self.name_dropdown)

        self.y_dropdown = NoScrollComboBox()
        self.y_dropdown.addItem("Select a target column")
        layout.addRow("Target column", self.y_dropdown)

        self.mode_combo = NoScrollComboBox()
        self.mode_combo.addItems(
            [
                "Auto",
                "Model mode (highest uncertainty)",
                "Hit mode (objective-driven)",
            ]
        )
        self.mode_combo.currentIndexChanged.connect(self.update_strategy_ui)
        layout.addRow("Selection mode", self.mode_combo)

        self.objective_combo = NoScrollComboBox()
        self.objective_combo.addItems(["Maximize target", "Minimize target"])
        layout.addRow("Objective", self.objective_combo)

        self.alpha_entry = QLineEdit()
        self.alpha_entry.setPlaceholderText("Optional. Value between 0 and 1.")
        layout.addRow("Alpha override", self.alpha_entry)

        self.strategy_hint = QLabel()
        self.strategy_hint.setWordWrap(True)
        self.strategy_hint.setStyleSheet("color: #6f5a45;")
        layout.addRow("", self.strategy_hint)

        self.content_layout.addWidget(group)
        self.update_strategy_ui()

    def _build_ignore_section(self):
        group = QGroupBox("Ignored Columns")
        layout = QVBoxLayout(group)
        self.ignore_selector = DualListSelector("Available columns", "Ignored columns")
        layout.addWidget(self.ignore_selector)
        self.content_layout.addWidget(group)

    def _build_action_row(self, run_label: str, run_handler):
        row = QHBoxLayout()
        self.run_button = QPushButton(run_label)
        self.run_button.setStyleSheet(RUN_BUTTON_STYLE)
        self.run_button.clicked.connect(run_handler)
        self.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.run_button, stretch=1)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet(STOP_BUTTON_STYLE)
        self.stop_button.clicked.connect(lambda: stop_process(self))
        self.stop_button.setDisabled(True)
        self.stop_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.stop_button, stretch=1)

        self.content_layout.addLayout(row)
        self.content_layout.addStretch()

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if not file_path:
            return

        self.file_path = file_path
        self.file_chip.setText(Path(file_path).name)
        self.file_chip.setToolTip(file_path)

        df = pd.read_csv(file_path)
        self.all_columns = list(df.columns)
        self.name_dropdown.clear()
        self.y_dropdown.clear()
        self.name_dropdown.addItem("Select a name column")
        self.y_dropdown.addItem("Select a target column")
        self.name_dropdown.addItems(self.all_columns)
        self.y_dropdown.addItems(self.all_columns)
        self.ignore_selector.set_available_items(self.all_columns)

    def update_strategy_ui(self):
        mode = self.mode_combo.currentText()
        if mode == "Model mode (highest uncertainty)":
            self.objective_combo.setDisabled(True)
            self.alpha_entry.setDisabled(True)
            self.strategy_hint.setText(
                "Model mode ranks candidates only by predictive uncertainty (`--mode model`). Objective and alpha are not used."
            )
        elif mode == "Hit mode (objective-driven)":
            self.objective_combo.setDisabled(False)
            self.alpha_entry.setDisabled(False)
            self.strategy_hint.setText(
                "Hit mode uses the selected objective plus an optional alpha override between 0 and 1."
            )
        else:
            self.objective_combo.setDisabled(False)
            self.alpha_entry.setDisabled(False)
            self.strategy_hint.setText(
                "Auto mode chooses between model mode and hit mode based on the ROBERT score. Objective is required; alpha is optional."
            )

    def selected_objective_value(self) -> str:
        return "max" if self.objective_combo.currentText() == "Maximize target" else "min"

    def build_command(self) -> list[str]:
        if not self.file_path:
            raise ValueError("Please select a CSV file.")

        name_column = self.name_dropdown.currentText()
        y_column = self.y_dropdown.currentText()
        if name_column == "Select a name column" or y_column == "Select a target column":
            raise ValueError("Please select both identifier and target columns.")

        command = [
            get_almos_python_executable(),
            "-u",
            "-m",
            "almos",
            "--al",
            "--csv_name",
            self.file_path,
            "--name",
            name_column,
            "--y",
            y_column,
        ]

        n_exps = self.n_exps_entry.text().strip()
        if n_exps:
            command.extend(["--n_exps", n_exps])

        mode = self.mode_combo.currentText()
        if mode == "Model mode (highest uncertainty)":
            command.extend(["--mode", "model"])
        elif mode == "Hit mode (objective-driven)":
            command.extend(["--mode", "hit", "--objective", self.selected_objective_value()])
        else:
            command.extend(["--objective", self.selected_objective_value()])

        alpha = self.alpha_entry.text().strip()
        if alpha and mode != "Model mode (highest uncertainty)":
            command.extend(["--alpha", alpha])

        ignored_columns = self.ignore_selector.values()
        if ignored_columns:
            command.extend(["--ignore", f"[{','.join(ignored_columns)}]"])

        return command

    def run_active_learning(self):
        try:
            alpha = self.alpha_entry.text().strip()
            if alpha and self.mode_combo.currentText() != "Model mode (highest uncertainty)":
                alpha_value = float(alpha)
                if not 0 <= alpha_value <= 1:
                    raise ValueError("Alpha must be a number between 0 and 1.")
            command = self.build_command()
        except ValueError as exc:
            QMessageBox.warning(self, "Warning", str(exc))
            return

        self.start_command(command, self.working_directory())


class ALMOSApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EasyALMOS")
        self.resize(980, 920)
        self.setStyleSheet(APP_STYLESHEET)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        with as_file(files("almos") / "icons" / "almos_logo.png") as logo_path:
            if logo_path.exists():
                pixmap = QPixmap(str(logo_path)).scaled(430, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                logo_label = QLabel()
                logo_label.setPixmap(pixmap)
                logo_label.setAlignment(Qt.AlignCenter)
                main_layout.addWidget(logo_label)

        with as_file(files("almos") / "icons" / "almos_icon.png") as icon_path:
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

        intro = QLabel(
            "Launch the most common ALMOS workflows from a lightweight interface. "
            "The GUI intentionally exposes only the parameters that matter most for day-to-day clustering and active learning runs."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#efe5d5; border:1px solid #d9c8af; border-radius:12px; padding:12px; color:#4f3e2e;"
        )
        main_layout.addWidget(intro)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(220)
        self.console_output.setMaximumHeight(320)
        self.console_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.console_output.setStyleSheet(
            """
            QTextEdit {
                background-color: #14110f;
                color: #f4efe8;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 14px;
                line-height: 1.35;
                border-radius: 12px;
                border: 1px solid #3a322b;
            }
            """
        )
        main_layout.addWidget(self.console_output)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(12)
        main_layout.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.clustering_tab = ClusteringTab(self.progress, self.console_output)
        self.active_learning_tab = ActiveLearningTab(self.progress, self.console_output)
        self.tabs.addTab(self.clustering_tab, "Clustering")
        self.tabs.addTab(self.active_learning_tab, "Active Learning")
        main_layout.addWidget(self.tabs)

    def closeEvent(self, event):
        running = any(
            hasattr(tab, "worker") and tab.worker and tab.worker.isRunning()
            for tab in [self.clustering_tab, self.active_learning_tab]
        )
        if not running:
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "Exit Confirmation",
            "ALMOS is still running. Do you want to stop the current process and exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for tab in [self.clustering_tab, self.active_learning_tab]:
                if hasattr(tab, "worker") and tab.worker and tab.worker.isRunning():
                    tab.worker.stop()
                    tab.worker.wait()
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    window = ALMOSApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
