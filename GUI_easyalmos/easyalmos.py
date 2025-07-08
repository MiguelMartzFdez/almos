from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QFileDialog, QComboBox, QListWidget, QListWidgetItem, QLineEdit,
    QTextEdit, QProgressBar, QMessageBox, QCheckBox, QSizePolicy, QScrollArea
)
from PySide6.QtGui import QPixmap, QIcon, QWheelEvent
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
import pandas as pd
import os
import shlex
import subprocess
import threading
import platform
from ansi2html import Ansi2HTMLConverter
import subprocess
import psutil
import sys
from importlib.resources import files, as_file

# =============================================
# Generic parameters for the GUI and functions
# =============================================

# Style for the listbox
box_features = """
QListWidget {
    border: 1px solid gray;
    padding: 5px;
    font-family: Consolas;
    font-size: 12px;
}
QListWidget::item:selected {
    background: #0078d7;
    color: white;
}
"""
class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

def move_to_selected(available_list, ignore_list):
    selected_items = available_list.selectedItems()
    existing = {ignore_list.item(i).text() for i in range(ignore_list.count())}
    for item in selected_items:
        if item.text() not in existing:
            ignore_list.addItem(QListWidgetItem(item.text()))
        available_list.takeItem(available_list.row(item))

def move_to_available(ignore_list, available_list):
    selected_items = ignore_list.selectedItems()
    existing = {available_list.item(i).text() for i in range(available_list.count())}
    for item in selected_items:
        if item.text() not in existing:
            available_list.addItem(QListWidgetItem(item.text()))
        ignore_list.takeItem(ignore_list.row(item))

def stop_process(widget):
    """Stops the ALMOS process safely after user confirmation, non-blocking."""

    confirmation = QMessageBox.question(
        widget, 
        "WARNING!", 
        "Are you sure you want to stop ALMOS?",
        QMessageBox.Yes | QMessageBox.No, 
        QMessageBox.No
    )

    if confirmation == QMessageBox.No:
        return

    widget.manual_stop = True

    if hasattr(widget, 'worker') and widget.worker is not None and widget.worker.isRunning():
        widget.console_output.append(
            "<br><b><span style='color:orangered;'>Stopping ALMOS...</span></b>"
        )
        widget.progress.setRange(0, 100)
        widget.stop_button.setDisabled(True)
        QTimer.singleShot(0, widget.worker.stop)

