import importlib.util
from functools import lru_cache
from typing import Optional

from loguru import logger

from .settings import settings

DEFAULT_NO_SPEECH_THRESHOLD = 0.6
DEFAULT_TEMPERATURE = 0.0


class ASRError(Exception):
    pass


@lru_cache(maxsize=1)
def _load_faster_whisper():
    if importlib.util.find_spec("faster_whisper") is None:
        raise ImportError("faster-whisper not available")
    from faster_whisper import WhisperModel

    model_size = settings.MODEL_SIZE
    logger.info(
        f"Loading faster-whisper model: {model_size} (device={settings.MODEL_DEVICE}, compute_type={settings.COMPUTE_TYPE})"
    )
    model = WhisperModel(model_size, device=settings.MODEL_DEVICE, compute_type=settings.COMPUTE_TYPE)
    return model


@lru_cache(maxsize=1)
def _load_whisper():
    if importlib.util.find_spec("whisper") is None:
        raise ImportError("whisper not available")
    import whisper

    model_size = settings.MODEL_SIZE
    logger.info(f"Loading whisper fallback model: {model_size}")
    return whisper.load_model(model_size, device=settings.MODEL_DEVICE)


def _get_initial_prompt() -> Optional[str]:
    prompt = (settings.INITIAL_PROMPT or "").strip()
    return prompt or None


def transcribe(wav_path: str) -> str:
    prompt = _get_initial_prompt()
    try:
        model = _load_faster_whisper()
        segments, _ = model.transcribe(
            wav_path,
            language="fa",
            beam_size=settings.BEAM_SIZE,
            vad_filter=settings.VAD_FILTER,
            temperature=DEFAULT_TEMPERATURE,
            no_speech_threshold=DEFAULT_NO_SPEECH_THRESHOLD,
            condition_on_previous_text=True,
            initial_prompt=prompt,
        )
        text_parts = [seg.text.strip() for seg in segments]
        return " ".join(text_parts).strip()
    except ImportError as exc:
        logger.warning(f"faster-whisper unavailable, falling back to whisper: {exc}")
    except Exception as exc:
        logger.error(f"faster-whisper failed: {exc}")
    try:
        model = _load_whisper()
        import whisper

        result = model.transcribe(
            wav_path,
            language="fa",
            beam_size=settings.BEAM_SIZE,
            temperature=DEFAULT_TEMPERATURE,
            condition_on_previous_text=True,
            initial_prompt=prompt,
        )
        return result.get("text", "").strip()
    except Exception as exc:
        raise ASRError(f"transcription failed: {exc}")


__all__ = ["transcribe", "ASRError"]
