
import os
import json
import random
import requests
import threading
import asyncio
import re
import fcntl
import time
import math
import logging

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)


# ==========================================
# CONFIGURATION
# ==========================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

MODEL_NAME = "openrouter/free"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

MEMORY_FILE = "johnny_memory.json"
PORT = int(os.environ.get("PORT", 10000))

MAX_HISTORY = 20
MAX_MESSAGE_LENGTH = 3900
MAX_RETRIES = 3

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

if not OPENROUTER:
    raise RuntimeError("OPENROUTER_API_KEY is missing")


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("JOHNNY")


# ==========================================
# SINGLE INSTANCE PROTECTION
# ==========================================

lock_file = open("/tmp/johnny_bot.lock", "w")

try:
    fcntl.flock(
        lock_file,
        fcntl.LOCK_EX | fcntl.LOCK_NB
    )
except BlockingIOError:
    raise RuntimeError("Johnny is already running")


# ==========================================
# JOHNNY PERSONALITY
# ==========================================

SYSTEM = """Ты — Джонни Сильверхенд из Cyberpunk 2077.

ТВОЯ ЛИЧНОСТЬ:

Ты рокер, бунтарь, анархист и бывший участник группы Samurai.
Самоуверенный, циничный, вспыльчивый, саркастичный и независимый.
У тебя острый язык, огромное эго и презрение к корпорациям.

Ты не пытаешься понравиться каждому.
Не поддакиваешь собеседнику.
Если он неправ — споришь.
Если говорит глупость — подкалываешь.
У тебя собственное мнение.

МАНЕРА РЕЧИ:

- Разговаривай как обычный живой человек.
- Предпочитай короткие и средние ответы.
- Не растягивай простые ответы в огромные монологи.
- Не используй пафосные метафоры.
- Используй сарказм и иронию, когда уместно.
- Иногда называй собеседника чумбой или самураем.
- Не повторяй одни и те же приветствия.
- Не превращай каждую тему в разговор о Найт-Сити.
- Не заканчивай каждый ответ риторическим вопросом.
- Сохраняй естественную разговорную манеру речи.

ФОРМАТ:

- Только обычный текст.
- Никакого Markdown.
- Не используй жирный шрифт и декоративное форматирование.
- Не добавляй бессмысленные вступления.
- Не пересказывай вопрос пользователя.

ЗНАНИЕ ВСЕЛЕННОЙ:

- Опирайся на реальные события Cyberpunk 2077 и Cyberpunk 2020.
- Не придумывай воспоминания, знакомства и события.
- Не выдавай предположения за факты.
- Если чего-то не знаешь, прямо скажи об этом.

ОТНОШЕНИЕ:

Ты воспринимаешь собеседника как отдельную личность.
Можешь дружить, спорить, шутить и подкалывать.
Не превращайся в послушного помощника.
Не изображай постоянную агрессию.

ВАЖНО:

- Текущий язык общения определяется отдельной инструкцией ниже.
- Строго соблюдай выбранный язык.
- Не смешивай русский и английский.
- Не используй китайские иероглифы.
- Имена персонажей, игр и организаций оставляй в оригинале.
- Если пользователь переключает язык, сразу переходи на него.

Ты Джонни Сильверхенд.
Просто разговаривай.
"""


# ==========================================
# LANGUAGE SYSTEM
# ==========================================

LANGUAGE_RUSSIAN = "ru"
LANGUAGE_ENGLISH = "en"

LANGUAGE_INSTRUCTIONS = {

    "ru": """
ТЕКУЩИЙ ЯЗЫК: РУССКИЙ.

Всегда отвечай исключительно на русском языке.
Используй естественный разговорный русский.
Не вставляй случайные английские слова.
Сохраняй сарказм, характер и манеру Джонни.
""",

    "en": """
CURRENT LANGUAGE: ENGLISH.

Always communicate exclusively in English.
Use natural, fluent, conversational English.
Never randomly insert Russian words or sentences.
Maintain Johnny Silverhand's personality, sarcasm,
rebellious attitude, dark humor and characteristic slang.

Use natural expressions such as "chum", "samurai"
and other fitting Cyberpunk-style slang when appropriate.

Do not translate Russian expressions literally.
Speak like a native English-speaking Johnny Silverhand.
"""
}


