from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import unicodedata

import yaml


@dataclass(frozen=True)
class Result:
    ok: bool
    reply: str
    auto_send_attempted: bool = False
    auto_send_window_check_passed: bool | None = None
    foreground_process: str | None = None
    foreground_title: str | None = None


@dataclass(frozen=True)
class PreparedAction:
    status: str
    reply: str = ""
    params: dict[str, Any] | None = None
    candidates: tuple[dict[str, Any], ...] = ()


class Skill(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str

    def prepare(self, **params) -> PreparedAction:
        return PreparedAction(status="ready", params=dict(params))

    @abstractmethod
    def run(self, **params) -> Result:
        raise NotImplementedError


def load_app_config():
    config_path = Path(__file__).resolve().parents[1] / "config" / "apps.yaml"
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError("apps.yaml must contain a YAML mapping.")
    return config


def resolve_alias(items: dict, requested_name: str):
    requested = normalize_alias(requested_name)
    for configured_name, details in items.items():
        if not isinstance(details, dict):
            continue
        aliases = details.get("aliases", [])
        if not isinstance(aliases, list):
            continue
        candidates = [configured_name, *aliases]
        if any(isinstance(alias, str) and normalize_alias(alias) == requested for alias in candidates):
            return configured_name, details
    return None, None


def normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().casefold().split())
