"""Display completed workflow milestones and the next step in EasyALMOS."""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QStyle, QVBoxLayout, QWidget,
)


class WorkflowProgress(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("workflowProgress")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        self.status = QLabel()
        self.status.setObjectName("secondaryText")
        self.toggle = QPushButton("Hide Steps")
        self.toggle.setCheckable(True)
        header.addWidget(self.title, stretch=1)
        header.addWidget(self.status)
        header.addWidget(self.toggle)
        layout.addLayout(header)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName("Workflow progress")
        layout.addWidget(self.bar)

        self.checklist = QWidget()
        self.checklist_layout = QGridLayout(self.checklist)
        self.checklist_layout.setContentsMargins(0, 0, 0, 0)
        self.checklist_layout.setHorizontalSpacing(16)
        self.checklist_layout.setVerticalSpacing(4)
        for column in range(2):
            self.checklist_layout.setColumnStretch(column, 1)
        layout.addWidget(self.checklist)
        self.toggle.toggled.connect(self.toggle_details)

        self.steps: dict[str, QLabel] = {}
        self.markers: dict[str, QLabel] = {}
        self.check_icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        self.step_names: dict[str, str] = {}
        self.completed: dict[str, str] = {}
        self.state = ""
        self.hide()

    @Slot(bool)
    def toggle_details(self, visible: bool):
        self.checklist.setVisible(visible)
        self.toggle.setText("Hide Steps" if visible else "Show Steps")

    @Slot(str, object)
    def begin(self, title: str, steps: tuple[tuple[str, str], ...]):
        for label in self.steps.values():
            row = label.parentWidget()
            self.checklist_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.steps.clear()
        self.markers.clear()
        self.completed.clear()
        self.step_names = dict(steps)
        self.title.setText(f"{title} progress")
        self.state = "Running"
        self.status.setText(self.state)
        for index, (key, _) in enumerate(steps):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)
            marker = QLabel()
            marker.setFixedSize(15, 17)
            marker.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(marker, alignment=Qt.AlignTop)
            label = QLabel()
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            row_layout.addWidget(label, stretch=1)
            self.markers[key] = marker
            self.steps[key] = label
            self.checklist_layout.addWidget(row, index // 2, index % 2)
        self.bar.setRange(0, 0)
        self.toggle.setChecked(True)
        self.update_steps()
        self.show()

    @Slot(str, str)
    def complete_step(self, key: str, detail: str):
        if self.state == "Running" and key in self.step_names and key not in self.completed:
            self.completed[key] = detail
            self.bar.setRange(0, 100)
            self.bar.setValue(min(99, 100 * len(self.completed) // len(self.steps)))
            self.status.setText(f"{self.state} · {len(self.completed)}/{len(self.steps)} steps")
            self.update_steps()

    @Slot(int, bool)
    def finish(self, exit_code: int, stopped: bool):
        if self.state != "Running":
            return
        if stopped:
            self.state = "Stopped"
        else:
            self.state = "Completed" if exit_code == 0 else "Failed"
        self.bar.setRange(0, 100)
        if not self.completed:
            self.bar.setValue(0)
        status = self.state
        if self.state == "Completed":
            if len(self.completed) == len(self.steps):
                self.bar.setValue(100)
            else:
                status = "Completed · some step details unavailable"
        self.status.setText(status)
        self.update_steps()

    def update_steps(self):
        current = next((key for key in self.steps if key not in self.completed), None)
        for key, name in self.step_names.items():
            if key in self.completed:
                detail = self.completed[key]
                self.set_step(key, f"{name} · {detail}", "Completed", "#23694c")
            elif key == current and self.state == "Running":
                self.set_step(key, name, "In progress", "#204f3b", "●")
            elif key == current and self.state in ("Failed", "Stopped"):
                self.set_step(key, name, self.state, "#922f2b", "×")
            else:
                self.set_step(key, name, "Pending", "#526961", "○")

    def set_step(self, key: str, text: str, status: str, color: str, symbol: str = ""):
        label = self.steps[key]
        marker = self.markers[key]
        label.setText(text)
        label.setAccessibleDescription(status)
        label.setStyleSheet(f"color: {color};")
        marker.setStyleSheet(f"color: {color};")
        if status == "Completed":
            marker.setPixmap(self.check_icon.pixmap(13, 13))
        else:
            marker.setText(symbol)
