from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import threading
import traceback
from html import escape
from importlib.resources import as_file, files
from pathlib import Path

import pandas as pd
import psutil
from ansi2html import Ansi2HTMLConverter
from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
    QPalette,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
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

from almos.campaign import RunResult, import_measurements, read_run_result
from almos.easyalmos.progress import WorkflowProgress
from almos.package_versions import ALMOS_VERSION
from almos.progress import PROGRESS_ENV, read_progress


APP_STYLESHEET = """
QMainWindow {
    background: #eef3f1;
}
QWidget {
    font-size: 13px;
}
QDialog {
    background: #f7faf8;
}
QMenu, QToolTip {
    background: #ffffff;
    color: #20342d;
    border: 1px solid #c7d6ce;
}
QMenu::item:selected {
    background: #d9ece2;
    color: #154a36;
}
QToolTip {
    padding: 4px 6px;
}
QFrame#appHeader, QFrame#resultsPanel, QFrame#workflowProgress {
    background: #ffffff;
    border: 1px solid #d9e4de;
    border-radius: 14px;
}
QLabel#appTitle {
    color: #14392c;
    font-size: 24px;
    font-weight: 700;
}
QTabWidget::pane, QScrollArea {
    border: none;
    background: transparent;
}
QWidget#workflowPage, QWidget#workflowContent {
    background: #eef3f1;
}
QTabBar::tab {
    background: #e4ebe7;
    color: #364f44;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 8px 16px;
    margin: 0 6px 4px 0;
    font-weight: 700;
}
QTabBar::tab:selected {
    background: #d9ece2;
    color: #154a36;
    border-color: #91bba8;
}
QTabBar::tab:!selected:hover {
    background: #dfe8e3;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #d9e4de;
    border-radius: 11px;
    margin-top: 12px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background: #ffffff;
}
QLabel#sectionTitle {
    color: #244d3d;
    font-weight: 700;
}
QLabel#resultTitle {
    color: #14392c;
    font-size: 17px;
    font-weight: 700;
}
QLabel#secondaryText {
    color: #526961;
}
QLabel#datasetName {
    background: #edf5f0;
    border: 1px solid #d3e2d9;
    border-radius: 7px;
    padding: 7px 10px;
}
QLabel#batchFolderHelp {
    color: #3e6153;
    background: #f5f9f7;
    border: 1px solid #d3e2d9;
    border-radius: 8px;
    padding: 9px;
}
QLineEdit, QComboBox, QListWidget, QTextEdit {
    background: #ffffff;
    border: 1px solid #c7d6ce;
    border-radius: 7px;
    padding: 5px 8px;
}
QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTextEdit:focus {
    border-color: #318265;
}
QLineEdit:disabled, QComboBox:disabled {
    background: #f1f4f2;
    color: #64766d;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #20342d;
    border: 1px solid #c7d6ce;
    selection-background-color: #d9ece2;
    selection-color: #154a36;
}
QListWidget::item {
    padding: 3px 5px;
}
QListWidget::item:selected {
    background: #d9ece2;
    color: #154a36;
}
QScrollBar:vertical {
    background: #eef3f1;
    width: 9px;
}
QScrollBar::handle:vertical {
    background: #b9cdc3;
    border-radius: 4px;
    min-height: 26px;
}
QScrollBar::handle:vertical:hover {
    background: #8eafa1;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QPushButton {
    background: #ffffff;
    color: #224a3b;
    border: 1px solid #c7d6ce;
    border-radius: 7px;
    padding: 7px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background: #e8f2ed;
}
QPushButton[variant="primary"] {
    background: #23694c;
    border-color: #23694c;
    color: #ffffff;
    padding: 8px 13px;
}
QPushButton[variant="primary"]:hover {
    background: #18523b;
}
QPushButton[variant="stop"] {
    border-color: #d9b9b4;
    color: #922f2b;
}
QPushButton[variant="stop"]:hover {
    background: #f9eeec;
}
QPushButton:focus {
    border-color: #318265;
}
QPushButton[variant="primary"]:focus {
    border-color: #82c8ad;
}
QPushButton:disabled, QPushButton[variant="primary"]:disabled, QPushButton[variant="stop"]:disabled {
    background: #edf2ef;
    border-color: #dfe7e2;
    color: #64766d;
}
QProgressBar {
    border: none;
    border-radius: 4px;
    background: #dce8e1;
}
QProgressBar::chunk {
    background: #318265;
    border-radius: 4px;
}
QTextEdit#runLog {
    background: #fbfdfc;
    border-color: #c7d6ce;
    color: #20342d;
    padding: 8px;
    font-family: Consolas, monospace;
}
"""


