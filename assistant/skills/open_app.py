import os
import platform
import subprocess
from typing import Callable
from urllib.parse import urlsplit

from assistant.skills.base import Result, Skill, load_app_config, resolve_alias


def launch_target(target: str):
    parsed = urlsplit(target)
    is_windows_path = (
        len(parsed.scheme) == 1
        and len(target) > 2
        and target[1] == ":"
        and target[2] in {"\\", "/"}
    )
    if parsed.scheme and not is_windows_path:
        if parsed.scheme not in {"http", "https", "mailto", "ms-settings", "spotify"}:
            raise ValueError("That application URI scheme is not supported.")
        if platform.system() == "Windows":
            os.startfile(target)
        else:
            subprocess.Popen([target], shell=False)
        return
    subprocess.Popen([target], shell=False)


class OpenAppSkill(Skill):
    name = "open_app"
    description = (
        "Open an application that is configured in the allowlist. Match the user's spoken "
        "app name or alias exactly; if it is not configured, do not guess."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Configured app name or alias."},
        },
        "required": ["app"],
        "additionalProperties": False,
    }
    risk = "safe"

    def __init__(self, apps=None, launcher: Callable[[str], None] = launch_target):
        config = load_app_config() if apps is None else {"apps": apps}
        self.apps = config.get("apps", {})
        self.launcher = launcher

    def run(self, app: str) -> Result:
        name, details = resolve_alias(self.apps, app)
        if details is None:
            return Result(ok=False, reply=f"I don't have {app} configured, so I won't guess.")
        target = details.get("target")
        if not isinstance(target, str) or not target.strip():
            return Result(ok=False, reply=f"{name} has no launch target configured.")
        try:
            self.launcher(target)
        except (OSError, ValueError) as error:
            return Result(ok=False, reply=f"I couldn't open {name}: {error}.")
        return Result(ok=True, reply=f"Opening {name}.")
