from typing import Callable
from urllib.parse import urlsplit
import webbrowser

from assistant.skills.base import Result, Skill, load_app_config, resolve_alias


class OpenWebsiteSkill(Skill):
    name = "open_website"
    description = (
        "Open a website configured in the allowlist. Match the user's spoken website name "
        "or alias exactly; do not invent URLs."
    )
    parameters = {
        "type": "object",
        "properties": {
            "website": {"type": "string", "description": "Configured website name or alias."},
        },
        "required": ["website"],
        "additionalProperties": False,
    }
    risk = "safe"

    def __init__(self, websites=None, opener: Callable[[str], bool] = webbrowser.open):
        config = load_app_config() if websites is None else {"websites": websites}
        self.websites = config.get("websites", {})
        self.opener = opener

    def run(self, website: str) -> Result:
        name, details = resolve_alias(self.websites, website)
        if details is None:
            return Result(ok=False, reply=f"I don't have {website} configured, so I won't guess.")
        url = details.get("url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return Result(ok=False, reply=f"{name} has an invalid website URL configured.")
        if not self.opener(url):
            return Result(ok=False, reply=f"I couldn't open {name} in your browser.")
        return Result(ok=True, reply=f"Opening {name} in your browser.")