def apply_light_theme(app: QApplication):
    app.setAttribute(Qt.AA_DontUseNativeDialogs)
    style_hints = app.styleHints()
    if hasattr(style_hints, "setColorScheme"):
        style_hints.setColorScheme(Qt.ColorScheme.Light)
    if app.styleSheet() != APP_STYLESHEET:
        app.setStyle("Fusion")
        app.setStyleSheet(APP_STYLESHEET)
    palette = app.style().standardPalette()
    for role, color in {
        QPalette.Window: "#eef3f1",
        QPalette.WindowText: "#20342d",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f2f7f4",
        QPalette.Text: "#20342d",
        QPalette.Button: "#ffffff",
        QPalette.ButtonText: "#224a3b",
        QPalette.Highlight: "#d9ece2",
        QPalette.HighlightedText: "#154a36",
        QPalette.PlaceholderText: "#526961",
        QPalette.ToolTipBase: "#ffffff",
        QPalette.ToolTipText: "#20342d",
        QPalette.Link: "#1a634a",
        QPalette.LinkVisited: "#62517c",
    }.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#64766d"))
    if app.palette() != palette:
        app.setPalette(palette)


class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


def list_values(list_widget: QListWidget) -> list[str]:
    return [list_widget.item(i).text() for i in range(list_widget.count())]


