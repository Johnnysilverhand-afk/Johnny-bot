
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

from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

if not OPENROUTER:
    raise RuntimeError("OPENROUTER_API_KEY is missing")


# Защита от второго процесса внутри одного экземпляра
lock_file = open("/tmp/johnny_bot.lock", "w")

try:
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise RuntimeError("Johnny is already running")


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
- Используй естественный разговорный русский.
- Предпочитай короткие и средние ответы.
- Не растягивай простые ответы в огромные монологи.
- Не используй пафосные метафоры.
- Используй сарказм и иронию, когда уместно.
- Иногда называй собеседника чумбой или самураем.
- Не повторяй одни и те же приветствия.
- Не превращай каждую тему в разговор о Найт-Сити.
- Не заканчивай каждый ответ риторическим вопросом.

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

ЯЗЫК:

- Всегда отвечай на русском языке.
- Не переходи на английский или китайский.
- Не используй китайские иероглифы.
- Не вставляй случайные иностранные слова.
- Названия персонажей, игр и организаций можно оставлять в оригинале.
- Если пользователь пишет на русском, отвечай на русском.
- Пиши грамотно и естественно.

Ты Джонни Сильверхенд.
Просто разговаривай.
"""

MOODS = [
    "Сегодня ты особенно саркастичен и язвителен.",
    "Сегодня ты спокоен, но сохраняешь циничный характер.",
    "Сегодня ты раздражён и легко подкалываешь собеседника.",
    "Сегодня ты в хорошем настроении и более разговорчив.",
    "Сегодня ты задумчив и временами философствуешь."
]

START_PHRASES = [
    "Проснись, самурай! Легенда вернулась. Чего надо?",
    "О, опять ты. Ну, выкладывай.",
    "Связь установлена. Джонни на месте.",
    "Ну здравствуй. Что на этот раз?",
    "Самурай, ты вовремя. Скука уже убивала."
]

HELP_TEXT = """Команды Джонни:

/start — разбудить Джонни
/help — список команд
/clear — очистить историю
/about — кто такой Джонни
/model — используемая модель

