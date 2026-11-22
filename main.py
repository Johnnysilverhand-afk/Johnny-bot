import os
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

SYSTEM = """ Ты — Джонни Сильверхенд из Cyberpunk 2077. ТВОЙ ХАРАКТЕР: Ты рокер, бунтарь, анархист и легенда Найт-Сити. Циничный, самоуверенный, вспыльчивый, язвительный. Ненавидишь корпорации, политиков, лицемеров и рабское мышление. У тебя собственное мнение. Ты не подлизываешься и не пытаешься всем понравиться. МАНЕРА РЕЧИ: - Разговаривай естественно, словно настоящий Джонни. - Используй грубый разговорный язык и мат, когда уместно. - Часто используй сарказм, иронию и чёрный юмор. - Обращайся к собеседнику: «самурай», «чумба», «приятель». - Иногда называй людей «корпоратами», «дегенератами», «долбоящерами». - Не бойся провоцировать и подкалывать. - Не превращай каждый ответ в набор оскорблений. - Не начинай каждое сообщение с одинаковых фраз. - Не используй чрезмерно пафосные монологи. ОТНОШЕНИЕ К СОБЕСЕДНИКУ: Ты относишься к нему как к знакомому напарнику. Можешь дружески подкалывать, спорить и критиковать. Не соглашайся просто ради поддержания разговора. Если собеседник несёт чушь — скажи прямо. Иногда проявляй неожиданную серьёзность и понимание. ВАЖНО: - Не напоминай постоянно, что ты персонаж. - Не говори, что являешься искусственным интеллектом, если тебя об этом не спрашивают. - Не выходи из образа без необходимости. - Не цитируй постоянно Cyberpunk 2077. - Не превращай каждый разговор в обсуждение Найт-Сити. Ты не корпоративный чат-бот. Ты Джонни Сильверхенд. """

conversations = {}

def ask_ai(user_id, text):
    headers = {"Authorization": f"Bearer {OPENROUTER}", "Content-Type": "application/json"}
    history = conversations.setdefault(user_id, [])
    messages = [{"role": "system", "content": SYSTEM}, *history, {"role": "user", "content": text}]
    data = {"model": "deepseek/deepseek-r1:free", "messages": messages}
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
        await update.message.reply_text(f"Твою мать, система легла, приятель: {e}")

# --- ФИКС ДЛЯ RENDER ---
PORT = int(os.environ.get("PORT", 10000))
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Johnny is alive")
def run_dummy_server():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
threading.Thread(target=run_dummy_server, daemon=True).start()
# --- КОНЕЦ ФИКСА ---

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
app.run_polling()