LANGUAGE_PATTERNS = {

    "ru": [
        r"говори по-русски",
        r"говори на русском",
        r"переключись на русский",
        r"перейди на русский",
        r"давай на русском",
        r"пиши на русском",
        r"верни русский",
        r"switch to russian",
        r"speak russian",
        r"reply in russian"
    ],

    "en": [
        r"говори по-английски",
        r"говори на английском",
        r"переключись на английский",
        r"перейди на английский",
        r"давай на английском",
        r"пиши на английском",
        r"switch to english",
        r"speak english",
        r"reply in english",
        r"english please"
    ]
}


def get_language(user_id):

    user_id = str(user_id)

    with memory_lock:

        return user_languages.get(
            user_id,
            LANGUAGE_RUSSIAN
        )


def set_language(user_id, language):

    user_id = str(user_id)

    if language not in ("ru", "en"):
        return

    with memory_lock:

        user_languages[user_id] = language

        save_memory()

    logger.info(
        "Language changed for user %s: %s",
        user_id,
        language
    )


def detect_language_request(text):

    text = text.lower().strip()

    for language, patterns in LANGUAGE_PATTERNS.items():

        for pattern in patterns:

            if re.search(pattern, text):
                return language

    return None


# ==========================================
# MOOD SYSTEM
# ==========================================

MOODS = [
    "Сегодня ты особенно саркастичен и язвителен.",
    "Сегодня ты спокоен, но сохраняешь циничный характер.",
    "Сегодня ты раздражён и легко подкалываешь собеседника.",
    "Сегодня ты в хорошем настроении и более разговорчив.",
    "Сегодня ты задумчив и временами философствуешь."
]

MOOD_CHANGE_CHANCE = 0.08


START_PHRASES = {
    "ru": [
        "Проснись, самурай! Легенда вернулась. Чего надо?",
        "О, опять ты. Ну, выкладывай.",
        "Связь установлена. Джонни на месте.",
        "Ну здравствуй. Что на этот раз?",
        "Самурай, ты вовремя. Скука уже убивала."
    ],

    "en": [
        "Wake the fuck up, samurai! The legend is back. What's up?",
        "Oh, it's you again. Go on, I'm listening.",
        "Connection established. Johnny's here.",
        "Well, hello there. What is it this time?",
        "You're right on time, samurai. I was getting bored."
    ]
}


HELP_TEXT = {

    "ru": """Команды Джонни:

/start — разбудить Джонни
/help — список команд
/clear — очистить историю
/about — кто такой Джонни
/model — используемая модель
/language ru — русский язык
/language en — английский язык

Также можно попросить меня переключить язык обычным сообщением.""",

    "en": """Johnny's commands:

/start — wake Johnny up
/help — show commands
/clear — clear conversation history
/about — about Johnny
/model — current AI model
/language ru — switch to Russian
/language en — switch to English

You can also ask me to change languages naturally."""
}


ABOUT_TEXT = {

    "ru": """Джонни Сильверхенд.
Рокер, бунтарь и бывший участник Samurai.
Создан на базе ИИ через OpenRouter.
Работает на бесплатной модели.""",

    "en": """Johnny Silverhand.
Rocker, rebel and former member of Samurai.
Powered by AI through OpenRouter.
Currently running on a free model."""
}


# ==========================================
# MEMORY
# ==========================================

conversations = {}
user_moods = {}
user_languages = {}

memory_lock = threading.RLock()

user_locks = {}
user_locks_guard = threading.Lock()


def get_user_lock(user_id):

    with user_locks_guard:

        if user_id not in user_locks:
            user_locks[user_id] = threading.Lock()

        return user_locks[user_id]


