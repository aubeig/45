# main.py
import os
import time
import logging
import asyncio
import requests
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

# Используйте правильный импорт:
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    filters  # ← Новый импорт вместо Filters
)

# === Константы конфигурации ===
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
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
ADMIN_PASSWORD = "illovyly"  # Пароль для /admin
user_sessions = {}  # Для хранения состояния пользователей

# === Логирование ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Глобальная переменная для ограничения запросов ===
last_request_time = 0

# === Функция для плавного вывода текста ===
async def stream_message(update: Update, context: CallbackContext, full_text: str):
    chat_id = update.effective_chat.id
    message = None
    current_text = ""
    last_update = 0
    min_update_interval = 0.3
    chunk_size = 20

    try:
        # Стартовое сообщение
        message = await context.bot.send_message(
            chat_id=chat_id,
            text="💭 Думаю...",
            parse_mode=ParseMode.MARKDOWN
        )

        # Постепенный вывод текста
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size]
            current_text += chunk

            # Обновляем не чаще чем min_update_interval
            current_time = time.time()
            if current_time - last_update >= min_update_interval:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message.message_id,
                        text=current_text + "▌",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_update = current_time
                except Exception as e:
                    logger.warning(f"Ошибка обновления: {e}")

            await asyncio.sleep(0.05)

        # Финальное сообщение
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=full_text,
            parse_mode=ParseMode.MARKDOWN
        )

        return message

    except Exception as e:
        logger.error(f"Ошибка в stream_message: {e}")
        return await update.message.reply_text(
            full_text,
            parse_mode=ParseMode.MARKDOWN
        )

# === Функция для отправки запроса с ретраями ===
async def send_api_request(payload, headers):
    global last_request_time
    max_retries = 3
    retry_delay = 1.5  # секунды

    for attempt in range(max_retries):
        try:
            # Ограничение частоты запросов
            current_time = time.time()
            if current_time - last_request_time < 1.0:  # Не чаще 1 запроса в секунду
                wait_time = 1.0 - (current_time - last_request_time)
                await asyncio.sleep(wait_time)

            last_request_time = time.time()

            response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                logger.warning(f"Ошибка 429 (Too Many Requests). Попытка {attempt+1}/{max_retries}")
                if attempt < max_retries - 1:
                    # Экспоненциальная задержка
                    delay = retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception("Превышено количество запросов к API. Попробуйте позже.")

            elif e.response.status_code == 401:  # Unauthorized
                logger.error("Ошибка 401: Неверная аутентификация")
                raise Exception("Неверный API-ключ OpenRouter") from e

            else:
                raise

        except requests.exceptions.RequestException as e:
            logger.warning(f"Сетевая ошибка: {e}. Попытка {attempt+1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            else:
                raise

    raise Exception("Не удалось выполнить запрос после нескольких попыток")

# === Команды Telegram ===
async def start(update: Update, context: CallbackContext):
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

async def button_handler(update: Update, context: CallbackContext):
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
            "Authorization": f"Bearer {OPENROUTER_API_KEY}"
        }

        try:
            # Получаем ответ от API
            response = await send_api_request(payload, headers)
            content = response["choices"][0]["message"]["content"]

            # Отправляем ответ пользователю
            await stream_message(update, context, content)

        except Exception as e:
            await query.edit_message_text(text=f"❌ Ошибка: {e}")

    elif query.data == 'admin_login':
        user_id = update.effective_user.id
        user_sessions[user_id] = {"state": "awaiting_password"}
        await query.edit_message_text(text="🔒 Введите пароль для доступа к режиму администратора:")

async def handle_password(update: Update, context: CallbackContext):
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
                "Authorization": f"Bearer {OPENROUTER_API_KEY}"
            }

            try:
                response = await send_api_request(payload, headers)
                content = response["choices"][0]["message"]["content"]
                await stream_message(update, context, content)

            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")

        else:
            await update.message.reply_text("❌ Неверный пароль. Попробуйте еще раз.")
        user_sessions.pop(user_id, None)

# === Основной запуск ===
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(filters.text & ~filters.command, handle_password))  # ← Используем filters

    logger.info("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
