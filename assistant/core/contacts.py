import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml


E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


@dataclass(frozen=True)
class Contact:
    name: str
    number: str
    aliases: tuple[str, ...]


def normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().casefold().split())


def load_contacts(path: Path | None = None) -> dict[str, Contact]:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "contacts.yaml"
    if not path.exists():
        raise FileNotFoundError(
            "contacts.yaml is missing; copy config/contacts.example.yaml to "
            "config/contacts.yaml and add your contacts."
        )

    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)
    if not isinstance(data, dict) or not isinstance(data.get("contacts"), dict):
        raise ValueError("contacts.yaml must contain a 'contacts' mapping.")

    contacts = {}
    for name, details in data["contacts"].items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every contact name must be a non-empty string.")
        if not isinstance(details, dict):
            raise ValueError(f"Contact '{name}' must have a mapping.")
        number = details.get("number")
        if not isinstance(number, str) or not E164_PATTERN.fullmatch(number):
            raise ValueError(f"Contact '{name}' has an invalid E.164 number.")
        aliases = details.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            raise ValueError(f"Contact '{name}' aliases must be a list of strings.")
        contacts[name] = Contact(
            name=name,
            number=number,
            aliases=tuple(alias for alias in aliases if alias.strip()),
        )
    return contacts


def find_contacts(requested_name: str, contacts: dict[str, Contact]) -> list[Contact]:
    requested = normalize_alias(requested_name)
    matches = []
    for contact in contacts.values():
        candidates = (contact.name, *contact.aliases)
        if requested in {normalize_alias(candidate) for candidate in candidates}:
            matches.append(contact)
    return matches
