"""
Ежедневные слова: подбор, отправка (утренняя рассылка и /today).

Каждое слово отправляется ОДНИМ сообщением: аудио-файл с произношением
(.mp3, как файл-документ) и подписью (эмодзи-иллюстрация, слово, перевод,
определение, пример) сразу под ним — тапнул на плеер и услышал, без
отдельной кнопки и отдельного сообщения где-то ещё в чате.

Эмодзи выбирается по смыслу слова (ключевые слова в самом слове и его
определении) — "car" даёт 🚗, "bottle" — 🍾 и т.д., а не случайную
"техническую"/"общую" картинку. Если под слово не нашлось подходящего
правила, используется детерминированный запасной вариант по хэшу id
(одно и то же слово — всегда одно и то же эмодзи).
"""
import asyncio
import hashlib
import logging
import re
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import config
import db
from utils import tts, wordbank

logger = logging.getLogger(__name__)

# Правила подбора эмодзи по ключевым словам: ищем вхождение подстроки в
# "word + definition_en" (в нижнем регистре). Порядок важен — проверяются
# сверху вниз, первое совпадение побеждает, поэтому более конкретные
# правила стоят раньше более общих.
EMOJI_RULES = [
    (["car", "vehicle", "traffic jam", "traffic"], "🚗"),
    (["bottle"], "🍾"),
    (["phone", "telephone", "call "], "📞"),
    (["laptop", "computer", "device", "upgrade", "troubleshoot", "software", "app "], "💻"),
    (["email", "inbox"], "📧"),
    (["document", "paperwork", "contract", "form ", "receipt", "invoice"], "📄"),
    (["book", " read "], "📖"),
    (["coffee", "cafe", "café"], "☕"),
    (["restaurant", "meal", " food", "lunch", "dinner", "grocery"], "🍽️"),
    (["apartment", "accommodation", "landlord", "roommate", " rent", "house", "home "], "🏠"),
    (["hotel"], "🏨"),
    (["plane", "flight", "airport", "board a", "jet lag"], "✈️"),
    (["trip", "travel", "destination", "itinerary", "journey", "tour", "vacation", "culture shock"], "🧳"),
    (["map", "route", "navigate", "corner", "straight ahead", "turn left", "get to"], "🗺️"),
    (["budget", "expense", "afford", "invest", " cost", " pay ", "price", "salary", "bargain", "money", "financ"], "💰"),
    (["bank"], "🏦"),
    (["calendar", "schedule", "agenda", "deadline", "appointment", "punctual"], "📅"),
    (["clock", " time", "delay"], "⏰"),
    (["meeting", "conference"], "🧑‍💼"),
    (["colleague", "collaborate", "coworker", "teamwork", " team", "on the same page"], "🤝"),
    (["boss", "manager", "supervisor", "stakeholder", "chain of command", "delegate a task"], "🧑‍💼"),
    (["doctor", "hospital", "medicine", "prescription", "illness", "recover"], "💊"),
    (["health", "well-being", "well being"], "🩺"),
    (["family", "childhood", "parent", "upbringing", "neighbor"], "👨‍👩‍👧"),
    (["weather"], "⛅"),
    (["shop", "store", "purchase", " buy "], "🛍️"),
    (["key ", "lock", "door"], "🔑"),
    (["idea", "consider", "perspective", "opinion", "believe", "point of view", "assume", "clarify", "elaborate", "emphasize", "justify", "make sense", "off the top of my head"], "💡"),
    (["problem", "issue", "challenge", "difficulty", "struggle", "obstacle", "bottleneck"], "⚠️"),
    (["solve", "solution", "figure out", "troubleshoot"], "🧩"),
    (["goal", "achieve", "accomplish", "milestone", "target"], "🎯"),
    (["progress", "improve", "growth", "development"], "📈"),
    (["promotion", "career", "advance", "performance review", "get up to speed"], "🚀"),
    (["grateful", "relieved", "satisfied", "glad", "worthwhile"], "😊"),
    (["exhaust", "overwhelm", "burnout", "stress"], "😩"),
    (["angry", "frustrat", "annoy"], "😤"),
    (["confiden", "determined", "ambitious", "skillful"], "💪"),
    (["curious", "interested"], "🤔"),
    (["patient", "calm"], "🧘"),
    (["safety", "hazard", "risk", "danger", "protective equipment", "ppe"], "⚠️"),
    (["fire "], "🔥"),
    (["machine", "equipment", "mechanism", "operate a machine", "hydraulic", "gasket", "bearing", "lubrication", "vibration"], "⚙️"),
    (["repair", "maintenance", "replace a part", "malfunction", "breakdown"], "🔧"),
    (["factory", "production", "assembly", "manufactur", "plant "], "🏭"),
    (["quality", "inspect", "defect", "standard", "non-conformance", "near miss", "sanity check"], "✅"),
    (["measure", "gauge", "tolerance", "calibrat", "dimension", "specification"], "📏"),
    (["weld", "fabricat", "machining", "torque", "component"], "🔩"),
    (["supply chain", "vendor", "procurement", "shipment", "warehouse", "inventory", "logistics", "raw material", "freight", "customs clearance", "backorder"], "📦"),
    (["incident report", "report"], "📋"),
    (["data", "analysis", "statistic", "throughput", "yield", "output", "batch", "efficiency", "capacity", "cost-effective"], "📊"),
    (["environment", "sustainab", "eco"], "🌱"),
    (["energy", "electric", "power", "voltage"], "⚡"),
    (["water", "liquid"], "💧"),
    (["material", "corrosion", "wear and tear"], "🧱"),
    (["talk", "speak", "discuss", "conversation", "communicat", "put it into words", "put it another way", "tip of my tongue", "mother tongue"], "💬"),
    (["apologize", "sorry", "amends"], "🙏"),
    (["agree", "negotiate", "agreement", "sign off"], "🤝"),
    (["argue", "disagree", "contradict"], "🗣️"),
    (["blueprint", "technical drawing", "prototype", "schematic", "as-built", "critical path", "change order", "punch list"], "📐"),
    (["shutdown", "downtime"], "🛑"),
    (["hobby", "leisure", "recharge", "relax", "binge-watch", "fresh air"], "🎨"),
    (["chores", "errand", "routine", "habit"], "🗓️"),
    (["workload", "prioritize", "overtime", "day off", "trial run", "moving forward"], "📋"),
    (["motivation", "give it a shot", "step out of your comfort zone", "practice makes perfect"], "🔥"),
    (["community", "diverse", "awareness"], "🌐"),
    (["balance"], "⚖️"),
    (["reliable", "trustworthy", "genuine", "supportive"], "🤝"),
    (["flexible", "adapt", "spontaneous"], "🤸"),
    (["misunderstanding", "torn between", "change my mind", "make up my mind", "rule of thumb", "make a decision"], "🤔"),
    (["reliable connection", "automate", "optimize", "streamline", "implement", "rollout", "downstream", "upstream", "regulation", "compliance", "commissioning", "deliverable", "alignment", "load capacity", "control room", "traceability", "backup system", "onboarding"], "⚙️"),
    (["consistent"], "🔁"),
    (["get along with", "run into", "hang out", "catch up"], "👋"),
    (["look forward to"], "🤗"),
    (["take a break"], "☕"),
    (["get used to"], "🔁"),
    (["run out of"], "📉"),
    (["drop someone off"], "🚗"),
    (["settle down"], "🏡"),
    (["picky", "outgoing", "stubborn", "down to earth"], "🙂"),
    (["seat taken"], "💺"),
    (["kindly", "at your earliest convenience", "could you", "would you mind"], "🙏"),
    (["scale of the project", "field engineer", "handover"], "🏗️"),
]