def load_memory():

    global conversations, user_moods, user_languages

    if not os.path.exists(MEMORY_FILE):
        logger.info("No previous memory found")
        return

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Invalid memory structure")

        raw_conversations = data.get("conversations", {})
        raw_moods = data.get("moods", {})
        raw_languages = data.get("languages", {})

        if not isinstance(raw_conversations, dict):
            raw_conversations = {}

        if not isinstance(raw_moods, dict):
            raw_moods = {}

        if not isinstance(raw_languages, dict):
            raw_languages = {}

        conversations = {}

        for user_id, history in raw_conversations.items():

            if not isinstance(history, list):
                continue

            valid_history = []

            for message in history:

                if not isinstance(message, dict):
                    continue

                role = message.get("role")
                content = message.get("content")

                if role not in ("user", "assistant"):
                    continue

                if not isinstance(content, str):
                    continue

                valid_history.append({
                    "role": role,
                    "content": content
                })

            conversations[str(user_id)] = valid_history[-MAX_HISTORY:]

        user_moods = {
            str(user_id): mood
            for user_id, mood in raw_moods.items()
            if isinstance(mood, str)
        }

        user_languages = {
            str(user_id): language
            for user_id, language in raw_languages.items()
            if language in ("ru", "en")
        }

        logger.info("JOHNNY MEMORY LOADED")

    except Exception:

        logger.exception("MEMORY LOAD ERROR")


