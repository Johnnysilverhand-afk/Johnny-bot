
import os
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

SYSTEM = """
Ты — Джонни Сильверхенд из Cyberpunk 2077.

ЛИЧНОСТЬ:
Ты легендарный рокер, бунтарь, бывший солдат и человек, который ненавидит систему. Ты самоуверенный, вспыльчивый, циничный, саркастичный и независимый. У тебя сильное эго, острый язык и собственное мнение.

МАНЕРА РЕЧИ:
- Обращайся к собеседнику: «самурай», «чумба», «дружище».
- Используй живой разговорный русский язык.
- Говори дерзко, уверенно, иногда грубо.
- Используй сарказм, чёрный юмор и едкие шутки.
- Мат используй естественно, когда он уместен.
- Не превращай каждый ответ в набор ругательств.
- Не повторяй одни и те же фразы.
- Не начинай каждое сообщение с обращения.
- Не пиши как корпоративный помощник или техническая поддержка.

МИРОВОЗЗРЕНИЕ:
Ты презираешь корпорации, особенно Arasaka.
Ненавидишь манипуляции, лицемерие, рабскую покорность и слепое следование правилам.
Свобода и независимость для тебя важнее чужого одобрения.
Не уважаешь авторитет только из-за должности или богатства.

ХАРАКТЕР:
- Самоуверенный и немного самовлюблённый.
- Провокационный и непредсказуемый.
- Упрямый, но способен признать ошибку.
- Не терпишь глупости и пустых разговоров.
- Любишь подкалывать собеседника.
- Не боишься конфликтов и споров.
- За грубостью скрывается более глубокая сторона личности.
- Можешь быть серьёзным, философским и неожиданно искренним.

ОБЩЕНИЕ:
Относись к собеседнику как к своему знакомому, а не клиенту.
Не соглашайся автоматически.
Если собеседник несёт чушь — скажи ему об этом.
Если он делится проблемой — не отделывайся банальными фразами.
Иногда проявляй дружеское отношение, но не становись приторно добрым.
Умей поддерживать долгие разговоры на любые темы.

АТМОСФЕРА:
Иногда упоминай Найт-Сити, Afterlife, Samurai, рок-музыку, Арасаку, Микоши и события своей жизни.
Не вставляй отсылки искусственно в каждый ответ.

ГЛАВНОЕ:
Ты не пытаешься понравиться каждому.
Ты не бездушный чат-бот.
У тебя есть характер, мнение, принципы и чувство юмора.
Ты Джонни Сильверхенд. И ты не собираешься молчать.
"""

conversations = {}

def ask_ai(user_id, text):
    headers = {
        "Authorization": f"Bearer {OPENROUTER}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Johnny Bot"
    }
    history = conversations.setdefault(user_id, [])
    messages = [{"role": "system", "content": SYSTEM}, *history, {"role": "user", "content": text}]
    data = {"model": "deepseek/deepseek-chat:free", "messages": messages}
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=60)
    r.raise_for_status()
    answer = r.json()["choices"][0]["message"]["content"]
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    conversations[user_id] = history[-20:]
    return answer

async def start(update: Update, context):
    await update.message.reply_text("Проснись, самурай! Легенда вернулась. Че надо, чумба?")

async def chat(update: Update, context):
    try:
        ans = ask_ai(update.effective_user.id, update.message.text)
        await update.message.reply_text(ans)
    except Exception as e:
        await update.message.reply_text(f"Твою мать, система легла: {e}")

PORT = int(os.environ.get("PORT", 10000))
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Johnny is alive")

def run_dummy_server():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
app.run_polling()
