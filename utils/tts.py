"""
Озвучка текста (Text-to-Speech) БЕСПЛАТНО через открытый TTS-сервис
StreamElements (использует живые голоса Amazon Polly, в том числе
приятный женский голос Joanna — без ключа и регистрации). Работает
через обычный HTTP-запрос, поэтому надёжнее, чем протоколы вроде
edge-tts, которые Microsoft периодически меняет и блокирует с облачных
серверов.

Результат конвертируется в .ogg/Opus, чтобы Telegram показывал его
как обычное голосовое сообщение.
"""
import io

import requests

from utils import _compat  # noqa: F401  (должен идти до pydub)
from pydub import AudioSegment

import config

STREAMELEMENTS_TTS_URL = "https://api.streamelements.com/kappa/v2/speech"


def synthesize_to_ogg(text: str) -> bytes:
    """Озвучивает текст голосом config.TTS_VOICE и возвращает байты
    готового .ogg/Opus файла для отправки как голосовое сообщение."""
    response = requests.get(
        STREAMELEMENTS_TTS_URL,
        params={"voice": config.TTS_VOICE, "text": text},
        timeout=20,
    )
    response.raise_for_status()

    mp3_io = io.BytesIO(response.content)
    audio = AudioSegment.from_file(mp3_io, format="mp3")
    ogg_io = io.BytesIO()
    audio.export(ogg_io, format="ogg", codec="libopus")
    ogg_io.seek(0)
    return ogg_io.read()
