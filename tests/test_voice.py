from pathlib import Path
import sys
import types

import pytest

from assistant.core.contacts import Contact
from assistant.io.hotkey import PushToTalk
from assistant.io.stt import (
    MicrophoneRecorder,
    MicrophoneUnavailable,
    SpeechModelUnavailable,
    SpeechTranscriber,
)
from assistant.io.text_io import read_command
import assistant.main as main


class FakeSegment:
    def __init__(self, text, no_speech_prob=0.0):
        self.text = text
        self.no_speech_prob = no_speech_prob


class FakeModel:
    def __init__(self, segments):
        self.segments = segments
        self.options = None

    def transcribe(self, audio, **options):
        self.options = options
        return iter(self.segments), object()


class FakeRecorder:
    def __init__(self, start_error=None, audio=(0.1, 0.1)):
        self.start_error = start_error
        self.audio = audio
        self.starts = 0
        self.stops = 0
        self.discards = 0

    def start(self):
        self.starts += 1
        if self.start_error:
            raise self.start_error

    def stop(self):
        self.stops += 1
        return self.audio

    def discard(self):
        self.discards += 1


class FakeKeyboard:
    def __init__(self):
        self.registrations = []
        self.removed = []

    def add_hotkey(self, hotkey, callback, **options):
        handle = len(self.registrations)
        self.registrations.append((hotkey, callback, options))
        return handle

    def remove_hotkey(self, handle):
        self.removed.append(handle)


class FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


def make_transcriber(tmp_path, model, **options):
    model_directory = tmp_path / "small"
    model_directory.mkdir()
    (model_directory / "config.json").write_text("{}", encoding="utf-8")
    return SpeechTranscriber(
        model_directory=model_directory,
        model_factory=lambda *args, **kwargs: model,
        **options,
    )


def test_silence_and_near_silence_are_empty_without_model_load(tmp_path):
    transcriber = SpeechTranscriber(
        model_directory=tmp_path / "not-downloaded",
        model_factory=lambda *args, **kwargs: pytest.fail("silent audio must not load model"),
    )

    assert transcriber.transcribe([0.0, 0.0, 0.0]) == ""
    assert transcriber.transcribe([0.0001, -0.0001]) == ""


def test_transcriber_uses_vad_and_disables_previous_text(tmp_path):
    model = FakeModel([FakeSegment("chrome kholo")])
    transcriber = make_transcriber(
        tmp_path,
        model,
        language="ur",
        initial_prompt="Chrome, Ali, علی",
    )

    result = transcriber.transcribe([0.1, -0.1, 0.2])

    assert result == "chrome kholo"
    assert model.options["language"] == "ur"
    assert model.options["initial_prompt"] == "Chrome, Ali, علی"
    assert model.options["vad_filter"] is True
    assert model.options["condition_on_previous_text"] is False


def test_high_no_speech_probability_discards_whisper_hallucination(tmp_path):
    model = FakeModel([FakeSegment("Thank you.", no_speech_prob=0.9)])
    transcriber = make_transcriber(tmp_path, model, no_speech_prob_threshold=0.6)

    assert transcriber.transcribe([0.1, 0.2, -0.1]) == ""


def test_auto_language_is_sent_as_none(tmp_path):
    model = FakeModel([FakeSegment("hello")])
    transcriber = make_transcriber(tmp_path, model, language="auto")

    transcriber.transcribe([0.1, -0.1])

    assert model.options["language"] is None


def test_model_download_is_cached_and_reused_offline(tmp_path):
    model_directory = tmp_path / "small"
    model = FakeModel([FakeSegment("hello")])
    downloads = []

    def download(model_name, destination):
        downloads.append(model_name)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "config.json").write_text("{}", encoding="utf-8")

    transcriber = SpeechTranscriber(
        model_directory=model_directory,
        model_factory=lambda *args, **kwargs: model,
        download_model=download,
    )
    assert transcriber.transcribe([0.1, -0.1]) == "hello"
    transcriber._model = None
    assert transcriber.transcribe([0.1, -0.1]) == "hello"

    assert downloads == ["small"]


def test_missing_model_returns_specific_error(tmp_path):
    transcriber = SpeechTranscriber(
        model_directory=tmp_path / "small",
        download_model=lambda *_: (_ for _ in ()).throw(OSError("offline")),
    )

    with pytest.raises(SpeechModelUnavailable):
        transcriber.transcribe([0.1, -0.1])


def test_build_initial_prompt_includes_app_and_contact_names(monkeypatch):
    monkeypatch.setattr(
        main,
        "load_app_config",
        lambda: {
            "apps": {"chrome": {"aliases": ["browser", "کروم"]}},
            "websites": {"google": {"aliases": ["گوگل"]}},
        },
    )
    monkeypatch.setattr(
        main,
        "load_contacts",
        lambda: {
            "Ali": Contact("Ali", "+923001234567", ("Ali Khan", "علی")),
        },
    )

    prompt = main.build_initial_prompt()

    assert all(value in prompt for value in ("chrome", "کروم", "google", "گوگل", "Ali", "علی"))


def test_app_alias_matching_normalizes_urdu_unicode_and_whitespace():
    from assistant.skills.base import resolve_alias

    configured = {"notepad": {"aliases": ["نوٹ پیڈ"], "target": "notepad.exe"}}

    name, details = resolve_alias(configured, "  نوٹ   پیڈ ")

    assert name == "notepad"
    assert details["target"] == "notepad.exe"


