"""
Ежедневные слова: подбор, отправка (утренняя рассылка и /today).

Каждое слово отправляется ОТДЕЛЬНЫМ сообщением: эмодзи-иллюстрация +
подпись (слово, перевод, определение, пример) и кнопка "Слушать
произношение" под ним. Эмодзи выбирается детерминированно по слову (одно
и то же слово — всегда одно и то же эмодзи), без обращения к сторонним
сервисам генерации картинок — те оказались слишком медленными и
ненадёжными на бесплатном хостинге, а эмодзи работает мгновенно и
никогда не ломается.
"""
import asyncio
import hashlib
import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config
import db
from utils import tts, wordbank

logger = logging.getLogger(__name__)

GENERAL_EMOJIS = [
    "💬", "🗣️", "☕", "🏙️", "👋", "🛍️", "📱", "🎉",
    "🚗", "🏠", "🍽️", "✈️", "💼", "📅", "🤝",
]
TECHNICAL_EMOJIS = [
    "🔧", "⚙️", "🛠️", "🏭", "🔩", "📐", "🧰", "⚡",
    "🔬", "📊", "🚧", "🦺", "📦", "🧯", "🔌",
]


def _pick_emoji(w: dict) -> str:
    """Детерминированно выбирает эмодзи-иллюстрацию для слова (по хэшу id),
    чтобы у одного и того же слова оно всегда было одинаковым, а слова между
    собой выглядели разнообразно."""
    pool = TECHNICAL_EMOJIS if w["_source"] == "technical" else GENERAL_EMOJIS
    idx = int(hashlib.sha256(w["id"].encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[idx]


def format_word_caption(w: dict) -> str:
    emoji = _pick_emoji(w)
    tag = "🔧 техническое" if w["_source"] == "technical" else "💬 общее"
    return (
        f"{emoji} <b>{w['word']}</b> <i>({w['pos']})</i> — {w['ru']}\n"
        f"<i>{tag}</i>\n\n"
        f"{w['definition_en']}\n\n"
        f"<i>\"{w['example_en']}\"</i>"
    )


def _voice_button(word_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔊 Слушать произношение", callback_data=f"voice:{word_id}")]]
    )


async def send_one_word(bot, chat_id: int, w: dict):
    """Отправляет одно слово: эмодзи+подпись с кнопкой "Слушать произношение"
    под НИМ ЖЕ (у каждого слова — своя кнопка). Голос отправляется не
    автоматически, а только когда пользователь сам нажмёт на кнопку под
    нужным словом."""
    caption = format_word_caption(w)
    markup = _voice_button(w["id"])
    await bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)


async def handle_word_voice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Срабатывает по нажатию на кнопку "🔊 Слушать произношение" под словом —
    озвучивает именно это слово, по требованию, а не автоматически."""
    query = update.callback_query
    word_id = query.data.split(":", 1)[1]
    w = wordbank.get_word_by_id(word_id)
    if not w:
        await query.answer("Не нашёл это слово 🤔", show_alert=True)
        return

    await query.answer("🎧 Готовлю произношение...")
    try:
        speech_text = f"{w['word']}. {w['word']}. {w['example_en']}"
        audio = tts.synthesize_to_ogg(speech_text)
        # Отправляем голосовое как ОТВЕТ на сообщение с этим словом — так
        # в чате видно, к какому именно слову оно относится, даже если
        # рассылка успела уйти далеко вниз, и можно тапнуть на цитату,
        # чтобы вернуться к нужному слову, не листая вручную.
        await context.bot.send_voice(
            query.message.chat_id,
            audio,
            reply_to_message_id=query.message.message_id,
        )
    except Exception:
        logger.exception("Не удалось озвучить слово %s", w["word"])
        await context.bot.send_message(
            query.message.chat_id,
            "Не получилось озвучить слово, попробуй ещё раз чуть позже.",
            reply_to_message_id=query.message.message_id,
        )


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
