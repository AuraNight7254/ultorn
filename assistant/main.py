import platform
from pathlib import Path

import yaml

from assistant.core.brain import Brain
from assistant.core.logger import ActionLogger
from assistant.core.providers import create_provider
from assistant.core.registry import discover_skills
from assistant.io.text_io import read_command


ROOT = Path(__file__).resolve().parent.parent


def load_settings():
    settings_path = Path(__file__).resolve().parent / "config" / "settings.yaml"
    with settings_path.open(encoding="utf-8") as settings_file:
        settings = yaml.safe_load(settings_file)
    if not isinstance(settings, dict):
        raise ValueError("settings.yaml must contain a YAML mapping.")
    return settings


def run():
    system_name = platform.system()
    if system_name == "Windows":
        print("Detected OS: Windows.")
    else:
        print(f"Detected OS: {system_name}; this project is configured primarily for Windows.")

    settings = load_settings()
    assistant_settings = settings.get("assistant", {})
    provider_settings = settings.get("provider", {})
    assistant_name = assistant_settings.get("name", "ultron")

    provider = create_provider(provider_settings)
    logger = ActionLogger(ROOT / "logs" / "actions.jsonl")
    skills = discover_skills()
    send_whatsapp = skills.get("send_whatsapp")
    if send_whatsapp is not None:
        send_whatsapp.auto_send = bool(settings.get("whatsapp_auto_send", False))
        send_whatsapp.send_delay_seconds = float(
            settings.get("whatsapp_send_delay_seconds", 3)
        )
    brain = Brain(
        provider=provider,
        skills=skills,
        logger=logger,
        assistant_name=assistant_name,
    )

    print(f"{assistant_name} is ready. Type 'exit' to quit.")
    while True:
        try:
            command = read_command(assistant_name)
        except EOFError:
            break
        if command is None:
            continue
        if command.casefold() in {"exit", "quit"}:
            break
        print(brain.process(command))


if __name__ == "__main__":
    run()
