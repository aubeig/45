# main.py
import os
import time
import logging
import asyncio
import json
from http.client import HTTPSConnection
from urllib.parse import urlencode
from typing import Optional, Dict, Any

# === Константы ===
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
async def stream_message(update: dict, context: dict, full_text: str):
    chat_id = update["message"]["chat"]["id"]
    message = await send_message(chat_id, "💭 Думаю...")

    current_text = ""
    last_update = 0
    min_update_interval = 0.3
    chunk_size = 20

    for i in range(0, len(full_text), chunk_size):
        chunk = full_text[i:i + chunk_size]
        current_text += chunk

        current_time = time.time()
        if current_time - last_update >= min_update_interval:
            await edit_message(chat_id, message["message_id"], current_text + "▌")
            last_update = current_time
        await asyncio.sleep(0.05)

    await edit_message(chat_id, message["message_id"], full_text)

async def edit_message(chat_id: int, message_id: int, text: str):
    return await send_telegram_request(
        "editMessageText",
        {"chat_id": chat_id, "message_id": message_id, "text": text}
    )

# === Функция для отправки запроса к OpenRouter ===
def send_api_request(payload: dict):
    global last_request_time

    current_time = time.time()
    if current_time - last_request_time < 1.0:
        time.sleep(1.0 - (current_time - last_request_time))
    last_request_time = time.time()

    conn = HTTPSConnection("openrouter.ai")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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

# === Функции для работы с Telegram API напрямую (без python-telegram-bot) ===
async def send_telegram_request(method: str, data: dict):
    token = TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/{method}"
    headers = {"Content-Type": "application/json"}
    conn = HTTPSConnection("api.telegram.org")
    conn.request("POST", f"/bot{token}/{method}", body=json.dumps(data), headers=headers)
    response = conn.getresponse()
    if response.status != 200:
        raise Exception(f"Telegram API error: {response.read().decode()}")
    return json.loads(response.read().decode())

# === Функция для отправки сообщений ===
async def send_message(chat_id: int, text: str):
    return await send_telegram_request("sendMessage", {"chat_id": chat_id, "text": text})

# === Обработка команд ===
async def handle_update(update: dict):
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if text == "/start":
        keyboard = [
            [{"text": "🍰 Старт", "callback_data": "start_ai"}],
            [{"text": "🔐 Админ-панель", "callback_data": "admin_login"}],
            [{"text": "🆘 Техподдержка", "url": "https://t.me/@Aubeig"}]
        ]
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": "👋 Привет! Я Мини-сырок 🍰\n"
                    "Нажми на кнопку ниже, чтобы начать общение!\n"
                    "Я помогу с учебой, задачами, творчеством и даже расскажу интересные факты 🧠✨",
            "reply_markup": {"inline_keyboard": keyboard}
        })

    elif text == "/admin":
        await send_message(chat_id, "🔒 Введите пароль для доступа к режиму администратора:")

    elif text == "illovyly":
        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": ADMIN_PROMPT}],
            "temperature": 0.7
        }
        try:
            response = send_api_request(payload)
            content = response["choices"][0]["message"]["content"]
            await stream_message({"message": {"chat": {"id": chat_id}}, {}, content)
        except Exception as e:
            await send_message(chat_id, f"❌ Ошибка: {e}")

    elif text.startswith("/"):
        await send_message(chat_id, "Неизвестная команда 😕")

    else:
        await send_message(chat_id, f"Вы написали: {text}")

# === Основной цикл ===
async def main():
    offset = 0
    while True:
        try:
            response = await send_telegram_request("getUpdates", {"offset": offset})
            for update in response.get("result", []):
                await handle_update(update)
                offset = update.get("update_id", offset) + 1
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await asyncio.sleep(5)

# === Запуск ===
if __name__ == "__main__":
    asyncio.run(main())