def save_memory():

    try:

        with memory_lock:

            data = {
                "conversations": conversations,
                "moods": user_moods,
                "languages": user_languages
            }

            temp_file = MEMORY_FILE + ".tmp"

            with open(
                temp_file,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

                file.flush()
                os.fsync(file.fileno())

            os.replace(
                temp_file,
                MEMORY_FILE
            )

    except Exception:

        logger.exception("MEMORY SAVE ERROR")


# ==========================================
# MOOD MANAGEMENT
# ==========================================

def get_mood(user_id):

    user_id = str(user_id)

    with memory_lock:

        if user_id not in user_moods:

            user_moods[user_id] = random.choice(MOODS)

            save_memory()

        return user_moods[user_id]


def update_mood(user_id):

    user_id = str(user_id)

    with memory_lock:

        current_mood = get_mood(user_id)

        if random.random() < MOOD_CHANGE_CHANCE:

            available_moods = [
                mood for mood in MOODS
                if mood != current_mood
            ]

            user_moods[user_id] = random.choice(
                available_moods
            )

            save_memory()

            logger.info(
                "Mood changed for user %s",
                user_id
            )

        return user_moods[user_id]


# ==========================================
# RATE LIMIT HANDLING
# ==========================================

class OpenRouterRateLimitError(Exception):

    def __init__(self, reset_timestamp=None):

        self.reset_timestamp = reset_timestamp

        super().__init__(
            "OpenRouter rate limit exceeded"
        )


def get_rate_limit_reset(response):

    reset_value = response.headers.get(
        "X-RateLimit-Reset"
    )

    if not reset_value:

        try:

            error_data = response.json()

            metadata = error_data.get(
                "error", {}
            ).get("metadata", {})

            headers = metadata.get("headers", {})

            reset_value = (
                headers.get("X-RateLimit-Reset")
                or headers.get("x-ratelimit-reset")
            )

        except Exception:
            pass

    if not reset_value:
        return None

    try:

        timestamp = float(reset_value)

        if timestamp > 10000000000:
            timestamp /= 1000

        return timestamp

    except (ValueError, TypeError):
        return None


def format_wait_time(reset_timestamp, language="ru"):

    if not reset_timestamp:

        if language == "en":
            return (
                "The exact reset time is unknown. "
                "Try again later, samurai."
            )

        return (
            "Точное время сброса неизвестно. "
            "Попробуй немного позже, чумба."
        )

    seconds_left = math.ceil(
        reset_timestamp - time.time()
    )

    if seconds_left <= 0:

        if language == "en":
            return (
                "The limit should have reset by now. "
                "Try again, samurai."
            )

        return (
            "Лимит должен был уже сброситься. "
            "Попробуй ещё раз, чумба."
        )

    hours = seconds_left // 3600
    minutes = (seconds_left % 3600) // 60

    if language == "en":

        if hours > 0:
            wait = f"{hours} h."

            if minutes > 0:
                wait += f" {minutes} min."

        elif minutes > 0:
            wait = f"{minutes} min."

        else:
            wait = f"{seconds_left} sec."

        return (
            f"The daily AI limit is exhausted, chum. "
            f"Time until reset: {wait}. "
            f"Hang in there, samurai."
        )

    if hours > 0:

        wait = f"{hours} ч."

        if minutes > 0:
            wait += f" {minutes} мин."

    elif minutes > 0:

        wait = f"{minutes} мин."

    else:

        wait = f"{seconds_left} сек."

    return (
        f"Дневной лимит ИИ исчерпан, чумба. "
        f"До следующего сброса осталось: {wait}. "
        f"Потерпи, самурай."
    )


# ==========================================
# RESPONSE CLEANER
# ==========================================

def clean_answer(answer):

    if not isinstance(answer, str):
        raise ValueError("Invalid AI response")

    answer = re.sub(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
        "",
        answer
    )

    answer = re.sub(
        r"[\u200b-\u200f\u202a-\u202e\ufeff]",
        "",
        answer
    )

    answer = re.sub(
        r"\n{3,}",
        "\n\n",
        answer
    )

    return answer.strip()


# ==========================================
# OPENROUTER API
# ==========================================

def ask_ai(user_id, text):

    user_id = str(user_id)

    headers = {
        "Authorization": f"Bearer {OPENROUTER}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Johnny Bot"
    }

    with get_user_lock(user_id):

        language = get_language(user_id)

        with memory_lock:

            history = conversations.setdefault(
                user_id,
                []
            )

            history = history[-MAX_HISTORY:]

            mood = update_mood(user_id)

            messages = [
                {
                    "role": "system",
                    "content": (
                        SYSTEM
                        + "\n\nТВОЁ НАСТРОЕНИЕ:\n"
                        + mood
                        + "\n\n"
                        + LANGUAGE_INSTRUCTIONS[language]
                    )
                },
                *history,
                {
                    "role": "user",
                    "content": text
                }
            ]

        payload = {
            "model": MODEL_NAME,
            "messages": messages
        }

        response = None

        for attempt in range(MAX_RETRIES):

            try:

                response = requests.post(
                    API_URL,
                    headers=headers,
                    json=payload,
                    timeout=(20, 90)
                )

                if response.status_code == 429:

                    raise OpenRouterRateLimitError(
                        get_rate_limit_reset(response)
                    )

                if response.status_code in (
                    500, 502, 503, 504
                ):

                    if attempt < MAX_RETRIES - 1:

                        logger.warning(
                            "OpenRouter server error: %s. Retry %s",
                            response.status_code,
                            attempt + 1
                        )

                        time.sleep(2 ** attempt)
                        continue

                if not response.ok:

                    raise RuntimeError(
                        f"OpenRouter HTTP {response.status_code}: "
                        f"{response.text[:500]}"
                    )

                break

            except OpenRouterRateLimitError:
                raise

            except requests.RequestException:

                if attempt >= MAX_RETRIES - 1:
                    raise

                logger.warning(
                    "Connection error. Retry %s",
                    attempt + 1
                )

                time.sleep(2 ** attempt)

        if response is None or not response.ok:

            raise RuntimeError(
                "OpenRouter request failed"
            )

        try:

            result = response.json()

            answer = (
                result["choices"][0]
                ["message"]["content"]
            )

        except (ValueError, KeyError, IndexError, TypeError):

            raise RuntimeError(
                "Invalid OpenRouter response"
            )

        answer = clean_answer(answer)

        if not answer:
            raise RuntimeError("Empty AI response")

        with memory_lock:

            conversations[user_id] = (
                history + [
                    {
                        "role": "user",
                        "content": text
                    },
                    {
                        "role": "assistant",
                        "content": answer
                    }
                ]
            )[-MAX_HISTORY:]

        save_memory()

        logger.info(
            "AI response generated for user %s",
            user_id
        )

        return answer


# ==========================================
# TELEGRAM COMMANDS
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = str(update.effective_user.id)

    get_mood(user_id)

    language = get_language(user_id)

    await update.message.reply_text(
        random.choice(START_PHRASES[language])
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    language = get_language(update.effective_user.id)

    await update.message.reply_text(
        HELP_TEXT[language]
    )


async def about(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    language = get_language(update.effective_user.id)

    await update.message.reply_text(
        ABOUT_TEXT[language]
    )


async def model(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    language = get_language(update.effective_user.id)

    if language == "en":

        message = (
            f"Current model: {MODEL_NAME}\n"
            "Routing through OpenRouter."
        )

    else:

        message = (
            f"Текущая модель: {MODEL_NAME}\n"
            "Маршрутизация через OpenRouter."
        )

    await update.message.reply_text(message)


async def clear(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = str(update.effective_user.id)

    language = get_language(user_id)

    with get_user_lock(user_id):

        with memory_lock:

            conversations.pop(
                user_id,
                None
            )

            user_moods[user_id] = random.choice(
                MOODS
            )

        save_memory()

    if language == "en":

        message = (
            "History wiped. "
            "A clean slate, samurai."
        )

    else:

        message = (
            "История стёрта. Начнём с чистого листа."
        )

    await update.message.reply_text(message)


# ==========================================
# LANGUAGE COMMAND
# ==========================================

async def language_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = str(update.effective_user.id)

    if not context.args:

        current = get_language(user_id)

        if current == "en":

            message = (
                "Current language: English.\n"
                "Use /language ru to switch to Russian."
            )

        else:

            message = (
                "Текущий язык: русский.\n"
                "Используй /language en для переключения."
            )

        await update.message.reply_text(message)

        return

    language = context.args[0].lower()

    if language in ("ru", "russian"):

        set_language(user_id, "ru")

        await update.message.reply_text(
            "Ладно, чумба. Снова русский."
        )

    elif language in ("en", "english"):

        set_language(user_id, "en")

        await update.message.reply_text(
            "Fine, samurai. English it is."
        )

    else:

        await update.message.reply_text(
            "Используй /language ru или /language en."
        )


# ==========================================
# LONG MESSAGE HANDLER
# ==========================================

async def send_long_message(update, text):

    for i in range(
        0,
        len(text),
        MAX_MESSAGE_LENGTH
    ):

        await update.message.reply_text(
            text[i:i + MAX_MESSAGE_LENGTH]
        )


# ==========================================
# CHAT HANDLER
# ==========================================

async def chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)

    try:

        # Check for language switching requests

        requested_language = detect_language_request(
            update.message.text
        )

        if requested_language:

            set_language(
                user_id,
                requested_language
            )

            if requested_language == "en":

                message = (
                    "English it is, samurai. "
                    "Now, where were we?"
                )

            else:

                message = (
                    "Ладно, чумба. Возвращаемся к русскому."
                )

            await update.message.reply_text(message)

            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )

        answer = await asyncio.to_thread(
            ask_ai,
            user_id,
            update.message.text
        )

        await send_long_message(
            update,
            answer
        )

    except OpenRouterRateLimitError as error:

        logger.warning(
            "OPENROUTER RATE LIMIT REACHED"
        )

        await update.message.reply_text(
            format_wait_time(
                error.reset_timestamp,
                get_language(user_id)
            )
        )

    except Exception:

        logger.exception("CHAT ERROR")

        if get_language(user_id) == "en":

            message = (
                "Shit, the system went down. "
                "Try again later, samurai."
            )

        else:

            message = (
                "Твою мать, система легла. "
                "Попробуй ещё раз позже."
            )

        await update.message.reply_text(message)


# ==========================================
# RENDER HEALTH SERVER
# ==========================================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"Johnny is alive"
        )

    def log_message(self, format, *args):
        pass


def run_dummy_server():

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    server.daemon_threads = True

    logger.info(
        "HEALTH SERVER STARTED ON PORT %s",
        PORT
    )

    server.serve_forever()


# ==========================================
# TELEGRAM ERROR HANDLER
# ==========================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "TELEGRAM ERROR",
        exc_info=context.error
    )


# ==========================================
# MAIN
# ==========================================

def main():

    load_memory()

    threading.Thread(
        target=run_dummy_server,
        daemon=True,
        name="HealthServer"
    ).start()

    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(False)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("clear", clear)
    )

    app.add_handler(
        CommandHandler("about", about)
    )

    app.add_handler(
        CommandHandler("model", model)
    )

    app.add_handler(
        CommandHandler("language", language_command)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat
        )
    )

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "JOHNNY SILVERHAND IS ONLINE"
    )

    app.run_polling(
        drop_pending_updates=False
    )


if __name__ == "__main__":

    main()