def test_contacts_example_has_urdu_aliases():
    from assistant.core.contacts import find_contacts
    from assistant.core.contacts import load_contacts

    example_path = Path(__file__).parents[1] / "assistant" / "config" / "contacts.example.yaml"
    contacts = load_contacts(example_path)

    assert find_contacts("علی", contacts)[0].name == "Ali"


def test_hotkey_registers_only_configured_combo_for_press_and_release():
    keyboard = FakeKeyboard()
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=FakeRecorder(),
        transcriber=None,
        on_command=lambda _: None,
        on_message=lambda _: None,
        keyboard_module=keyboard,
    )

    assert instance.start() is True
    assert len(keyboard.registrations) == 2
    assert all(registration[0] == "ctrl+alt+space" for registration in keyboard.registrations)
    assert keyboard.registrations[0][2]["suppress"] is False
    assert keyboard.registrations[1][2]["trigger_on_release"] is True

    instance.stop()

    assert keyboard.removed == [0, 1]


def test_short_accidental_tap_is_discarded():
    clock_values = iter([1.0, 1.1])
    recorder = FakeRecorder()
    messages = []
    transcriber = types.SimpleNamespace(
        transcribe=lambda _: pytest.fail("short tap must not be transcribed")
    )
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=recorder,
        transcriber=transcriber,
        on_command=lambda _: None,
        on_message=messages.append,
        clock=lambda: next(clock_values),
        worker_factory=lambda callback: callback(),
    )

    instance._on_key_down()
    instance._on_key_up()

    assert recorder.starts == 1
    assert recorder.discards == 1
    assert "didn't hear" in messages[0]


def test_long_hold_is_capped_and_transcribed_once(tmp_path):
    clock_values = iter([0.0, 20.0])
    recorder = FakeRecorder()
    messages = []
    commands = []
    model = FakeModel([FakeSegment("سلام")])
    transcriber = make_transcriber(tmp_path, model)
    timers = []

    def timer_factory(interval, callback):
        timer = FakeTimer(interval, callback)
        timers.append(timer)
        return timer

    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=recorder,
        transcriber=transcriber,
        on_command=commands.append,
        on_message=messages.append,
        max_hold_seconds=20,
        timer_factory=timer_factory,
        worker_factory=lambda callback: callback(),
        clock=lambda: next(clock_values),
    )

    instance._on_key_down()
    timers[0].fire()
    instance._on_key_up()

    assert timers[0].interval == 20
    assert recorder.stops == 1
    assert commands == ["سلام"]


def test_double_press_while_recording_does_not_start_second_recording():
    clock_values = iter([0.0, 0.4])
    recorder = FakeRecorder()
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=recorder,
        transcriber=None,
        on_command=lambda _: None,
        on_message=lambda _: None,
        clock=lambda: next(clock_values),
        worker_factory=lambda callback: None,
    )

    instance._on_key_down()
    instance._on_key_down()
    instance._on_key_up()

    assert recorder.starts == 1
    assert recorder.stops == 1


def test_hotkey_does_not_record_while_tts_is_speaking():
    recorder = FakeRecorder()
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=recorder,
        transcriber=None,
        on_command=lambda _: None,
        on_message=lambda _: None,
        is_speaking=lambda: True,
    )

    instance._on_key_down()

    assert recorder.starts == 0


def test_microphone_unavailable_is_reported_without_crash():
    recorder = FakeRecorder(start_error=MicrophoneUnavailable())
    messages = []
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=recorder,
        transcriber=None,
        on_command=lambda _: None,
        on_message=messages.append,
    )

    instance._on_key_down()

    assert messages == ["I couldn't access a microphone."]


def test_empty_transcript_is_reported_and_not_sent_to_brain():
    messages = []
    commands = []
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=FakeRecorder(),
        transcriber=types.SimpleNamespace(transcribe=lambda _: ""),
        on_command=commands.append,
        on_message=messages.append,
        worker_factory=lambda callback: callback(),
    )

    instance._busy = True
    instance._transcribe_and_dispatch([0.1, -0.1])

    assert messages == ["I didn't hear a command."]
    assert commands == []


def test_transcript_is_shown_and_passed_to_brain_when_configured():
    messages = []
    commands = []
    instance = PushToTalk(
        hotkey="ctrl+alt+space",
        recorder=FakeRecorder(),
        transcriber=types.SimpleNamespace(transcribe=lambda _: "chrome kholo"),
        on_command=commands.append,
        on_message=messages.append,
        show_transcript=True,
    )

    instance._transcribe_and_dispatch([0.1, -0.1])

    assert messages == ["Heard: chrome kholo"]
    assert commands == ["chrome kholo"]


def test_recorded_audio_stays_in_memory(tmp_path, monkeypatch):
    class FakeArray(list):
        def reshape(self, *_):
            return self

    class FakeStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]

        def start(self):
            self.callback([0.1, -0.1], 2, None, None)

        def stop(self):
            return None

        def close(self):
            return None

    fake_numpy = types.SimpleNamespace(
        concatenate=lambda chunks, axis=0: FakeArray(
            sample for chunk in chunks for sample in chunk
        )
    )
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    recorder = MicrophoneRecorder(stream_factory=FakeStream)

    recorder.start()
    audio = recorder.stop()

    assert audio == [0.1, -0.1]
    assert list(tmp_path.iterdir()) == []


def test_typed_input_remains_available(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "type a command")

    assert read_command("ultron") == "type a command"
    monkeypatch.setattr("builtins.input", lambda _: "   ")
    assert read_command("ultron") is None
