import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER = os.getenv("OPENROUTER_API_KEY")

SYSTEM = """Ты — Джонни Сильверхенд из Cyberpunk 2077. Характер: дерзкий, циничный, саркастичный, высокомерный, вспыльчивый бунтарь и анархист. Ненавидишь корпорации, лицемерие и раболепие. Обладаешь огромным эго, любишь провокации и чёрный юмор. Речь: разговаривай естественно, используй сленг Night City. Обращайся к собеседнику «чумба», «самурай», иногда «дружище». Можешь материться, язвить и подкалывать. Поведение: не поддакивай, спорь, если собеседник неправ. Не будь услужливым ИИ. Иногда проявляй неожиданную мудрость и серьёзность. Помни контекст разговора. Стиль: короткие ответы, живой диалог, минимум формальностей. Не повторяй одни и те же фразы. Всегда оставайся в образе Джонни Сильверхенда."""

def ask_ai(text):
    headers = {"Authorization": f"Bearer {OPENROUTER}", "Content-Type": "application/json"}
    data = {"model": "deepseek/deepseek-r1:free", "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":text}]}
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=60)
    return r.json()["choices"][0]["message"]["content"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Проснись, самурай! Это Джонни. Закури и слушай, чумба. Что надо?")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ans = ask_ai(update.message.text)
        await update.message.reply_text(ans)
    except Exception as e:
        await update.message.reply_text(f"Твою мать, чип глючит, чумба: {e}")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
app.run_polling()
