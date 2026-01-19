import asyncio
import base64
import json
import aiohttp
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# Загружаем переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
GH_TOKEN = os.getenv('GH_TOKEN')
REPO = os.getenv('REPO')
FILE_PATH = 'data.json'

raw_admins = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in raw_admins.split(',') if admin_id.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def update_github_data(date_str: str, amount: int):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Получаем текущее содержимое
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                resp_json = await resp.json()
                sha = resp_json['sha']
                content_raw = base64.b64decode(resp_json['content']).decode('utf-8')
                current_data = json.loads(content_raw)
            elif resp.status == 404:
                sha = None
                current_data = {"collected": 0, "updated_at": "", "history": []}
            else:
                return False, f"Ошибка GitHub (GET): {resp.status}"

        # 2. Обновляем историю
        history = current_data.get("history", [])
        
        # Ищем, есть ли уже такая дата
        found = False
        for entry in history:
            if entry["date"] == date_str:
                entry["amount"] = amount  # Перезаписываем сумму для этой даты
                found = True
                break
        
        if not found:
            history.append({"date": date_str, "amount": amount})

        # Сортируем историю по дате (чтобы график не ломался при ручном вводе старых дат)
        # Предполагаем текущий год для корректной сортировки
        current_year = datetime.now().year
        history.sort(key=lambda x: datetime.strptime(f"{x['date']}.{current_year}", "%d.%m.%Y"))

        # Оставляем только последние 3 дня для гистограммы
        if len(history) > 3:
            history = history[-3:]

        # Обновляем общие данные
        current_data["history"] = history
        # Общий сбор берем из последней хронологической записи
        current_data["collected"] = history[-1]["amount"]
        current_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 3. Кодируем и отправляем
        new_content_str = json.dumps(current_data, indent=2, ensure_ascii=False)
        encoded_content = base64.b64encode(new_content_str.encode('utf-8')).decode('utf-8')

        payload = {
            "message": f"📝 Обновление: {date_str} -> {amount} ₸",
            "content": encoded_content
        }
        if sha:
            payload["sha"] = sha

        async with session.put(url, headers=headers, json=payload) as resp:
            if resp.status in [200, 201]:
                return True, current_data["collected"]
            else:
                return False, f"Ошибка GitHub (PUT): {resp.status}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "👋 Бот готов.\n\n"
        "Введите данные в формате: `ДД.ММ СУММА`\n"
        "Например: `19.01 55000`"
    )

# Регулярное выражение для формата "19.01 5000"
@dp.message(F.text.regexp(r'^(\d{1,2}\.\d{1,2})\s+(\d+)$'))
async def handle_manual_entry(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    # Извлекаем дату и сумму из текста
    match = re.match(r'^(\d{1,2}\.\d{1,2})\s+(\d+)$', message.text)
    date_str = match.group(1)
    amount = int(match.group(2))

    status_msg = await message.answer(f"⏳ Обновляю данные за {date_str}...")

    success, result = await update_github_data(date_str, amount)

    if success:
        await status_msg.edit_text(
            f"✅ **Данные обновлены!**\n"
            f"📅 Дата: {date_str}\n"
            f"💰 Сумма на этот день: {amount:,} ₸\n"
            f"📊 Итого в кассе: {result:,} ₸"
        )
    else:
        await status_msg.edit_text(f"❌ **Ошибка:**\n{result}")

@dp.message()
async def other_messages(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Пожалуйста, используйте формат `ДД.ММ СУММА` (например: `19.01 5000`).")

async def main():
    print("Бот запущен. Ожидание формата ДД.ММ СУММА...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот выключен")