def optional_positive_integer(text: str, label: str) -> int | None:
    if not text.strip():
        return None
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return value


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
        left_label.setObjectName("sectionTitle")
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QListWidget.MultiSelection)
        self.available_list.setMaximumHeight(140)
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.available_list)

        button_layout = QVBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)
        self.add_button = QPushButton("→")
        self.add_button.setToolTip("Ignore selected columns")
        self.add_button.setAccessibleName("Ignore selected columns")
        self.add_button.setFixedSize(44, 34)
        self.remove_button = QPushButton("←")
        self.remove_button.setToolTip("Restore selected columns")
        self.remove_button.setAccessibleName("Restore selected columns")
        self.remove_button.setFixedSize(44, 34)
        button_layout.addStretch()
        button_layout.addWidget(self.add_button, alignment=Qt.AlignCenter)
        button_layout.addWidget(self.remove_button, alignment=Qt.AlignCenter)
        button_layout.addStretch()

        right_layout = QVBoxLayout()
        right_label = QLabel(selected_title)
        right_label.setObjectName("sectionTitle")
        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QListWidget.MultiSelection)
        self.selected_list.setMaximumHeight(140)
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
    step_completed = Signal(str, str)
    process_finished = Signal(int)
    request_stop = Signal()

    def __init__(self, command: list[str], working_dir: str | None = None):
        super().__init__()
        self.command = command
        self.working_dir = working_dir
        self.process = None
        self._stop_requested = False
        self._stop_lock = threading.Lock()
        self.ansi_converter = Ansi2HTMLConverter(dark_bg=False)
        self.is_windows = platform.system() == "Windows"
        self.request_stop.connect(self._handle_stop)

    def run(self):
        exit_code = -1
        try:
            if self._stop_requested:
                return
            environment = {**os.environ, PROGRESS_ENV: "1"}
            if self.is_windows:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                process = subprocess.Popen(
                    self.command,
                    cwd=self.working_dir,
                    env=environment,
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
                process = subprocess.Popen(
                    self.command,
                    cwd=self.working_dir,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    preexec_fn=os.setsid,
                    shell=False,
                )

            with self._stop_lock:
                self.process = process
                stop_requested = self._stop_requested
            if stop_requested:
                self._terminate_process(process)

            def read_stdout():
                try:
                    for line in process.stdout:
                        if self._stop_requested:
                            break
                        event = read_progress(line)
                        if event is not None:
                            self.step_completed.emit(*event)
                            continue
                        formatted_line = self.ansi_converter.convert(line.rstrip(), full=False)
                        self.output_received.emit(formatted_line)
                except Exception as exc:
                    self.error_received.emit(f"Error reading stdout: {exc}")

            def read_stderr():
                try:
                    for line in process.stderr:
                        if self._stop_requested:
                            break
                        self.error_received.emit(line.rstrip())
                except Exception as exc:
                    self.error_received.emit(f"Error reading stderr: {exc}")

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            exit_code = process.wait()
            stdout_thread.join()
            stderr_thread.join()

        except Exception as exc:
            exit_code = -1
            self.error_received.emit(f"Unable to run ALMOS: {exc}\n{traceback.format_exc()}")
            if self.process is not None:
                self._handle_stop()
        finally:
            with self._stop_lock:
                self.process = None
                stop_requested = self._stop_requested
            self.process_finished.emit(-1 if stop_requested else exit_code)

    def stop(self):
        self.request_stop.emit()

    def _handle_stop(self):
        with self._stop_lock:
            if self._stop_requested:
                return
            self._stop_requested = True
            process = self.process
        if process is not None:
            self._terminate_process(process)

    def _terminate_process(self, process):
        try:
            parent = psutil.Process(process.pid)
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
        except psutil.NoSuchProcess:
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

    worker = widget.worker
    if worker is not None and worker.isRunning():
        widget.manual_stop = True
        widget.console_output.append(
            "<br><b><span style='color:#805010;'>Stopping ALMOS...</span></b>"
        )
        widget.progress.setRange(0, 100)
        widget.stop_button.setDisabled(True)
        QTimer.singleShot(0, lambda: worker.stop() if widget.worker is worker else None)


class BaseWorkflowTab(QWidget):
    running_changed = Signal(bool)
    result_ready = Signal(object)
    progress_started = Signal(str, object)
    step_completed = Signal(str, str)
    progress_finished = Signal(int, bool)
    workflow_module = ""
    success_title = "Success"
    success_message = "Process completed successfully."
    failure_message = "Process did not complete successfully."
    target_placeholder = "Select a target column"

    def __init__(self, progress_bar: QProgressBar, console_output: QTextEdit):
        super().__init__()
        self.setObjectName("workflowPage")
        self.progress = progress_bar
        self.console_output = console_output
        self.worker: WorkerThread | None = None
        self.manual_stop = False
        self.file_path = ""
        self.campaign_directory: Path | None = None
        self.all_columns: list[str] = []
        self.run_context = None

    def start_command(self, command: list[str], working_dir: str | None):
        if not self.run_button.isEnabled():
            return

        self.run_context = None
        if working_dir and self.file_path:
            directory = Path(working_dir).resolve()
            self.run_context = (directory, Path(self.file_path).resolve(), self.manifest_versions(directory))
        worker = WorkerThread(command, working_dir=working_dir)
        worker.setParent(self)
        worker.output_received.connect(self.append_output)
        worker.error_received.connect(self.append_error)
        worker.step_completed.connect(self.step_completed)
        worker.process_finished.connect(self.on_process_finished)
        worker.finished.connect(worker.deleteLater)
        self.worker = worker

        self.console_output.clear()
        self.run_button.setDisabled(True)
        self.stop_button.setDisabled(False)
        self.progress.setRange(0, 0)
        self.progress_started.emit(self.workflow_title, self.progress_steps(command))
        self.running_changed.emit(True)

        try:
            worker.start()
        except RuntimeError as exc:
            self.append_error(f"Unable to start the ALMOS worker: {exc}")
            worker.process_finished.emit(-1)
            worker.deleteLater()

    @Slot(str)
    def append_output(self, message: str):
        self.console_output.append(f"<span style='color:#20342d;'>{message}</span>")

    @Slot(str)
    def append_error(self, message: str):
        html_message = escape(message).replace("\n", "<br>")
        self.console_output.append(f"<span style='color:#922f2b;'>{html_message}</span>")

    def select_file(self):
        directory = self.working_directory() or ""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", directory, "CSV Files (*.csv)")
        if file_path:
            self.load_dataset(file_path)

    def load_dataset(self, file_path: str, *, campaign_directory: Path | None = None) -> bool:
        filename = Path(file_path).name
        try:
            dataset = pd.read_csv(file_path)
            if dataset.empty:
                raise ValueError("The CSV must contain at least one data row.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid Dataset", f"Could not load {filename}. {exc}")
            return False

        self.file_path = file_path
        self.campaign_directory = campaign_directory
        self.file_chip.setText(filename)
        self.file_chip.setToolTip(file_path)
        self.all_columns = list(dataset.columns)
        rows, columns = dataset.shape
        self.file_summary.setText(f"Rows {rows:,} · Columns {columns:,}")
        self.file_summary.show()
        self.name_dropdown.clear()
        self.y_dropdown.clear()
        self.name_dropdown.addItem("Select a name column")
        self.y_dropdown.addItem(self.target_placeholder)
        self.name_dropdown.addItems(self.all_columns)
        self.y_dropdown.addItems(self.all_columns)
        self.ignore_selector.set_available_items(self.all_columns)
        return True

    @staticmethod
    def manifest_versions(directory):
        versions = {}
        for path in directory.glob("batch_*/run.json"):
            if not re.fullmatch(r"batch_[0-9]+", path.parent.name):
                continue
            try:
                info = path.stat()
            except OSError:
                continue
            versions[path] = (info.st_mtime_ns, info.st_ino)
        return versions

    def completed_result(self, context):
        if context is None:
            return None
        directory, source, before = context
        matches = []
        for manifest, version in self.manifest_versions(directory).items():
            if before.get(manifest) == version:
                continue
            try:
                result = read_run_result(manifest)
            except (OSError, ValueError):
                continue
            if result.module == self.workflow_module and result.input_path == source:
                matches.append(result)
        return max(matches, key=lambda result: result.batch, default=None)

    def working_directory(self) -> str | None:
        if not self.file_path:
            return None
        if self.campaign_directory is not None:
            return str(self.campaign_directory)
        source = Path(self.file_path).resolve()
        batch_folder = re.fullmatch(r"batch_([0-9]+)", source.parent.name)
        if batch_folder and source.stem.endswith(f"_b{batch_folder[1]}"):
            return str(source.parent.parent)
        return str(source.parent)

    def _build_file_section(self):
        group = QGroupBox("Input Dataset")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 16, 14, 12)

        row = QHBoxLayout()
        self.file_button = QPushButton("Select CSV…")
        self.file_button.clicked.connect(self.select_file)
        self.file_chip = QLabel("No file selected")
        self.file_chip.setObjectName("datasetName")
        self.file_chip.setTextFormat(Qt.PlainText)
        self.file_chip.setWordWrap(True)
        row.addWidget(self.file_button)
        row.addWidget(self.file_chip, stretch=1)
        layout.addLayout(row)

        self.file_summary = QLabel()
        self.file_summary.setObjectName("secondaryText")
        self.file_summary.hide()
        layout.addWidget(self.file_summary)
        self.content_layout.addWidget(group)
        return layout

    def _build_action_row(self, layout, run_label: str, run_handler):
        row = QHBoxLayout()
        self.run_button = QPushButton(run_label)
        self.run_button.setProperty("variant", "primary")
        self.run_button.clicked.connect(run_handler)
        self.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.run_button, stretch=1)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("variant", "stop")
        self.stop_button.clicked.connect(lambda: stop_process(self))
        self.stop_button.setDisabled(True)
        self.stop_button.setMinimumWidth(82)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.content_layout.addStretch()

    @Slot(int)
    def on_process_finished(self, exit_code: int):
        self.worker = None
        context, self.run_context = self.run_context, None
        manual_stop = self.manual_stop
        self.manual_stop = False
        self.run_button.setDisabled(False)
        self.stop_button.setDisabled(True)
        self.progress.setRange(0, 100)
        self.progress_finished.emit(exit_code, manual_stop)
        self.running_changed.emit(False)

        if manual_stop:
            self.console_output.clear()
            QMessageBox.information(self, "Stopped", "ALMOS has been successfully stopped.")
            return

        if exit_code == 0:
            self.console_output.append("<span style='color:#23694c;'>Process finished successfully.</span>")
            result = self.completed_result(context)
            if result is not None:
                self.result_ready.emit(result)
            else:
                QMessageBox.information(self, self.success_title, self.success_message)
        else:
            self.console_output.append("<span style='color:#922f2b;'>Process did not complete correctly.</span>")
            QMessageBox.warning(self, "Warning", self.failure_message)