class WorkerThread(QThread):
    output_received = Signal(str)
    error_received = Signal(str)
    process_finished = Signal(int)
    request_stop = Signal()

    def __init__(self, command, working_dir=None):
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
                self.process = subprocess.Popen(
                    shlex.split(self.command),
                    cwd=self.working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(
                    shlex.split(self.command),
                    cwd=self.working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    preexec_fn=os.setsid
                )

            def read_stdout():
                try:
                    for line in self.process.stdout:
                        if self._stop_requested:
                            break
                        formatted_line = self.ansi_converter.convert(line.strip(), full=False)
                        self.output_received.emit(formatted_line)
                except Exception as e:
                    self.error_received.emit(f"Error reading stdout: {e}")

            def read_stderr():
                try:
                    for line in self.process.stderr:
                        if self._stop_requested:
                            break
                        self.error_received.emit(line.strip())
                except Exception as e:
                    self.error_received.emit(f"Error reading stderr: {e}")

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            exit_code = self.process.wait() if self.process else -1
            stdout_thread.join()
            stderr_thread.join()

            self.process = None
            self.process_finished.emit(-1 if self._stop_requested else exit_code)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error_received.emit(f"Error in run(): {e}\n{tb}")

    def stop(self):
        self.request_stop.emit()

    def _handle_stop(self):
        self._stop_requested = True
        if not self.process:
            return
        try:
            parent = psutil.Process(self.process.pid)
            procs = parent.children(recursive=True)
            procs.append(parent)
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
            gone, alive = psutil.wait_procs(procs, timeout=2)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
        except Exception as e:
            self.error_received.emit(f"Error stopping process: {e}")

class ClusteringTab(QWidget):
    def on_process_finished(self, exit_code):
        """Handles the cleanup after the clustering process finishes."""
        self.run_button.setDisabled(False)
        self.stop_button.setDisabled(True)
        self.progress.setRange(0, 100)

        if hasattr(self, 'worker') and self.worker:
            if self.worker.process and self.worker.process.poll() is None:
                self.worker.stop()
            self.worker = None

        if hasattr(self, 'manual_stop') and self.manual_stop:
            self.console_output.clear()
            QMessageBox.information(self, "INFO", "ALMOS has been successfully stopped.")
            self.manual_stop = False
            return

        output_text = self.console_output.toPlainText()

        if "Time cluster:" in output_text:
            self.console_output.append("<span style='color:green;'>Process finished successfully.</span>")
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Success!")
            msg_box.setText("Clustering completed successfully.")
            msg_box.exec()
        else:
            self.console_output.append("<span style='color:orange;'>Process did not complete correctly.</span>")
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Process Failed")
            msg_box.setText("Clustering did not complete successfully.")
            msg_box.exec()

        self.manual_stop = False

    def __init__(self, progress_bar, console_output):
        super().__init__()
        self.progress = progress_bar
        self.console_output = console_output
        self.file_path = ""
        self.all_columns = []

        layout = QVBoxLayout(self)

        self.label = QLabel("Select CSV File:")
        layout.addWidget(self.label)
        self.file_button = QPushButton("Select file")
        self.file_button.clicked.connect(self.select_file)
        layout.addWidget(self.file_button)

        self.n_clusters_label = QLabel("Number of clusters (If not specified, will be estimated with 'Elbow method'):")
        layout.addWidget(self.n_clusters_label)
        self.n_clusters_entry = QLineEdit()
        layout.addWidget(self.n_clusters_entry)

        self.name_label = QLabel("Select name column:")
        layout.addWidget(self.name_label)
        self.name_dropdown = NoScrollComboBox()
        layout.addWidget(self.name_dropdown)

        self.y_label = QLabel("Select target column (optional):")
        layout.addWidget(self.y_label)
        self.y_dropdown = NoScrollComboBox()
        layout.addWidget(self.y_dropdown)

        # AQME Checkbox + Descriptor level combo (horizontal layout)
        aqme_row_layout = QHBoxLayout()

        self.aqme_checkbox = QCheckBox("Enable AQME Workflow")
        self.descp_combo = NoScrollComboBox()
        self.descp_combo.addItems(["denovo", "interpret", "full"])
        self.descp_combo.setCurrentText("interpret")

        aqme_row_layout.addWidget(self.aqme_checkbox)
        aqme_row_layout.addSpacing(20)  
        aqme_row_layout.addWidget(QLabel("Descriptor level:"))
        aqme_row_layout.addWidget(self.descp_combo)
        aqme_row_layout.addStretch() 

        layout.addLayout(aqme_row_layout)

        # --- Column selection layout ---
        column_layout = QHBoxLayout()

        # Left side (Available Columns)
        left_layout = QVBoxLayout()
        self.available_label = QLabel("Available Columns")
        self.available_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QListWidget.MultiSelection)
        self.available_list.setStyleSheet(box_features)
        left_layout.addWidget(self.available_label)
        left_layout.addWidget(self.available_list)

        # Buttons
        button_layout = QVBoxLayout()
        button_layout.setAlignment(Qt.AlignVCenter)

        self.add_button = QPushButton(">>")
        self.add_button.setFixedSize(40, 30)
        self.add_button.clicked.connect(lambda: move_to_selected(self.available_list, self.ignore_list))

        self.remove_button = QPushButton("<<")
        self.remove_button.setFixedSize(40, 30)
        self.remove_button.clicked.connect(lambda: move_to_available(self.ignore_list, self.available_list))

        button_layout.addStretch()
        button_layout.addWidget(self.add_button, alignment=Qt.AlignCenter)
        button_layout.addWidget(self.remove_button, alignment=Qt.AlignCenter)
        button_layout.addStretch()

        # Right side (Ignored Columns)
        right_layout = QVBoxLayout()
        self.ignored_label = QLabel("Ignored Columns")
        self.ignored_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.ignore_list = QListWidget()
        self.ignore_list.setSelectionMode(QListWidget.MultiSelection)
        self.ignore_list.setStyleSheet(box_features)
        right_layout.addWidget(self.ignored_label)
        right_layout.addWidget(self.ignore_list)

        # Assemble
        column_layout.addLayout(left_layout)
        column_layout.addLayout(button_layout)
        column_layout.addLayout(right_layout)
        layout.addLayout(column_layout)
        layout.addSpacing(15)

        # Run and Stop buttons in a horizontal layout, filling all available space
        button_row_layout = QHBoxLayout()

        self.run_button = QPushButton("Run Clustering")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3e8e41;
            }
            QPushButton:disabled {
            background-color: #b0b0b0;
            color: #eeeeee;
            }
        """)
        
        self.run_button.clicked.connect(self.run_clustering)
        self.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_row_layout.addWidget(self.run_button, stretch=1)  # Equal stretch

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 14px;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
            QPushButton:disabled {
                background-color: #b0b0b0;
                color: #eeeeee;
            }
        """)
        self.stop_button.clicked.connect(lambda: stop_process(self))
        self.stop_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stop_button.setDisabled(True)
        button_row_layout.addWidget(self.stop_button, stretch=1)

        layout.addLayout(button_row_layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if not file_path:
            return
        self.file_path = file_path
        self.label.setText(f"Selected file: {self.file_path}")
        df = pd.read_csv(self.file_path)
        self.all_columns = list(df.columns)
        self.name_dropdown.clear()
        self.y_dropdown.clear()
        self.name_dropdown.addItem("None")
        self.y_dropdown.addItem("None")
        self.name_dropdown.addItems(self.all_columns)
        self.y_dropdown.addItems(self.all_columns)
        self.available_list.clear()
        self.ignore_list.clear()
        for col in self.all_columns:
            self.available_list.addItem(QListWidgetItem(col))

    def run_clustering(self):
        if not self.file_path or self.name_dropdown.currentText() == "None":
            QMessageBox.warning(self, "WARNING!", "Please select a CSV file and name column.")
            return

        # Disable Run, enable Stop, set progress to indeterminate, clear console
        self.console_output.clear()
        self.run_button.setDisabled(True)
        self.stop_button.setDisabled(False)
        self.progress.setRange(0, 0)

        csv_name = self.file_path
        n_clusters = self.n_clusters_entry.text()
        descp_level = self.descp_combo.currentText() if self.aqme_checkbox.isChecked() else None
        aqme_workflow = self.aqme_checkbox.isChecked()
        name = self.name_dropdown.currentText()
        y = self.y_dropdown.currentText()
        ignore_columns = [self.ignore_list.item(i).text() for i in range(self.ignore_list.count())]
        ignore_value = ",".join(ignore_columns)

        command = f'python -u -m almos --cluster --input "{csv_name}"'
        if aqme_workflow:
            command += f' --aqme --descp_level "{descp_level}"'
        if name and name != "None" and not aqme_workflow:
            command += f' --name "{name}"'
        if y and y != "None":
            command += f' --y "{y}"'
        if ignore_value:
            command += f' --ignore "[{ignore_value}]"'
        if n_clusters:
            command += f' --n_clusters "{n_clusters}"'

        self.worker = WorkerThread(command)
        self.worker.output_received.connect(lambda msg: self.console_output.append(f"<span style='color:white;'>{msg}</span>"))
        self.worker.error_received.connect(lambda msg: self.console_output.append(f"<span style='color:red;'>{msg}</span>"))
        self.worker.process_finished.connect(self.on_process_finished)
        self.worker.start()

class ActiveLearningTab(QWidget):
    def update_ui_for_mode(self):
        mode = self.mode_selector.currentText()
        if mode == "Exploratory Learning":
            self.n_points_label.setText("Number of experiments (default: 1):")
            self.batch_label.hide()
            self.batch_entry.hide()
            self.y_dropdown.show()
            self.y_available_label.hide()
            self.y_available_list.hide()
            self.y_selected_label.hide()
            self.y_selected_list.hide()
            self.add_y_button.hide()
            self.remove_y_button.hide()
        elif mode == "Bayesian Optimization":
            self.n_points_label.setText("Number of BO iterations (default: 1):")
            self.batch_label.show()
            self.batch_entry.show()
            self.y_dropdown.hide()
            self.y_available_label.show()
            self.y_available_list.show()
            self.y_selected_label.show()
            self.y_selected_list.show()
            self.add_y_button.show()
            self.remove_y_button.show()

    def run_mode_dispatcher(self):
        mode = self.mode_selector.currentText()
        if mode == "Exploratory Learning":
            self.run_active_learning()
        elif mode == "Bayesian Optimization":
            self.run_bayesian_optimization()

    def on_process_finished(self, exit_code):
        """Handles the cleanup after the Active Learning process finishes."""
        self.run_button.setDisabled(False)
        self.stop_button.setDisabled(True)
        self.progress.setRange(0, 100)

        if hasattr(self, 'worker') and self.worker:
            if self.worker.process and self.worker.process.poll() is None:
                self.worker.stop()
            self.worker = None

        if hasattr(self, 'manual_stop') and self.manual_stop:
            self.console_output.clear()
            QMessageBox.information(self, "INFO", "ALMOS has been successfully stopped.")
            self.manual_stop = False
            return

        output_text = self.console_output.toPlainText()
        mode = self.mode_selector.currentText()

        # Define success text and message by mode
        if mode == "Exploratory Learning":
            success_text = "Process Completed! Total time taken for the process"
            success_msg = "Active Learning completed successfully."
        elif mode == "Bayesian Optimization":
            success_text = "Process completed in"
            success_msg = "Bayesian Optimization completed successfully."
        else:
            success_text = ""
            success_msg = "Process completed."

        if success_text and success_text in output_text:
            self.console_output.append("<span style='color:green;'>Process finished successfully.</span>")
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Success!")
            msg_box.setText(success_msg)
            msg_box.exec()
        else:
            self.console_output.append("<span style='color:orange;'>Process did not complete correctly.</span>")
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("WARNING!")
            msg_box.setText(f"{mode} did not complete successfully.")
            msg_box.exec()

        self.manual_stop = False

    def __init__(self, progress_bar, console_output):
        super().__init__()
        self.progress = progress_bar
        self.console_output = console_output
        self.file_path = ""
        self.all_columns = []

        # SCROLL SETUP
        outer_layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)
        self.scroll_layout = QVBoxLayout(scroll_content)
        outer_layout.addWidget(scroll_area)

        # GUI elements go in self.scroll_layout
        self.label = QLabel("Select CSV File:")
        self.scroll_layout.addWidget(self.label)

        self.file_button = QPushButton("Select file")
        self.file_button.clicked.connect(self.select_file)
        self.scroll_layout.addWidget(self.file_button)

        # Active Learning mode selector + Reverse checkbox (horizontal layout)
        mode_row_layout = QHBoxLayout()

        self.mode_selector = NoScrollComboBox()
        self.mode_selector.addItems(["Exploratory Learning", "Bayesian Optimization"])
        self.mode_selector.currentIndexChanged.connect(self.update_ui_for_mode)

        self.reverse_checkbox = QCheckBox("Minimize objective") # Minimize if checked
        self.reverse_checkbox.setToolTip("Check this if your goal is to minimize the selected target instead of maximizing it.")

        mode_row_layout.addWidget(QLabel("Select Active Learning mode:"))
        mode_row_layout.addWidget(self.mode_selector)
        mode_row_layout.addSpacing(20)
        mode_row_layout.addWidget(self.reverse_checkbox)
        mode_row_layout.addStretch()
        self.scroll_layout.addLayout(mode_row_layout)
        self.scroll_layout.addSpacing(15)

        self.n_points_label = QLabel("Number of experiments (dafault: 1):")
        self.scroll_layout.addWidget(self.n_points_label)
        self.n_points_entry = QLineEdit()
        self.scroll_layout.addWidget(self.n_points_entry)

        self.name_label = QLabel("Select name column:")
        self.scroll_layout.addWidget(self.name_label)

        self.name_dropdown = NoScrollComboBox()
        self.scroll_layout.addWidget(self.name_dropdown)

        self.batch_label = QLabel("Batch number (default: 0):")
        self.scroll_layout.addWidget(self.batch_label)
        self.batch_entry = QLineEdit()
        self.scroll_layout.addWidget(self.batch_entry)

        self.y_label = QLabel("Select target column(s):")
        self.scroll_layout.addWidget(self.y_label)

        # Single selection for Exploratory
        self.y_dropdown = NoScrollComboBox()
        self.scroll_layout.addWidget(self.y_dropdown)

        # --- Y selection layout for Bayesian Optimization ---
        y_column_layout = QHBoxLayout()

        # Left: Available y columns
        y_left_layout = QVBoxLayout()
        self.y_available_label = QLabel("Available target columns (y)")
        self.y_available_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.y_available_list = QListWidget()
        self.y_available_list.setSelectionMode(QListWidget.MultiSelection)
        self.y_available_list.setStyleSheet(box_features)
        y_left_layout.addWidget(self.y_available_label)
        y_left_layout.addWidget(self.y_available_list)

        # Center: Buttons
        y_button_layout = QVBoxLayout()
        y_button_layout.setAlignment(Qt.AlignVCenter)
        self.add_y_button = QPushButton(">>")
        self.add_y_button.setFixedSize(40, 30)
        self.add_y_button.clicked.connect(lambda: move_to_selected(self.y_available_list, self.y_selected_list))
        self.remove_y_button = QPushButton("<<")
        self.remove_y_button.setFixedSize(40, 30)
        self.remove_y_button.clicked.connect(lambda: move_to_available(self.y_selected_list, self.y_available_list))

        y_button_layout.addStretch()
        y_button_layout.addWidget(self.add_y_button, alignment=Qt.AlignCenter)
        y_button_layout.addWidget(self.remove_y_button, alignment=Qt.AlignCenter)
        y_button_layout.addStretch()

        # Right: Selected y columns
        y_right_layout = QVBoxLayout()
        self.y_selected_label = QLabel("Selected y columns")
        self.y_selected_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.y_selected_list = QListWidget()
        self.y_selected_list.setSelectionMode(QListWidget.MultiSelection)
        self.y_selected_list.setStyleSheet(box_features)
        y_right_layout.addWidget(self.y_selected_label)
        y_right_layout.addWidget(self.y_selected_list)

        # Assemble the full layout
        y_column_layout.addLayout(y_left_layout)
        y_column_layout.addLayout(y_button_layout)
        y_column_layout.addLayout(y_right_layout)

        self.scroll_layout.addLayout(y_column_layout)

        # --- Column selection layout ---
        column_layout = QHBoxLayout()

        left_layout = QVBoxLayout()
        self.available_label = QLabel("Available Columns")
        self.available_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QListWidget.MultiSelection)
        self.available_list.setStyleSheet(box_features)
        left_layout.addWidget(self.available_label)
        left_layout.addWidget(self.available_list)

        button_layout = QVBoxLayout()
        button_layout.setAlignment(Qt.AlignVCenter)

        self.add_button = QPushButton(">>")
        self.add_button.setFixedSize(40, 30)
        self.add_button.clicked.connect(lambda: move_to_selected(self.available_list, self.ignore_list))
        self.remove_button = QPushButton("<<")
        self.remove_button.setFixedSize(40, 30)
        self.remove_button.clicked.connect(lambda: move_to_available(self.ignore_list, self.available_list))

        button_layout.addStretch()
        button_layout.addWidget(self.add_button, alignment=Qt.AlignCenter)
        button_layout.addWidget(self.remove_button, alignment=Qt.AlignCenter)
        button_layout.addStretch()

        right_layout = QVBoxLayout()
        self.ignored_label = QLabel("Ignored columns")
        self.ignored_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.ignore_list = QListWidget()
        self.ignore_list.setSelectionMode(QListWidget.MultiSelection)
        self.ignore_list.setStyleSheet(box_features)
        right_layout.addWidget(self.ignored_label)
        right_layout.addWidget(self.ignore_list)

        column_layout.addLayout(left_layout)
        column_layout.addLayout(button_layout)
        column_layout.addLayout(right_layout)
        self.scroll_layout.addLayout(column_layout)
        self.scroll_layout.addSpacing(15)

        # Run and Stop buttons
        button_row_layout = QHBoxLayout()

        self.run_button = QPushButton("Run Active Learning")
        self.run_button.setStyleSheet("""QPushButton { background-color: #4CAF50; color: white; font-size: 14px; padding: 8px 16px; border: none; border-radius: 6px; }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:pressed { background-color: #3e8e41; }
            QPushButton:disabled { background-color: #b0b0b0; color: #eeeeee; }""")
        self.run_button.clicked.connect(self.run_mode_dispatcher)
        self.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_row_layout.addWidget(self.run_button, stretch=1)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("""QPushButton { background-color: #f44336; color: white; font-size: 14px; padding: 8px 16px; border: none; border-radius: 6px; }
            QPushButton:hover { background-color: #e53935; }
            QPushButton:pressed { background-color: #c62828; }
            QPushButton:disabled { background-color: #b0b0b0; color: #eeeeee; }""")
        self.stop_button.clicked.connect(lambda: stop_process(self))
        self.stop_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stop_button.setDisabled(True)
        button_row_layout.addWidget(self.stop_button, stretch=1)

        self.scroll_layout.addLayout(button_row_layout)

        # Inicializa estado correcto
        self.update_ui_for_mode()

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if not file_path:
            return
        self.file_path = file_path
        self.label.setText(f"Selected file: {self.file_path}")
        df = pd.read_csv(self.file_path)
        self.all_columns = list(df.columns)
        self.name_dropdown.clear()
        self.y_dropdown.clear()
        self.name_dropdown.addItem("None")
        self.y_dropdown.addItem("None")
        self.name_dropdown.addItems(self.all_columns)
        self.y_dropdown.addItems(self.all_columns)
        self.available_list.clear()
        self.ignore_list.clear() 
        for col in self.all_columns:
            self.available_list.addItem(QListWidgetItem(col))
        self.y_available_list.clear()
        self.y_selected_list.clear()
        for col in self.all_columns:
            self.y_available_list.addItem(QListWidgetItem(col))

    def run_active_learning(self):
        if not self.file_path or self.name_dropdown.currentText() == "None":
            QMessageBox.warning(self, "WARNING!", "Please select a CSV file, name column and target column.")
            return

        # Disable Run, enable Stop, set progress to indeterminate, clear console
        self.console_output.clear()
        self.run_button.setDisabled(True)
        self.stop_button.setDisabled(False)
        self.progress.setRange(0, 0)

        n_points = self.n_points_entry.text()
        y_column = self.y_dropdown.currentText()
        name_column = self.name_dropdown.currentText()
        ignore_columns = [item.text() for item in self.ignore_list.selectedItems()]
        ignore_value = ",".join(ignore_columns)
        reversed = self.reverse_checkbox.isChecked()

        command = f'python -u -m almos --el --csv_name "{self.file_path}" --name "{name_column}"'
        if n_points:
            command += f' --n_exps "{n_points}"'
        if y_column and y_column != "None":
            command += f' --y "{y_column}"'
        if ignore_value:
            command += f' --ignore "[{ignore_value}]"'
        if reversed:
            command += ' --reverse'

        self.worker = WorkerThread(command)
        self.worker.output_received.connect(lambda msg: self.console_output.append(f"<span style='color:white;'>{msg}</span>"))
        self.worker.error_received.connect(lambda msg: self.console_output.append(f"<span style='color:red;'>{msg}</span>"))
        self.worker.process_finished.connect(self.on_process_finished)
        self.worker.start()

    def run_bayesian_optimization(self):
        """Runs the Bayesian Optimization process with the selected parameters."""
        if not self.file_path:
            QMessageBox.warning(self, "WARNING!", "Please select a CSV file.")
            return

        name_column = self.name_dropdown.currentText()
        y_columns = [item.text() for item in self.y_selected_list.selectedItems()]
        if not y_columns:
            y_columns = [self.y_selected_list.item(i).text() for i in range(self.y_selected_list.count())]

        if name_column == "None" or not y_columns:
            QMessageBox.warning(self, "WARNING!", "Please select both name and at least one target (y) column.")
            return

        y_string = ",".join(y_columns)

        self.console_output.clear()
        self.run_button.setDisabled(True)
        self.stop_button.setDisabled(False)
        self.progress.setRange(0, 0)

        n_points = self.n_points_entry.text()
        batch_number = self.batch_entry.text() or "0"
        ignore_columns = [item.text() for item in self.ignore_list.selectedItems()]
        ignore_value = ",".join(ignore_columns)
        reversed = self.reverse_checkbox.isChecked()

        command = (
            f'python -u -m almos --bo --csv_name "{self.file_path}" '
            f'--name "{name_column}" --batch_number "{batch_number}" --y "[{y_string}]"'
        )

        if n_points:
            command += f' --n_exps "{n_points}"'
        if ignore_value:
            command += f' --ignore "[{ignore_value}]"'
        if reversed:
            command += ' --reverse'

        self.worker = WorkerThread(command)
        self.worker.output_received.connect(lambda msg: self.console_output.append(f"<span style='color:white;'>{msg}</span>"))
        self.worker.error_received.connect(lambda msg: self.console_output.append(f"<span style='color:red;'>{msg}</span>"))
        self.worker.process_finished.connect(self.on_process_finished)
        self.worker.start()

class ALMOSApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ALMOS")
        self.resize(700, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        with as_file(files("almos") / "icons" / "almos_logo.png") as logo_path:
            if logo_path.exists():
                pixmap = QPixmap(str(logo_path)).scaled(400, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                logo_label = QLabel()
                logo_label.setPixmap(pixmap)
                logo_label.setAlignment(Qt.AlignCenter)
                main_layout.addWidget(logo_label)

        with as_file(files("almos") / "icons" / "almos_icon.png") as icon_path:
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(275)
        self.console_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.console_output.setStyleSheet("""
            QTextEdit { background-color: black; color: white; padding: 5px; font-family: monospace; }
            QScrollBar:vertical { background: #2e2e2e; width: 12px; }
            QScrollBar::handle:vertical { background: #5a5a5a; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #787878; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; height: 0px; }
        """)
        main_layout.addWidget(self.console_output, stretch=1)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(10)
        self.progress.setStyleSheet("""
            QProgressBar { border: 2px solid gray; border-radius: 10px; background: #f0f0f0; text-align: center; font-weight: bold; }
            QProgressBar::chunk { background-color: #4CAF50; width: 5px; border-radius: 10px; }
        """)
        main_layout.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.clustering_tab = ClusteringTab(self.progress, self.console_output)
        self.active_learning_tab = ActiveLearningTab(self.progress, self.console_output)
        self.tabs.addTab(self.clustering_tab, "Clustering")
        self.tabs.addTab(self.active_learning_tab, "Active Learning")
        main_layout.addWidget(self.tabs)

    @Slot(int)
    def on_process_finished(self, exit_code):
        current_tab = self.tabs.currentWidget()
        if hasattr(current_tab, "on_process_finished"):
            current_tab.on_process_finished(exit_code)
        else:
            self.progress.setRange(0, 100)

    def closeEvent(self, event):
        confirm = any(
            hasattr(tab, 'worker') and tab.worker and tab.worker.isRunning()
            for tab in [self.clustering_tab, self.active_learning_tab]
        )
        if confirm:
            reply = QMessageBox.question(
                self, "Exit Confirmation",
                "ALMOS is still running. Do you want to stop the process and exit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                for tab in [self.clustering_tab, self.active_learning_tab]:
                    if hasattr(tab, 'worker') and tab.worker.isRunning():
                        tab.worker.stop()
                        tab.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ALMOSApp()
    window.show()
    sys.exit(app.exec())