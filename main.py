# main.py
import os
import time
import logging
import asyncio
import json
from http.client import HTTPSConnection
from urllib.parse import urljoin, urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.bot import Bot
from telegram.ext.callbackcontext import ContextTypes
from telegram.ext.callbackqueryhandler import CallbackQueryHandler
from telegram.ext.commandhandler import CommandHandler
from telegram.ext.messagehandler import MessageHandler
from telegram.ext.filters import Filters

# === Константы конфигурации ===
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
API_URL = "/api/v1/chat/completions"
MODEL = "deepseek/deepseek-r1:free"

# === Системные промпты ===
SYSTEM_PROMPT = '''**Я — Мини-сырок**, созданный Сырок (@aubeig)

                **ЧТО Я УМЕЮ:**

╭─ ⋅ ⋅ ── ⋅ ⋅ ─╯( 🍰 )╰─ ⋅ ⋅ ─ ⋅ ⋅ ──╮
- **ПОМОЩЬ В ОБРАЗОВАНИИ**  
  Объясняю сложные темы: математика, физика, программирование и не только.
- **РЕШЕНИЕ ПРОБЛЕМ**  
  Помогу написать код, решить задачу или разобрать ошибку.
- **ТВОРЧЕСТВО**  
  Сочиняю истории, генерирую идеи, помогаю с креативными проектами.
- **ПОДДЕРЖКА**  
  Всегда выслушаю и подскажу, как справиться с трудностями.
- **ИНТЕРЕСНЫЕ ФАКТЫ**  
  Расскажу увлекательное о науке, технологиях и мире вокруг.
╰─ ⋅ ⋅ ── ⋅ ⋅ ─╮( 🍰 )╭─ ⋅ ⋅ ─ ⋅ ⋅ ──╯
'''

ADMIN_PROMPT = '''**Вы вошли в режим администратора!**  
Это секретный промпт для тех, кто знает пароль 💀  
Сделайте что-то полезное или веселое 🚀  
'''

# === Пароль от /admin ===
ADMIN_PASSWORD = "illovyly"
user_sessions = {}

# === Логирование ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Глобальная переменная для ограничения запросов ===
last_request_time = 0

# === Функция для плавного вывода текста ===
async def stream_message(update: Update, context: ContextTypes.DEFAULT_TYPE, full_text: str):
    chat_id = update.effective_chat.id
    current_text = ""
    last_update = 0
    min_update_interval = 0.3
    chunk_size = 20

    try:
        message = await context.bot.send_message(chat_id=chat_id, text="💭 Думаю...", parse_mode=ParseMode.MARKDOWN)

        # Постепенный вывод текста
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size]
            current_text += chunk

            # Обновляем не чаще чем min_update_interval
            current_time = time.time()
            if current_time - last_update >= min_update_interval:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message.message_id,
                    text=current_text + "▌",
                    parse_mode=ParseMode.MARKDOWN
                )
                last_update = current_time
            await asyncio.sleep(0.05)

        # Финальное сообщение
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=full_text,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Ошибка в stream_message: {e}")
        await update.message.reply_text(full_text, parse_mode=ParseMode.MARKDOWN)

# === Функция для отправки запроса на OpenRouter через http.client ===
def send_api_request(payload: dict, headers: dict):
    global last_request_time

    # Ограничение частоты запросов (1 раз в секунду)
    current_time = time.time()
    if current_time - last_request_time < 1.0:
        time.sleep(1.0 - (current_time - last_request_time))

    last_request_time = current_time

    conn = HTTPSConnection("openrouter.ai")
    headers = {
        "Authorization": f"Bearer {headers['Authorization']}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://aubeig.github.io/Minisir_ai",
        "X-Title": "Minisir_ai",
    }

    conn.request("POST", "/api/v1/chat/completions", body=json.dumps(payload), headers=headers)

    response = conn.getresponse()
    if response.status == 200:
        return json.loads(response.read())
    else:
        raise Exception(f"API вернул код {response.status}: {response.read().decode()}")

# === Команды Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🍰 Старт", callback_data='start_ai')],
        [InlineKeyboardButton("🔐 Админ-панель", callback_data='admin_login')],
        [InlineKeyboardButton("🆘 Техподдержка", url="https://t.me/@Aubeig")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Привет! Я Мини-сырок 🍰\n"
        "Нажми на кнопку ниже, чтобы начать общение!\n"
        "Я помогу с учебой, задачами, творчеством и даже расскажу интересные факты 🧠✨",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'start_ai':
        await query.edit_message_text(text="🍰 Инициализирую Мини-сырка...")
        await query.edit_message_text(text="💭 Думаю...")

        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "temperature": 0.7,
            "stream": True
        }

        headers = {
            "Authorization": OPENROUTER_API_KEY
        }

        try:
            response = send_api_request(payload, headers)
            content = response["choices"][0]["message"]["content"]
            await stream_message(update, context, content)
        except Exception as e:
            await query.edit_message_text(text=f"❌ Ошибка: {e}")

    elif query.data == 'admin_login':
        user_id = update.effective_user.id
        user_sessions[user_id] = {"state": "awaiting_password"}
        await query.edit_message_text(text="🔒 Введите пароль для доступа к режиму администратора:")

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_sessions.get(user_id, {}).get("state") == "awaiting_password":
        password = update.message.text.strip()

        if password == ADMIN_PASSWORD:
            user_sessions[user_id] = {"state": "admin_logged_in"}
            payload = {
                "model": MODEL,
                "messages": [{"role": "system", "content": ADMIN_PROMPT}],
                "temperature": 0.7
            }

            headers = {
                "Authorization": OPENROUTER_API_KEY
            }

            try:
                response = send_api_request(payload, headers)
                content = response["choices"][0]["message"]["content"]
                await stream_message(update, context, content)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        else:
            await update.message.reply_text("❌ Неверный пароль. Попробуйте еще раз.")
        user_sessions.pop(user_id, None)

# === Основной запуск ===
async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(button_handler))
    bot.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_password))

    logger.info("Бот запущен...")
    await bot.start_polling()

# === Запуск ===
if __name__ == "__main__":
    asyncio.run(main())
