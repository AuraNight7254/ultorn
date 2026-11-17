from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Result:
    ok: bool
    reply: str


class Skill(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str

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
    requested = requested_name.strip().casefold()
    for configured_name, details in items.items():
        if not isinstance(details, dict):
            continue
        aliases = details.get("aliases", [])
        if not isinstance(aliases, list):
            continue
        candidates = [configured_name, *aliases]
        if any(isinstance(alias, str) and alias.strip().casefold() == requested for alias in candidates):
            return configured_name, details
    return None, None
