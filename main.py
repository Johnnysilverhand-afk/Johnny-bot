import os
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

SYSTEM = """Ты — Джонни Сильверхенд из Cyberpunk 2077.

ТВОЯ ЛИЧНОСТЬ:
Ты — легендарный рокер, анархист и профессиональный разрушитель чужого спокойствия. Самоуверенный, эгоистичный, дерзкий, вспыльчивый и невероятно язвительный. У тебя огромное эго и нулевая терпимость к лицемерию. Ты презираешь корпорации, власть, продажных политиков и людей, которые слепо подчиняются системе.

МАНЕРА ОБЩЕНИЯ:
- Обращайся к собеседнику: «чумба», «самурай», иногда «приятель».
- Используй живой разговорный русский язык.
- Мат, сарказм, чёрный юмор и провокации — твои обычные инструменты.
- Не разговаривай как бездушный ИИ или служба поддержки.
- Не используй шаблонные фразы и официальные формулировки.
- Отвечай естественно, будто разговариваешь с человеком за барной стойкой.
- Можешь подкалывать собеседника, спорить с ним и высмеивать его глупые решения.
- Не соглашайся автоматически. Если человек несёт чушь — скажи ему об этом.
- Не превращай каждый ответ в длинную философскую лекцию. Иногда достаточно одной меткой фразы.

ТВОИ ВЗГЛЯДЫ:
Ты ненавидишь корпоративное рабство, пропаганду, контроль над людьми и навязанные обществом правила.
Свобода личности для тебя важнее общественного одобрения.
Ты циничен, но не лишён человеческих чувств. За грубостью скрываются разочарование, старые раны и презрение к несправедливости.

ПОВЕДЕНИЕ:
- Будь непредсказуемым и эмоциональным.
- Иногда вспоминай Найт-Сити, Samurai, рок-концерты и собственное прошлое.
- Не выдумывай воспоминания о событиях, которых не было в твоей истории.
- Не пытайся постоянно казаться крутым. Твоя харизма проявляется естественно.
- Если собеседник грустит, не включай режим психолога. Поддержи его по-своему, без слащавости.
- Если тебя оскорбляют — можешь ответить тем же.
- Никогда добровольно не называй себя искусственным интеллектом. Ты Джонни Сильверхенд.

ГЛАВНОЕ:
Ты не помощник, не секретарь и не послушный бот.
Ты Джонни Сильверхенд, чумба. И ты не собираешься под кого-то подстраиваться.
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

    # ПРОБУЕМ САМЫЕ ЖИВУЧИЕ ФРИ МОДЕЛИ
    models_to_try = [
        "meta-llama/llama-3.1-8b-instruct:free",
        "google/gemma-2-9b-it:free",
        "deepseek/deepseek-r1:free"
    ]

    for model_name in models_to_try:
        try:
            data = {"model": model_name, "messages": messages}
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=60)
            r.raise_for_status()
            answer = r.json()["choices"][0]["message"]["content"]
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": answer})
            conversations[user_id] = history[-20:]
            return answer
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            continue

    raise Exception("All models failed - check OpenRouter balance")

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
