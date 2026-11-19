import math
from pathlib import Path
from typing import Any, Callable


class MicrophoneUnavailable(Exception):
    pass


class SpeechModelUnavailable(Exception):
    pass


def audio_rms(audio: Any) -> float:
    if hasattr(audio, "flatten"):
        samples = audio.flatten()
    else:
        samples = audio
    try:
        values = [float(sample) for sample in samples]
    except TypeError:
        values = [float(samples)]
    if not values:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in values) / len(values))


class MicrophoneRecorder:
    def __init__(
        self,
        device: int | str | None = None,
        sample_rate: int = 16000,
        channels: int = 1,
        stream_factory: Callable[..., Any] | None = None,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.stream_factory = stream_factory
        self._stream_error_types = (OSError, RuntimeError)
        self._stream = None
        self._chunks = []

    def start(self) -> None:
        if self._stream is not None:
            return
        if self.stream_factory is None:
            try:
                import sounddevice
            except ImportError as error:
                raise MicrophoneUnavailable("I couldn't access a microphone.") from error
            self.stream_factory = sounddevice.InputStream
            self._stream_error_types += (sounddevice.PortAudioError,)

        self._chunks = []

        def capture(indata, frames, time_info, status):
            self._chunks.append(indata.copy())

        try:
            self._stream = self.stream_factory(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                device=self.device,
                callback=capture,
            )
            self._stream.start()
        except self._stream_error_types as error:
            self._stream = None
            raise MicrophoneUnavailable("I couldn't access a microphone.") from error

    def stop(self):
        if self._stream is None:
            return None

        stream = self._stream
        self._stream = None
        try:
            stream.stop()
            stream.close()
        except self._stream_error_types as error:
            raise MicrophoneUnavailable("I couldn't access a microphone.") from error
        if not self._chunks:
            return None

        import numpy

        audio = numpy.concatenate(self._chunks, axis=0)
        self._chunks = []
        return audio.reshape(-1)

    def discard(self) -> None:
        if self._stream is not None:
            stream = self._stream
            self._stream = None
            stream.stop()
            stream.close()
        self._chunks = []


class SpeechTranscriber:
    def __init__(
        self,
        model_name: str = "small",
        language: str = "ur",
        initial_prompt: str = "",
        model_directory: Path | None = None,
        compute_type: str = "int8",
        silence_rms_threshold: float = 0.005,
        no_speech_prob_threshold: float = 0.6,
        model_factory: Callable[..., Any] | None = None,
        download_model: Callable[[str, Path], None] | None = None,
    ):
        if language not in {"auto", "en", "ur"}:
            raise ValueError("STT language must be 'auto', 'en', or 'ur'.")
        self.model_name = model_name
        self.language = language
        self.initial_prompt = initial_prompt
        self.model_directory = model_directory
        self.compute_type = compute_type
        self.silence_rms_threshold = silence_rms_threshold
        self.no_speech_prob_threshold = no_speech_prob_threshold
        self.model_factory = model_factory
        self.download_model = download_model
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        if self.model_directory is None:
            raise SpeechModelUnavailable("The speech model isn't downloaded.")

        model_directory = Path(self.model_directory)
        if not (model_directory / "config.json").is_file():
            download_errors = [ImportError, OSError, RuntimeError, ValueError]
            if self.download_model is None:
                try:
                    from huggingface_hub.errors import HfHubError
                except ImportError as error:
                    raise SpeechModelUnavailable(
                        "The speech model isn't downloaded."
                    ) from error
                download_errors.append(HfHubError)
            try:
                downloader = self.download_model or self._download_model
                downloader(self.model_name, model_directory)
            except tuple(download_errors) as error:
                raise SpeechModelUnavailable("The speech model isn't downloaded.") from error
        if not (model_directory / "config.json").is_file():
            raise SpeechModelUnavailable("The speech model isn't downloaded.")

        try:
            factory = self.model_factory or self._create_model_factory()
            self._model = factory(
                str(model_directory),
                device="cpu",
                compute_type=self.compute_type,
            )
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            raise SpeechModelUnavailable("The speech model isn't downloaded.") from error
        return self._model

    @staticmethod
    def _download_model(model_name: str, model_directory: Path) -> None:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=f"Systran/faster-whisper-{model_name}",
            local_dir=str(model_directory),
        )

    @staticmethod
    def _create_model_factory():
        from faster_whisper import WhisperModel

        return WhisperModel

    def transcribe(self, audio) -> str:
        if audio is None or audio_rms(audio) < self.silence_rms_threshold:
            return ""

        model = self._load_model()
        language = None if self.language == "auto" else self.language
        segments, _ = model.transcribe(
            audio,
            language=language,
            initial_prompt=self.initial_prompt or None,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        valid_segments = [
            segment
            for segment in segments
            if segment.text.strip()
            and segment.no_speech_prob <= self.no_speech_prob_threshold
        ]
        return " ".join(segment.text.strip() for segment in valid_segments).strip()
