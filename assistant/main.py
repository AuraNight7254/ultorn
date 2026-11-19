import platform
from pathlib import Path

import yaml

from assistant.core.brain import Brain
from assistant.core.contacts import load_contacts
from assistant.core.logger import ActionLogger
from assistant.core.providers import create_provider
from assistant.core.registry import discover_skills
from assistant.io.hotkey import PushToTalk
from assistant.io.stt import MicrophoneRecorder, SpeechTranscriber
from assistant.io.text_io import read_command
from assistant.skills.base import load_app_config


ROOT = Path(__file__).resolve().parent.parent


def load_settings():
    settings_path = Path(__file__).resolve().parent / "config" / "settings.yaml"
    with settings_path.open(encoding="utf-8") as settings_file:
        settings = yaml.safe_load(settings_file)
    if not isinstance(settings, dict):
        raise ValueError("settings.yaml must contain a YAML mapping.")
    return settings


def build_initial_prompt() -> str:
    config = load_app_config()
    names = []
    for section in ("apps", "websites"):
        entries = config.get(section, {})
        if not isinstance(entries, dict):
            continue
        for name, details in entries.items():
            names.append(str(name))
            if isinstance(details, dict):
                aliases = details.get("aliases", [])
                if isinstance(aliases, list):
                    names.extend(alias for alias in aliases if isinstance(alias, str))
    try:
        contacts = load_contacts()
    except (OSError, ValueError):
        contacts = {}
    for contact in contacts.values():
        names.append(contact.name)
        names.extend(contact.aliases)
    return ", ".join(dict.fromkeys(name for name in names if name.strip()))


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

    push_to_talk = None
    voice_settings = settings.get("voice", {})
    if voice_settings.get("enabled", True):
        model_directory = Path(
            voice_settings.get("model_directory", "assistant/models/faster-whisper-small")
        )
        if not model_directory.is_absolute():
            model_directory = ROOT / model_directory
        transcriber = SpeechTranscriber(
            model_name=voice_settings.get("stt_model", "small"),
            language=voice_settings.get("stt_language", "ur"),
            initial_prompt=build_initial_prompt(),
            model_directory=model_directory,
            silence_rms_threshold=float(
                voice_settings.get("silence_rms_threshold", 0.005)
            ),
            no_speech_prob_threshold=float(
                voice_settings.get("no_speech_prob_threshold", 0.6)
            ),
        )
        recorder = MicrophoneRecorder(
            device=voice_settings.get("mic_device"),
            sample_rate=int(voice_settings.get("sample_rate", 16000)),
        )

        def process_voice_command(transcript):
            print(brain.process(transcript))

        push_to_talk = PushToTalk(
            hotkey=voice_settings.get("hotkey", "ctrl+alt+space"),
            recorder=recorder,
            transcriber=transcriber,
            on_command=process_voice_command,
            on_message=print,
            show_transcript=bool(voice_settings.get("show_transcript", True)),
            max_hold_seconds=float(voice_settings.get("max_hold_seconds", 20)),
            min_hold_seconds=float(voice_settings.get("min_hold_seconds", 0.25)),
        )
        push_to_talk.start()

    print(f"{assistant_name} is ready. Type 'exit' to quit.")
    try:
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
    finally:
        if push_to_talk is not None:
            push_to_talk.stop()


if __name__ == "__main__":
    run()
