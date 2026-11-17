import json
from datetime import datetime, timezone
from pathlib import Path

from assistant.skills.base import Result


class ActionLogger:
    def __init__(self, path: Path):
        self.path = Path(path)

    def log(self, raw_command: str, skill: str | None, params: dict, confirmed: bool, result: Result):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_command": raw_command,
            "skill": skill,
            "params": params,
            "confirmed": confirmed,
            "auto_send_attempted": result.auto_send_attempted,
            "auto_send_window_check_passed": result.auto_send_window_check_passed,
            "foreground_process": result.foreground_process,
            "foreground_title": result.foreground_title,
            "result": {"ok": result.ok, "reply": result.reply},
        }
        with self.path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
