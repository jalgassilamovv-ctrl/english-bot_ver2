"""
Озвучка текста (Text-to-Speech) БЕСПЛАТНО через gTTS — официальный
публичный сервис Google Translate, без ключа и регистрации. Самый
надёжный из бесплатных вариантов: более "живые" нейросетевые голоса
(edge-tts, StreamElements) на практике оказались нестабильны при
запросах с облачных серверов — периодически ломаются или требуют
авторизацию, которой раньше не требовали.

Результат конвертируется в .ogg/Opus, чтобы Telegram показывал его
как обычное голосовое сообщение.
"""
import io

from gtts import gTTS

from utils import _compat  # noqa: F401  (должен идти до pydub)
from pydub import AudioSegment

import config


def synthesize_to_ogg(text: str) -> bytes:
    """Озвучивает текст и возвращает байты готового .ogg/Opus файла
    для отправки как голосовое сообщение (send_voice) — используется там,
    где сообщение одно и "цепное" автовоспроизведение Telegram не мешает
    (/pronounce, ответ в /talk)."""
    mp3_io = io.BytesIO()
    speech = gTTS(text=text, lang=config.TTS_LANG, tld=config.TTS_TLD)
    speech.write_to_fp(mp3_io)
    mp3_io.seek(0)

    audio = AudioSegment.from_file(mp3_io, format="mp3")
    ogg_io = io.BytesIO()
    audio.export(ogg_io, format="ogg", codec="libopus")
    ogg_io.seek(0)
    return ogg_io.read()


def synthesize_to_mp3(text: str) -> bytes:
    """Озвучивает текст и возвращает байты MP3 напрямую от gTTS (без
    конвертации в ogg/opus). Используется для отправки как обычный
    аудио-файл (send_audio), а не голосовое сообщение (send_voice): у
    "войсов" и кружочков в Telegram есть встроенное цепное
    автовоспроизведение подряд идущих сообщений — заканчивается одно,
    сразу включается следующее. Обычные аудио-файлы (с плеером-треком)
    так не цепляются друг за друга, поэтому для ежедневной рассылки, где
    слова идут одно за другим, нужен именно этот формат."""
    mp3_io = io.BytesIO()
    speech = gTTS(text=text, lang=config.TTS_LANG, tld=config.TTS_TLD)
    speech.write_to_fp(mp3_io)
    mp3_io.seek(0)
    return mp3_io.read()