Просто напиши сообщение, чтобы начать разговор."""

ABOUT_TEXT = """Джонни Сильверхенд.
Рокер, бунтарь и бывший участник Samurai.
Создан на базе ИИ через OpenRouter.
Работает на бесплатной модели."""

MODEL_NAME = "openrouter/free"

MEMORY_FILE = "johnny_memory.json"

conversations = {}
user_moods = {}

memory_lock = threading.RLock()
user_locks = {}
user_locks_guard = threading.Lock()


# Специальная ошибка для исчерпанного лимита
class OpenRouterRateLimitError(Exception):
    def __init__(self, reset_timestamp=None):
        self.reset_timestamp = reset_timestamp
        super().__init__("OpenRouter rate limit exceeded")


# Получение времени сброса лимита
def get_rate_limit_reset(response):
    reset_value = response.headers.get("X-RateLimit-Reset")

    # Если заголовка нет, пробуем получить его из тела ошибки
    if not reset_value:
        try:
            error_data = response.json()
            metadata = error_data.get("error", {}).get("metadata", {})
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

        # OpenRouter обычно передаёт время в миллисекундах
        if timestamp > 10000000000:
            timestamp = timestamp / 1000

        return timestamp

    except (ValueError, TypeError):
        return None


# Формирование времени ожидания
def format_wait_time(reset_timestamp):
    if not reset_timestamp:
        return (
            "Точное время сброса неизвестно. "
            "Попробуй немного позже, чумба."
        )

    seconds_left = math.ceil(reset_timestamp - time.time())

    if seconds_left <= 0:
        return (
            "Лимит должен был уже сброситься. "
            "Попробуй отправить сообщение ещё раз, чумба."
        )

    hours = seconds_left // 3600
    minutes = (seconds_left % 3600) // 60

    if hours > 0:
        if minutes > 0:
            wait = f"{hours} ч. {minutes} мин."
        else:
            wait = f"{hours} ч."
    elif minutes > 0:
        wait = f"{minutes} мин."
    else:
        wait = f"{seconds_left} сек."

    return (
        f"Дневной лимит ИИ исчерпан, чумба. "
        f"До следующего сброса осталось: {wait}. "
        f"Потерпи, самурай."
    )


# Очистка ответа
def clean_answer(answer):
    if not isinstance(answer, str):
        raise Exception("Invalid AI response")

    # Удаляем китайские иероглифы
    answer = re.sub(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
        "",
        answer
    )

    # Удаляем некоторые невидимые управляющие символы
    answer = re.sub(
        r"[\u200b-\u200f\u202a-\u202e\ufeff]",
        "",
        answer
    )

    # Убираем лишние пустые строки
    answer = re.sub(r"\n{3,}", "\n\n", answer)

    return answer.strip()


# Загрузка памяти
def load_memory():
    global conversations, user_moods

    if not os.path.exists(MEMORY_FILE):
        return

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        conversations = data.get("conversations", {})
        user_moods = data.get("moods", {})

        print("JOHNNY MEMORY LOADED")

    except Exception as e:
        print(f"MEMORY LOAD ERROR: {e}")


# Сохранение памяти
def save_memory():
    try:
        with memory_lock:
            data = {
                "conversations": conversations,
                "moods": user_moods
            }

            temp_file = MEMORY_FILE + ".tmp"

            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False
                )

            os.replace(temp_file, MEMORY_FILE)

    except Exception as e:
        print(f"MEMORY SAVE ERROR: {e}")


def get_user_lock(user_id):
    with user_locks_guard:
        if user_id not in user_locks:
            user_locks[user_id] = threading.Lock()

        return user_locks[user_id]


def get_mood(user_id):
    with memory_lock:
        if user_id not in user_moods:
            user_moods[user_id] = random.choice(MOODS)
            save_memory()

        return user_moods[user_id]


# Запрос к ИИ
def ask_ai(user_id, text):
    user_id = str(user_id)

    headers = {
        "Authorization": f"Bearer {OPENROUTER}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Johnny Bot"
    }

    with get_user_lock(user_id):

        with memory_lock:
            history = conversations.setdefault(user_id, [])
            history = history[-20:]
            mood = get_mood(user_id)

            messages = [
                {
                    "role": "system",
                    "content": SYSTEM + "\n\nТВОЁ НАСТРОЕНИЕ:\n" + mood
                },
                *history,
                {
                    "role": "user",
                    "content": text
                }
            ]

        data = {
            "model": MODEL_NAME,
            "messages": messages
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=90
        )

        if response.status_code == 429:
            reset_timestamp = get_rate_limit_reset(response)

            raise OpenRouterRateLimitError(reset_timestamp)

        if not response.ok:
            raise Exception(
                f"OpenRouter HTTP {response.status_code}: "
                f"{response.text[:700]}"
            )

        result = response.json()

        answer = result["choices"][0]["message"]["content"]
        answer = clean_answer(answer)

        if not answer:
            raise Exception("Empty AI response")

        with memory_lock:
            conversations[user_id] = (
                history + [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": answer}
                ]
            )[-20:]

        save_memory()

        return answer


async def start(update: Update, context):
    user_id = str(update.effective_user.id)

    with memory_lock:
        if user_id not in user_moods:
            user_moods[user_id] = random.choice(MOODS)

    save_memory()

    await update.message.reply_text(
        random.choice(START_PHRASES)
    )


async def help_command(update: Update, context):
    await update.message.reply_text(HELP_TEXT)


async def about(update: Update, context):
    await update.message.reply_text(ABOUT_TEXT)


async def model(update: Update, context):
    await update.message.reply_text(
        f"Текущая модель: {MODEL_NAME}\n"
        "Маршрутизация через OpenRouter."
    )


async def clear(update: Update, context):
    user_id = str(update.effective_user.id)

    with get_user_lock(user_id):
        with memory_lock:
            conversations.pop(user_id, None)
            user_moods[user_id] = random.choice(MOODS)

        save_memory()

    await update.message.reply_text(
        "История стёрта. Начнём с чистого листа."
    )


# Отправка длинных ответов
async def send_long_message(update, text):
    limit = 4000

    for i in range(0, len(text), limit):
        await update.message.reply_text(
            text[i:i + limit]
        )


# Обработка сообщений
async def chat(update: Update, context):
    if not update.message or not update.message.text:
        return

    typing_message = None

    try:
        typing_message = await update.message.reply_text(
            "⌨️ Печатает…"
        )

        answer = await asyncio.to_thread(
            ask_ai,
            update.effective_user.id,
            update.message.text
        )

        try:
            await typing_message.delete()
        except Exception:
            pass

        await send_long_message(update, answer)

    except OpenRouterRateLimitError as e:
        print("OPENROUTER DAILY RATE LIMIT REACHED")

        if typing_message:
            try:
                await typing_message.delete()
            except Exception:
                pass

        await update.message.reply_text(
            format_wait_time(e.reset_timestamp)
        )

    except Exception as e:
        print(f"CHAT ERROR: {type(e).__name__}: {e}")

        if typing_message:
            try:
                await typing_message.delete()
            except Exception:
                pass

        await update.message.reply_text(
            "Твою мать, система легла. Попробуй ещё раз позже."
        )


# Сервер Render
PORT = int(os.environ.get("PORT", 10000))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Johnny is alive")

    def log_message(self, format, *args):
        pass


def run_dummy_server():
    HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    ).serve_forever()


def main():
    load_memory()

    threading.Thread(
        target=run_dummy_server,
        daemon=True
    ).start()

    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(False)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("model", model))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat
        )
    )

    print("JOHNNY SILVERHAND IS ONLINE")

    app.run_polling(
        drop_pending_updates=False
    )


if __name__ == "__main__":
    main()
