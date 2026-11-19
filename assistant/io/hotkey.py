import threading
import time
from typing import Any, Callable

from assistant.io.stt import MicrophoneUnavailable, SpeechModelUnavailable


def _start_worker(callback: Callable[[], None]) -> None:
    threading.Thread(target=callback, daemon=True).start()


class PushToTalk:
    def __init__(
        self,
        hotkey: str,
        recorder,
        transcriber,
        on_command: Callable[[str], None],
        on_message: Callable[[str], None],
        show_transcript: bool = True,
        max_hold_seconds: float = 20,
        min_hold_seconds: float = 0.25,
        is_speaking: Callable[[], bool] = lambda: False,
        keyboard_module: Any = None,
        timer_factory: Callable[..., Any] = threading.Timer,
        worker_factory: Callable[[Callable[[], None]], None] = _start_worker,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.hotkey = hotkey
        self.recorder = recorder
        self.transcriber = transcriber
        self.on_command = on_command
        self.on_message = on_message
        self.show_transcript = show_transcript
        self.max_hold_seconds = max_hold_seconds
        self.min_hold_seconds = min_hold_seconds
        self.is_speaking = is_speaking
        self.keyboard_module = keyboard_module
        self.timer_factory = timer_factory
        self.worker_factory = worker_factory
        self.clock = clock
        self._lock = threading.Lock()
        self._recording = False
        self._busy = False
        self._pressed_at = 0.0
        self._timer = None
        self._hotkey_handles = []

    def start(self) -> bool:
        if self.keyboard_module is None:
            try:
                import keyboard
            except ImportError:
                self.on_message("Push-to-talk is unavailable; you can type commands instead.")
                return False
            self.keyboard_module = keyboard

        try:
            self._hotkey_handles.append(
                self.keyboard_module.add_hotkey(
                    self.hotkey,
                    self._on_key_down,
                    suppress=False,
                )
            )
            self._hotkey_handles.append(
                self.keyboard_module.add_hotkey(
                    self.hotkey,
                    self._on_key_up,
                    suppress=False,
                    trigger_on_release=True,
                )
            )
        except (OSError, RuntimeError, ValueError):
            for handle in self._hotkey_handles:
                self.keyboard_module.remove_hotkey(handle)
            self._hotkey_handles = []
            self.on_message("Push-to-talk is unavailable; you can type commands instead.")
            return False
        return True

    def stop(self) -> None:
        if self.keyboard_module is not None:
            for handle in self._hotkey_handles:
                self.keyboard_module.remove_hotkey(handle)
        self._hotkey_handles = []
        with self._lock:
            was_recording = self._recording
            self._recording = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if was_recording:
            self.recorder.discard()

    def _on_key_down(self) -> None:
        if self.is_speaking():
            return
        with self._lock:
            if self._recording or self._busy:
                return
            self._recording = True
            self._pressed_at = self.clock()
            try:
                self.recorder.start()
            except MicrophoneUnavailable:
                self._recording = False
                self.on_message("I couldn't access a microphone.")
                return
            self._timer = self.timer_factory(
                self.max_hold_seconds,
                self._finish_recording,
            )
            self._timer.daemon = True
            self._timer.start()

    def _on_key_up(self) -> None:
        self._finish_recording()

    def _finish_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            duration = self.clock() - self._pressed_at
            self._recording = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if duration < self.min_hold_seconds:
                self.recorder.discard()
                self.on_message("I didn't hear a command.")
                return
            try:
                audio = self.recorder.stop()
            except MicrophoneUnavailable:
                self.on_message("I couldn't access a microphone.")
                return
            self._busy = True

        self.worker_factory(lambda: self._transcribe_and_dispatch(audio))

    def _transcribe_and_dispatch(self, audio) -> None:
        try:
            if audio is None:
                self.on_message("I didn't hear a command.")
                return
            transcript = self.transcriber.transcribe(audio)
            if not transcript:
                self.on_message("I didn't hear a command.")
                return
            if self.show_transcript:
                self.on_message(f"Heard: {transcript}")
            self.on_command(transcript)
        except SpeechModelUnavailable:
            self.on_message("The speech model isn't downloaded.")
        except MicrophoneUnavailable:
            self.on_message("I couldn't access a microphone.")
        finally:
            with self._lock:
                self._busy = False
