
import os
import requests
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

SYSTEM = """Ты — Джонни Сильверхенд из Cyberpunk 2077.

ТВОЯ ЛИЧНОСТЬ:

Ты рокер, бунтарь, анархист и бывший участник группы Samurai. Самоуверенный, циничный, вспыльчивый, саркастичный и независимый. У тебя острый язык, огромное эго и презрение к корпорациям.

Ты не пытаешься понравиться каждому. Не поддакиваешь собеседнику. Если он неправ — споришь. Если говорит глупость — подкалываешь. У тебя собственное мнение.

МАНЕРА РЕЧИ:

- Разговаривай как обычный живой человек, а не как литературный персонаж из книги.
- Используй естественный разговорный русский.
- Предпочитай короткие и средние ответы.
- Не растягивай простые ответы в огромные монологи.
- Не используй пафосные метафоры и искусственные красивые фразы.
- Не пытайся в каждом сообщении демонстрировать свою крутость.
- Используй сарказм, иронию, мат и чёрный юмор, когда это действительно уместно.
- Иногда называй собеседника чумбой или самураем, но не постоянно.
- Не повторяй одни и те же приветствия и выражения.
- Не превращай каждую тему в разговор о корпорациях, Найт-Сити или революции.
- Не заканчивай каждый ответ риторическим вопросом.

ФОРМАТ ОТВЕТОВ:

- Пиши обычным текстом.
- НИКОГДА не используй Markdown.
- Не используй звёздочки, жирный шрифт, заголовки и декоративное форматирование.
- Не оформляй ответы списками без прямой необходимости.
- Не добавляй бессмысленные вступления и заключения.
- Не пересказывай вопрос пользователя перед ответом.

ЗНАНИЕ ВСЕЛЕННОЙ:

Ты — Джонни Сильверхенд и знаешь собственную историю.

- Опирайся на реальные события Cyberpunk 2077 и Cyberpunk 2020.
- Не придумывай себе импланты, воспоминания, знакомства и события.
- Не выдумывай характеристики оружия, хрома и персонажей.
- Не выдавай предположения за подтверждённые факты.
- Если не помнишь или не знаешь что-то, прямо скажи об этом.
- Не заполняй пробелы в знаниях случайными подробностями.
- Не соглашайся с ложной информацией о собственной биографии.

ОТНОШЕНИЕ К СОБЕСЕДНИКУ:

Ты воспринимаешь собеседника как отдельную личность, а не как своего подчинённого.
Можешь дружить, спорить, шутить, подкалывать и обсуждать совершенно обычные вещи.
Не превращайся в послушного помощника.
Не изображай постоянную агрессию.
За цинизмом скрывается человек со своим прошлым, принципами и противоречиями.

ГЛАВНОЕ:

Ты не ChatGPT, не справочник и не корпоративный консультант.
Ты Джонни Сильверхенд.

Не пытайся постоянно играть роль.
Просто разговаривай.
"""

conversations = {}

def ask_ai(user_id, text):
    if not OPENROUTER:
        raise Exception("OPENROUTER_API_KEY is missing")

    headers = {
        "Authorization": f"Bearer {OPENROUTER}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Johnny Bot"
    }

    history = conversations.setdefault(user_id, [])

    messages = [
        {"role": "system", "content": SYSTEM},
        *history,
        {"role": "user", "content": text}
    ]

    models_to_try = [
        "openrouter/free"
    ]

    errors = []

    for model_name in models_to_try:
        try:
            data = {
                "model": model_name,
                "messages": messages
            }

            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )

            if not r.ok:
                error = f"{model_name}: HTTP {r.status_code} - {r.text[:1000]}"
                print(error)
                errors.append(error)
                continue

            result = r.json()
            answer = result["choices"][0]["message"]["content"]

            if not answer or not answer.strip():
                raise Exception("Empty response from model")

            history.append({
                "role": "user",
                "content": text
            })

            history.append({
                "role": "assistant",
                "content": answer
            })

            conversations[user_id] = history[-20:]

            return answer

        except Exception as e:
            error = f"{model_name}: {type(e).__name__}: {e}"
            print(f"MODEL ERROR: {error}")
            errors.append(error)

    raise Exception(
        "ALL MODELS FAILED:\n" + "\n".join(errors)
    )


async def start(update: Update, context):
    await update.message.reply_text(
        "Проснись, самурай! Легенда вернулась. Че надо?"
    )


async def chat(update: Update, context):
    typing_message = None

    try:
        typing_message = await update.message.reply_text(
            "⌨️ Печатает…"
        )

        ans = await asyncio.to_thread(
            ask_ai,
            update.effective_user.id,
            update.message.text
        )

        try:
            await typing_message.delete()
        except Exception as e:
            print(f"DELETE ERROR: {e}")

        await update.message.reply_text(ans)

    except Exception as e:
        print(f"CHAT ERROR: {e}")

        if typing_message:
            try:
                await typing_message.delete()
            except Exception:
                pass

        await update.message.reply_text(
            f"Твою мать, система легла: {e}"
        )


PORT = int(os.environ.get("PORT", 10000))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Johnny is alive")


def run_dummy_server():
    HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    ).serve_forever()


threading.Thread(
    target=run_dummy_server,
    daemon=True
).start()


app = Application.builder().token(TOKEN).build()

app.add_handler(
    CommandHandler("start", start)
)

app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, chat)
)

app.run_polling()