# Запасной пул — только для тех редких слов, под которые не нашлось ни
# одного правила выше. Выбор детерминированный (по хэшу id), чтобы у
# конкретного слова эмодзи не менялось от раза к разу.
_FALLBACK_GENERAL = ["💬", "🗣️", "🏙️", "👋", "🛍️", "📱", "🎉", "💼", "📅"]
_FALLBACK_TECHNICAL = ["🔧", "⚙️", "🛠️", "🏭", "🔩", "📐", "🧰", "📊", "🔌"]


def _pick_emoji(w: dict) -> str:
    """Подбирает эмодзи, конкретно отражающее смысл слова: сперва ищем
    ключевые слова в самом слове/определении (car → 🚗, bottle → 🍾 и
    т.д.), и только если ничего не подошло — берём запасной вариант
    (для фраз по умолчанию 💬, иначе — по хэшу id, детерминированно)."""
    text = f"{w['word']} {w.get('definition_en', '')}".lower()
    for keywords, emoji in EMOJI_RULES:
        for kw in keywords:
            if kw in text:
                return emoji

    if w.get("pos") == "phrase":
        return "💬"

    pool = _FALLBACK_TECHNICAL if w["_source"] == "technical" else _FALLBACK_GENERAL
    idx = int(hashlib.sha256(w["id"].encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[idx]


def _safe_filename(word: str) -> str:
    """Превращает слово/фразу в безопасное имя файла для .mp3 (без
    пробелов и спецсимволов, которые могут не понравиться некоторым
    клиентам)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", word).strip("_").lower()
    return f"{slug or 'word'}.mp3"


def format_word_caption(w: dict) -> str:
    emoji = _pick_emoji(w)
    tag = "🔧 техническое" if w["_source"] == "technical" else "💬 общее"
    return (
        f"{emoji} <b>{w['word']}</b> <i>({w['pos']})</i> — {w['ru']}\n"
        f"<i>{tag}</i>\n\n"
        f"{w['definition_en']}\n\n"
        f"<i>\"{w['example_en']}\"</i>"
    )


async def send_one_word(bot, chat_id: int, w: dict):
    """Отправляет одно слово ОДНИМ сообщением: аудио-файл с произношением
    (файл-документ, .mp3) и подписью (эмодзи + слово + перевод +
    определение + пример) сразу под ним. Если озвучить не получилось
    (сбой TTS) — отправляем тем же текстом обычным сообщением, чтобы
    слово всё равно дошло."""
    caption = format_word_caption(w)
    try:
        speech_text = f"{w['word']}. {w['word']}. {w['example_en']}"
        audio = tts.synthesize_to_mp3(speech_text)
        await bot.send_document(
            chat_id,
            document=audio,
            filename=_safe_filename(w["word"]),
            caption=caption,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Не удалось озвучить слово %s", w["word"])
        await bot.send_message(chat_id, caption, parse_mode="HTML")


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
