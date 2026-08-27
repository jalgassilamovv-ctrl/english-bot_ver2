"""
Генерация картинки-иллюстрации к слову — БЕСПЛАТНО, без API-ключа, через
публичный сервис Pollinations.ai (image.pollinations.ai). Это сторонний
бесплатный сервис "как есть": иногда может отвечать медленно или быть
временно недоступным. Поэтому вызовы обёрнуты так, чтобы при любой ошибке
или таймауте бот просто пропускал картинку, не ломая отправку слова.

Если в будущем захочешь более стабильное и качественное решение — можно
заменить этот модуль вызовом платного API (например, OpenAI Images) —
остальной код бота трогать не придётся, он ждёт от этой функции просто
байты картинки или None.
"""
import hashlib
import logging
import urllib.parse

import requests

import config

logger = logging.getLogger(__name__)


def _seed_for(word_id: str) -> int:
    """Детерминированный seed по id слова, чтобы при повторной генерации
    (например, через /today) картинка была той же, а не случайной каждый раз."""
    digest = hashlib.sha256(word_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 1_000_000


def generate_word_image(word: dict) -> bytes | None:
    if not config.ENABLE_WORD_IMAGES:
        return None

    prompt = (
        f"simple clean flat illustration representing the word '{word['word']}' "
        f"({word['definition_en']}), minimalist icon style, no text, no letters, "
        f"plain background"
    )
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"{config.IMAGE_GENERATION_URL}/{encoded_prompt}"
    params = {
        "width": 512,
        "height": 512,
        "nologo": "true",
        "seed": _seed_for(word["id"]),
    }

    try:
        response = requests.get(url, params=params, timeout=config.IMAGE_TIMEOUT_SECONDS)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type:
            logger.warning("Сервис картинок вернул не изображение для %s", word["word"])
            return None
        return response.content
    except Exception:
        logger.warning("Не удалось сгенерировать картинку для слова %s", word["word"])
        return None
