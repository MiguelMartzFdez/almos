"""Pass workflow milestones from ALMOS subprocesses to EasyALMOS."""

import json
import os


PROGRESS_ENV = "ALMOS_GUI_PROGRESS"
PROGRESS_PREFIX = "ALMOS_PROGRESS "


def report_progress(step: str, detail: str):
    """Report a completed step when the GUI has requested progress events."""
    if os.environ.get(PROGRESS_ENV) == "1":
        print(PROGRESS_PREFIX + json.dumps({"step": step, "detail": detail}), flush=True)


def read_progress(line: str) -> tuple[str, str] | None:
    """Read a progress event and leave ordinary subprocess output untouched."""
    if not line.startswith(PROGRESS_PREFIX):
        return None
    try:
        event = json.loads(line.removeprefix(PROGRESS_PREFIX))
    except ValueError:
        return None
    if isinstance(event, dict) and isinstance(event.get("step"), str) and isinstance(event.get("detail"), str):
        return event["step"], event["detail"]
    return None