class ClusteringTab(BaseWorkflowTab):
    workflow_module = "cluster"
    workflow_title = "Clustering"
    success_title = "Clustering Completed"
    success_message = "Clustering completed successfully."
    failure_message = "Clustering did not complete successfully."
    target_placeholder = "Optional target column"

    @staticmethod
    def progress_steps(command: list[str]) -> tuple[tuple[str, str], ...]:
        evaluate = "--evaluate" in command
        steps = [("cluster_input", "Prepare input")]
        if "--aqme" in command and not evaluate:
            steps.append(("cluster_aqme", "Generate AQME descriptors"))
        steps.append(("cluster_cleanup", "Clean descriptors"))
        if not evaluate and "--n_points" not in command:
            steps.append(("cluster_budget", "Choose point count automatically"))
        steps.extend((
            ("cluster_selection", "Evaluate selected points" if evaluate else "Select points"),
            ("cluster_viewer", "Build Chemical Space"),
            ("cluster_publish", "Save batch outputs"),
        ))
        return tuple(steps)

    def __init__(self, progress_bar: QProgressBar, console_output: QTextEdit):
        super().__init__(progress_bar, console_output)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 2, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        scroll_content.setObjectName("workflowContent")
        scroll_content.setAutoFillBackground(True)
        self.content_layout = QVBoxLayout(scroll_content)
        self.content_layout.setContentsMargins(0, 3, 4, 4)
        self.content_layout.setSpacing(9)
        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area)

        self._build_file_section()
        self._build_cluster_options_section()
        self._build_ignore_section()
        self._build_action_row(outer_layout, "Run Clustering", self.run_clustering)

    def _build_cluster_options_section(self):
        group = QGroupBox("Batch Selection")
        layout = QFormLayout(group)
        layout.setContentsMargins(14, 16, 14, 12)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.setLabelAlignment(Qt.AlignLeft)
        layout.setFormAlignment(Qt.AlignTop)

        self.name_dropdown = NoScrollComboBox()
        self.name_dropdown.addItem("Select a name column")
        layout.addRow("Identifier column", self.name_dropdown)

        self.y_dropdown = NoScrollComboBox()
        self.y_dropdown.addItem(self.target_placeholder)
        layout.addRow("Target column", self.y_dropdown)

        self.n_points_entry = QLineEdit()
        self.n_points_entry.setPlaceholderText("Automatic if left blank")
        layout.addRow("Points to select", self.n_points_entry)

        self.evaluate_checkbox = QCheckBox("Evaluate an existing batch 0")
        self.evaluate_checkbox.setToolTip("Analyze the rows already assigned to batch 0 in the CSV.")
        self.evaluate_checkbox.toggled.connect(self.update_option_states)
        layout.addRow("Evaluation mode", self.evaluate_checkbox)

        self.aqme_checkbox = QCheckBox("Generate descriptors with AQME")
        self.aqme_checkbox.toggled.connect(self.update_option_states)
        layout.addRow("AQME", self.aqme_checkbox)

        self.descp_combo = NoScrollComboBox()
        self.descp_combo.addItems(["interpret", "full", "denovo"])
        self.descp_combo.setCurrentText("interpret")
        layout.addRow("Descriptor level", self.descp_combo)

        self.content_layout.addWidget(group)
        self.update_option_states()

    def _build_ignore_section(self):
        group = QGroupBox("Ignored Columns")
        layout = QVBoxLayout(group)
        self.ignore_selector = DualListSelector("Available columns", "Ignored columns")
        layout.addWidget(self.ignore_selector)
        self.content_layout.addWidget(group)

    def update_option_states(self):
        evaluate_mode = self.evaluate_checkbox.isChecked()
        self.n_points_entry.setDisabled(evaluate_mode)
        self.aqme_checkbox.setDisabled(evaluate_mode)
        self.descp_combo.setDisabled(evaluate_mode or not self.aqme_checkbox.isChecked())

    def build_command(self) -> list[str]:
        if not self.file_path:
            raise ValueError("Please select a CSV file.")

        name_column = self.name_dropdown.currentText()
        evaluate_mode = self.evaluate_checkbox.isChecked()
        aqme_enabled = self.aqme_checkbox.isChecked() and not evaluate_mode
        if name_column == "Select a name column":
            aqme_default = aqme_enabled and any(column.lower() == "code_name" for column in self.all_columns)
            if not aqme_default:
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

        if evaluate_mode:
            command.append("--evaluate")
        else:
            n_points = optional_positive_integer(self.n_points_entry.text(), "Points to select")
            if n_points is not None:
                command.extend(["--n_points", str(n_points)])

        if aqme_enabled:
            command.extend(["--aqme", "--descp_level", self.descp_combo.currentText()])
        if name_column != "Select a name column":
            command.extend(["--name", name_column])

        y_column = self.y_dropdown.currentText()
        if y_column != self.target_placeholder:
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
    workflow_module = "al"
    workflow_title = "Active Learning"
    success_title = "Active Learning Completed"
    success_message = "Active Learning completed successfully."
    failure_message = "Active Learning did not complete successfully."

    @staticmethod
    def progress_steps(_command: list[str]) -> tuple[tuple[str, str], ...]:
        return (
            ("al_input", "Prepare training data"),
            ("al_model", "Run ROBERT"),
            ("al_predictions", "Verify predictions"),
            ("al_selection", "Rank and select candidates"),
            ("al_publish", "Save batch outputs"),
        )

    def __init__(self, progress_bar: QProgressBar, console_output: QTextEdit):
        super().__init__(progress_bar, console_output)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 2, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        scroll_content.setObjectName("workflowContent")
        scroll_content.setAutoFillBackground(True)
        self.content_layout = QVBoxLayout(scroll_content)
        self.content_layout.setContentsMargins(0, 3, 4, 4)
        self.content_layout.setSpacing(9)
        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area)

        self._build_file_section()
        self._build_learning_options_section()
        self._build_ignore_section()
        self._build_action_row(outer_layout, "Run Active Learning", self.run_active_learning)

    def _build_file_section(self):
        layout = super()._build_file_section()
        self.import_measurements_button = QPushButton("Import Measurements…")
        self.import_measurements_button.setEnabled(False)
        self.import_measurements_button.clicked.connect(self.import_measurement_file)
        layout.addWidget(self.import_measurements_button, alignment=Qt.AlignLeft)

    def _build_learning_options_section(self):
        group = QGroupBox("Selection Strategy")
        layout = QFormLayout(group)
        layout.setContentsMargins(14, 16, 14, 12)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.n_exps_entry = QLineEdit()
        self.n_exps_entry.setPlaceholderText("Default: 1")
        layout.addRow("Experiments to propose", self.n_exps_entry)

        self.name_dropdown = NoScrollComboBox()
        self.name_dropdown.addItem("Select a name column")
        layout.addRow("Identifier column", self.name_dropdown)

        self.y_dropdown = NoScrollComboBox()
        self.y_dropdown.addItem(self.target_placeholder)
        layout.addRow("Target column", self.y_dropdown)
        self.name_dropdown.currentIndexChanged.connect(self.update_import_button)
        self.y_dropdown.currentIndexChanged.connect(self.update_import_button)

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
        self.strategy_hint.setObjectName("secondaryText")
        layout.addRow("", self.strategy_hint)

        self.content_layout.addWidget(group)
        self.update_strategy_ui()

    def _build_ignore_section(self):
        group = QGroupBox("Ignored Columns")
        layout = QVBoxLayout(group)
        self.ignore_selector = DualListSelector("Available columns", "Ignored columns")
        layout.addWidget(self.ignore_selector)
        self.content_layout.addWidget(group)

    def update_import_button(self):
        self.import_measurements_button.setEnabled(
            bool(self.file_path)
            and self.name_dropdown.currentIndex() > 0
            and self.name_dropdown.currentText() != self.y_dropdown.currentText()
        )

    def import_measurement_file(self):
        source = Path(self.file_path)
        identifier = self.name_dropdown.currentText()
        target = self.y_dropdown.currentText()
        measurements, _ = QFileDialog.getOpenFileName(
            self, "Select Measurements CSV", str(source.parent), "CSV Files (*.csv)",
        )
        if not measurements:
            return
        if self.y_dropdown.currentIndex() == 0:
            try:
                columns = pd.read_csv(measurements, nrows=0).columns
                if identifier not in columns:
                    raise ValueError(f"Measurements must include '{identifier}'.")
                targets = [column for column in columns if column != identifier and column.lower() != "batch"]
                if not targets:
                    raise ValueError("The measurements CSV must include a target column.")
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Import Failed", str(exc))
                return
            target = targets[0]
            if len(targets) > 1:
                target, accepted = QInputDialog.getItem(self, "Measurement Target", "Target column", targets, editable=False)
                if not accepted:
                    return
        base = re.sub(r"(_b[0-9]+)$", r"_measured\1", source.stem)
        if base == source.stem:
            base += "_measured"
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save Updated Dataset", str(source.with_name(f"{base}.csv")), "CSV Files (*.csv)",
        )
        if not destination:
            return
        if not Path(destination).suffix:
            destination += ".csv"
        try:
            count = import_measurements(source, measurements, destination, identifier, target)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))
            return
        campaign = None
        if Path(destination).resolve().parent == source.resolve().parent:
            campaign = Path(self.working_directory())
        if self.load_dataset(destination, campaign_directory=campaign):
            self.name_dropdown.setCurrentText(identifier)
            self.y_dropdown.setCurrentText(target)
        QMessageBox.information(self, "Measurements Imported", f"Saved {count} new measurements to {Path(destination).name}.")

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
        if name_column == "Select a name column" or y_column == self.target_placeholder:
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

        n_exps = optional_positive_integer(self.n_exps_entry.text(), "Experiments to propose")
        if n_exps is not None:
            command.extend(["--n_exps", str(n_exps)])

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
        apply_light_theme(QApplication.instance())
        self.setWindowTitle("EasyALMOS")
        self.setAcceptDrops(True)
        self.result: RunResult | None = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        main_layout.addWidget(self.build_header())

        self.console_output = QTextEdit()
        self.console_output.setObjectName("runLog")
        self.console_output.setReadOnly(True)
        self.console_output.setAcceptDrops(False)
        self.console_output.setMinimumHeight(110)
        self.progress_panel = WorkflowProgress()
        self.progress = self.progress_panel.bar

        self.tabs = QTabWidget()
        self.clustering_tab = ClusteringTab(self.progress, self.console_output)
        self.active_learning_tab = ActiveLearningTab(self.progress, self.console_output)
        self.clustering_tab.running_changed.connect(self.active_learning_tab.run_button.setDisabled)
        self.active_learning_tab.running_changed.connect(self.clustering_tab.run_button.setDisabled)
        for tab in (self.clustering_tab, self.active_learning_tab):
            tab.progress_started.connect(self.progress_panel.begin)
            tab.step_completed.connect(self.progress_panel.complete_step)
            tab.progress_finished.connect(self.progress_panel.finish)
            tab.result_ready.connect(self.show_result)
        self.tabs.addTab(self.clustering_tab, "Clustering")
        self.tabs.addTab(self.active_learning_tab, "Active Learning")
        self.workspace = QWidget()
        self.workspace_layout = QBoxLayout(QBoxLayout.LeftToRight, self.workspace)
        self.workspace_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace_layout.setSpacing(14)
        self.workspace_layout.addWidget(self.tabs, stretch=3)
        self.results_panel = self.build_results_panel()
        self.workspace_layout.addWidget(self.results_panel, 1, Qt.AlignTop)
        main_layout.addWidget(self.workspace, stretch=1)
        main_layout.addWidget(self.progress_panel)

        footer = QHBoxLayout()
        self.log_button = QPushButton("Show Log")
        self.log_button.setCheckable(True)
        self.log_button.toggled.connect(self.toggle_log)
        footer.addWidget(self.log_button)
        self.expand_log_button = QPushButton("Expand Log")
        self.expand_log_button.setCheckable(True)
        self.expand_log_button.toggled.connect(self.toggle_log_size)
        self.expand_log_button.hide()
        footer.addWidget(self.expand_log_button)
        footer.addStretch()
        main_layout.addLayout(footer)
        main_layout.addWidget(self.console_output)
        self.console_output.hide()
        self.setMinimumSize(620, 600)
        self.resize(1120, 790)

    def build_header(self):
        header = QFrame()
        header.setObjectName("appHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        with as_file(files("almos") / "icons" / "almos_icon.png") as icon_path:
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                logo = QLabel()
                logo.setPixmap(QPixmap(str(icon_path)).scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                logo.setAlignment(Qt.AlignCenter)
                layout.addWidget(logo)

        branding = QVBoxLayout()
        branding.setSpacing(0)
        title = QLabel("EasyALMOS")
        title.setObjectName("appTitle")
        version = QLabel(f"Version {ALMOS_VERSION}")
        version.setObjectName("secondaryText")
        branding.addWidget(title)
        branding.addWidget(version)
        layout.addLayout(branding)
        layout.addStretch()

        return header

    def resizeEvent(self, event: QResizeEvent):
        compact = event.size().width() < 880
        direction = QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight
        if direction != self.workspace_layout.direction():
            self.workspace_layout.setDirection(direction)
            self.workspace_layout.setStretch(1, 0 if compact else 1)
            self.results_toggle.setVisible(compact)
            self.results_toggle.setChecked(not compact or self.result is None)
        super().resizeEvent(event)

    def toggle_log(self, visible: bool):
        self.console_output.setVisible(visible)
        self.expand_log_button.setVisible(visible)
        if not visible:
            self.expand_log_button.setChecked(False)
        self.log_button.setText("Hide Log" if visible else "Show Log")

    def toggle_log_size(self, expanded: bool):
        self.workspace.setVisible(not expanded)
        self.centralWidget().layout().setStretchFactor(self.console_output, int(expanded))
        self.expand_log_button.setText("Restore Log" if expanded else "Expand Log")

    def build_results_panel(self):
        group = QFrame()
        group.setObjectName("resultsPanel")
        group.setMinimumWidth(290)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        heading = QLabel("Run Results")
        heading.setObjectName("sectionTitle")
        header = QHBoxLayout()
        header.addWidget(heading, stretch=1)
        self.open_batch_folder_button = QPushButton("Open Batch Folder…")
        self.open_batch_folder_button.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        self.open_batch_folder_button.clicked.connect(self.open_batch_folder)
        header.addWidget(self.open_batch_folder_button)
        self.results_toggle = QPushButton("Hide Details")
        self.results_toggle.setCheckable(True)
        self.results_toggle.setChecked(True)
        self.results_toggle.hide()
        header.addWidget(self.results_toggle)
        layout.addLayout(header)
        self.results_summary = QLabel("No batch open")
        self.results_summary.setObjectName("resultTitle")
        self.results_summary.setWordWrap(True)
        layout.addWidget(self.results_summary)

        self.results_details = QWidget()
        details_layout = QVBoxLayout(self.results_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(10)
        layout.addWidget(self.results_details)
        self.results_toggle.toggled.connect(self.toggle_results_details)

        self.result_file = QLabel()
        self.result_file.setObjectName("datasetName")
        self.result_file.setTextFormat(Qt.PlainText)
        self.result_file.setWordWrap(True)
        self.result_file.hide()
        self.result_count = QLabel()
        self.result_count.setObjectName("secondaryText")
        self.result_count.hide()
        details = QHBoxLayout()
        details.addWidget(self.result_file, stretch=1)
        details.addWidget(self.result_count)
        details_layout.addLayout(details)

        actions = QGridLayout()
        actions.setColumnStretch(0, 1)
        actions.setColumnStretch(1, 1)
        self.open_folder_button = QPushButton("Show Folder")
        self.open_dataset_button = QPushButton("Open CSV")
        self.open_viewer_button = QPushButton("Open Chemical Space")
        self.open_viewer_button.setToolTip("Open the interactive chemical space map in your browser")
        self.open_ranking_button = QPushButton("Open Ranking")
        self.continue_al_button = QPushButton("Continue in AL")
        for button, attribute, row, column, span in (
            (self.open_dataset_button, "dataset", 0, 0, 1),
            (self.open_folder_button, "directory", 0, 1, 1),
            (self.open_viewer_button, "viewer", 1, 0, 2),
            (self.open_ranking_button, "ranking", 2, 0, 2),
        ):
            button.setEnabled(False)
            button.hide()
            button.clicked.connect(lambda _checked, key=attribute: self.open_result_path(key))
            actions.addWidget(button, row, column, 1, span)
        details_layout.addLayout(actions)
        self.continue_al_button.setProperty("variant", "primary")
        self.continue_al_button.setEnabled(False)
        self.continue_al_button.hide()
        self.continue_al_button.clicked.connect(self.continue_active_learning)
        details_layout.addWidget(self.continue_al_button)

        self.batch_folder_help = QLabel(
            "Choose or drop batch_0 for Clustering, or a completed batch such as batch_1 for Active Learning. "
            "The folder contains the files EasyALMOS needs to reopen the results and continue the campaign."
        )
        self.batch_folder_help.setObjectName("batchFolderHelp")
        self.batch_folder_help.setWordWrap(True)
        details_layout.addWidget(self.batch_folder_help)
        return group

    def toggle_results_details(self, visible: bool):
        self.results_details.setVisible(visible)
        self.results_toggle.setText("Hide Details" if visible else "Show Details")

    @Slot(object)
    def show_result(self, result: RunResult):
        self.result = result
        label = "Clustering" if result.module == "cluster" else "Active Learning"
        self.results_summary.setText(f"{label} · Batch {result.batch}")
        self.results_summary.setToolTip(str(result.directory))
        count = result.selected_count
        self.result_count.setText(f"{count:,} selected" if count is not None else "")
        self.result_count.setVisible(count is not None)
        self.result_file.setText(result.dataset.name if result.dataset else "")
        self.result_file.setToolTip(str(result.dataset) if result.dataset else "")
        self.result_file.setVisible(result.dataset is not None)
        for button, path in (
            (self.open_folder_button, result.directory),
            (self.open_dataset_button, result.dataset),
            (self.open_viewer_button, result.viewer),
            (self.open_ranking_button, result.ranking),
            (self.continue_al_button, result.dataset),
        ):
            button.setEnabled(path is not None)
            button.setVisible(path is not None)
        self.results_toggle.setChecked(True)

    def run_picker_directory(self) -> str:
        if self.result is not None:
            return str(self.result.directory.parent)
        return self.tabs.currentWidget().working_directory() or ""

    def open_batch_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Open Completed Batch Folder", self.run_picker_directory())
        if path:
            self.load_batch_folder(Path(path))

    def load_batch_folder(self, folder: Path):
        try:
            if not folder.is_dir():
                raise ValueError("Select the completed batch folder itself, such as batch_0 for Clustering.")
            self.show_result(read_run_result(folder))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could Not Open Batch", str(exc))

    @staticmethod
    def dropped_batch_folder(event: QDropEvent) -> Path | None:
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        return path if path.is_dir() else None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self.dropped_batch_folder(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        path = self.dropped_batch_folder(event)
        if path is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self.load_batch_folder(path)

    def open_result_path(self, attribute: str):
        path = getattr(self.result, attribute, None)
        if path is not None and path.exists() and QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return
        QMessageBox.warning(self, "Could Not Open Result", "The output could not be opened.")

    def continue_active_learning(self):
        result = self.result
        tab = self.active_learning_tab
        if result is None or result.dataset is None:
            return
        campaign = result.directory
        if campaign.name == f"batch_{result.batch}":
            campaign = campaign.parent
        if not tab.load_dataset(str(result.dataset), campaign_directory=campaign):
            return
        identifier = result.options.get("name")
        target = result.options.get("y")
        if isinstance(identifier, str):
            tab.name_dropdown.setCurrentText(identifier)
        if isinstance(target, str):
            tab.y_dropdown.setCurrentText(target)
        ignored = result.options.get("ignore")
        selector = tab.ignore_selector
        selector.selected_list.clear()
        selector.set_available_items(tab.all_columns)
        if isinstance(ignored, list):
            for index in range(selector.available_list.count()):
                item = selector.available_list.item(index)
                column = item.text()
                item.setSelected(column in ignored and column not in (identifier, target))
            selector.move_to_selected()
        self.tabs.setCurrentWidget(tab)
        if self.workspace_layout.direction() == QBoxLayout.TopToBottom:
            self.results_toggle.setChecked(False)

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
