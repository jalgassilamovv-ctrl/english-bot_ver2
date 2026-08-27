"""
Ежедневные слова: подбор, отправка (утренняя рассылка и /today).

Каждое слово отправляется ОТДЕЛЬНЫМ сообщением: картинка-иллюстрация с
подписью (слово, перевод, определение, пример) + следом короткое голосовое
произношение именно этого слова. Так проще запоминать и не путать слова
между собой (в отличие от одной общей звуковой дорожки на все слова сразу).
"""
import asyncio
import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import config
import db
from utils import image as image_utils
from utils import tts, wordbank

logger = logging.getLogger(__name__)


def format_word_caption(w: dict) -> str:
    tag = "🔧" if w["_source"] == "technical" else "💬"
    return (
        f"{tag} <b>{w['word']}</b> <i>({w['pos']})</i> — {w['ru']}\n\n"
        f"{w['definition_en']}\n\n"
        f"<i>\"{w['example_en']}\"</i>"
    )


async def send_one_word(bot, chat_id: int, w: dict):
    """Отправляет одно слово: картинка+подпись, затем голосовое произношение."""
    caption = format_word_caption(w)
    photo_bytes = None
    try:
        photo_bytes = image_utils.generate_word_image(w)
    except Exception:
        logger.exception("Ошибка при генерации картинки для %s", w["word"])

    if photo_bytes:
        try:
            await bot.send_photo(chat_id, photo_bytes, caption=caption, parse_mode="HTML")
        except Exception:
            logger.exception("Не удалось отправить картинку для %s, шлю текстом", w["word"])
            await bot.send_message(chat_id, caption, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, caption, parse_mode="HTML")

    try:
        speech_text = f"{w['word']}. {w['word']}. {w['example_en']}"
        audio = tts.synthesize_to_ogg(speech_text)
        await bot.send_voice(chat_id, audio)
    except Exception:
        logger.exception("Не удалось озвучить слово %s", w["word"])


async def send_daily_words(bot, chat_id: int, prepend: str = None):
    """Подбирает новую порцию слов, сохраняет в БД и отправляет по одному."""
    known_ids = db.get_known_word_ids(chat_id)
    words = wordbank.pick_daily_words(known_ids, config.NEW_WORDS_PER_DAY, config.TECHNICAL_SHARE)

    if not words:
        await bot.send_message(
            chat_id,
            "🎉 Ты изучил все слова из моей базы! Напиши мне, и я подскажу, "
            "как расширить словарную базу дальше.",
        )
        return

    db.add_words_to_progress(chat_id, words)
    db.log_new_words_sent(chat_id, len(words))
    db.promote_new_to_learning(chat_id, [w["id"] for w in words])

    header = f"📚 <b>Твои {len(words)} новых слов на сегодня</b> (🔧 техническое · 💬 общее)"
    if prepend:
        header = prepend + "\n\n" + header
    await bot.send_message(chat_id, header, parse_mode="HTML")

    for i, w in enumerate(words):
        await send_one_word(bot, chat_id, w)
        if i < len(words) - 1:
            await asyncio.sleep(config.WORD_SEND_DELAY_SECONDS)

    await bot.send_message(
        chat_id,
        "Совет: пройди /quiz сегодня вечером, чтобы слова закрепились в памяти. "
        "Хочешь ещё раз услышать произношение — напиши /pronounce и слово.",
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db.touch_activity(chat_id)
    today_ids = db.get_words_added_on(chat_id, date.today().isoformat())
    if not today_ids:
        await update.message.reply_text(
            "На сегодня слова ещё не были присланы — отправляю подборку прямо сейчас!"
        )
        await send_daily_words(context.bot, chat_id)
        return
    words = [wordbank.get_word_by_id(wid) for wid in today_ids]
    words = [w for w in words if w]
    await update.message.reply_text(f"📚 <b>Слова, которые ты уже получил сегодня ({len(words)})</b>", parse_mode="HTML")
    for i, w in enumerate(words):
        await send_one_word(context.bot, chat_id, w)
        if i < len(words) - 1:
            await asyncio.sleep(config.WORD_SEND_DELAY_SECONDS)
