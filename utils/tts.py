"""
Озвучка текста (Text-to-Speech) БЕСПЛАТНЫМ способом через edge-tts —
использует те же живые нейросетевые голоса, что в Microsoft Edge
(без API-ключа, без регистрации). По умолчанию используется приятный
женский голос en-US-JennyNeural (см. config.TTS_VOICE).
Результат конвертируется в .ogg/Opus, чтобы Telegram показывал его
как обычное голосовое сообщение.
"""
import io

from utils import _compat  # noqa: F401  (должен идти до pydub)

import edge_tts
from pydub import AudioSegment

import config


async def synthesize_to_ogg(text: str) -> bytes:
    """Асинхронно озвучивает текст голосом config.TTS_VOICE и возвращает
    байты готового .ogg/Opus файла для отправки как голосовое сообщение."""
    communicate = edge_tts.Communicate(text, voice=config.TTS_VOICE)
    mp3_chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_chunks.extend(chunk["data"])

    mp3_io = io.BytesIO(bytes(mp3_chunks))
    audio = AudioSegment.from_file(mp3_io, format="mp3")
    ogg_io = io.BytesIO()
    audio.export(ogg_io, format="ogg", codec="libopus")
    ogg_io.seek(0)
    return ogg_io.read()
