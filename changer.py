import asyncio
import base64
import json
import aiohttp
import os
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

# Читаем ID админов
raw_admins = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in raw_admins.split(',') if admin_id.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def update_github_data(added_amount: int):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Получаем текущее содержимое файла и его SHA
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                resp_json = await resp.json()
                sha = resp_json['sha']
                # Декодируем текущий контент
                content_raw = base64.b64decode(resp_json['content']).decode('utf-8')
                current_data = json.loads(content_raw)
            elif resp.status == 404:
                # Если файла нет, создаем структуру с нуля
                sha = None
                current_data = {"collected": 0, "updated_at": "", "history": []}
            else:
                return False, f"Ошибка GitHub (GET): {resp.status}"

        # 2. Обновляем данные
        # Прибавляем сумму к общему сбору
        current_data["collected"] += added_amount
        
        # Обновляем время (для сайта)
        now = datetime.now()
        current_data["updated_at"] = now.strftime("%Y-%m-%d %H:%M")

        # Обновляем историю для гистограммы (последние 3 точки)
        new_history_entry = {
            "date": now.strftime("%d.%m"),
            "amount": current_data["collected"]
        }
        
        # Если запись за сегодня уже есть, обновляем её, если нет — добавляем
        if current_data["history"] and current_data["history"][-1]["date"] == new_history_entry["date"]:
            current_data["history"][-1]["amount"] = current_data["collected"]
        else:
            current_data["history"].append(new_history_entry)

        # Оставляем только последние 3 записи для гистограммы
        if len(current_data["history"]) > 3:
            current_data["history"] = current_data["history"][-3:]

        # 3. Кодируем новый контент
        new_content_str = json.dumps(current_data, indent=2, ensure_ascii=False)
        encoded_content = base64.b64encode(new_content_str.encode('utf-8')).decode('utf-8')

        payload = {
            "message": f"📊 Сбор пополнен на {added_amount} ₸ (Всего: {current_data['collected']} ₸)",
            "content": encoded_content
        }
        if sha:
            payload["sha"] = sha

        # 4. Отправляем обновление на GitHub
        async with session.put(url, headers=headers, json=payload) as resp:
            if resp.status in [200, 201]:
                return True, current_data["collected"]
            else:
                return False, f"Ошибка GitHub (PUT): {resp.status}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("👋 Бот готов. Пришлите сумму (только число), на которую пополнился сбор сегодня (в тенге).")

@dp.message(F.text.regexp(r'^\d+$'))
async def handle_amount(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    added_amount = int(message.text)
    status_msg = await message.answer("⏳ Связываюсь с GitHub...")

    success, result = await update_github_data(added_amount)

    if success:
        total = result
        await status_msg.edit_text(
            f"✅ **Данные обновлены!**\n"
            f"➕ Добавлено: {added_amount:,} ₸\n"
            f"💰 Общий сбор: {total:,} ₸"
        )
    else:
        await status_msg.edit_text(f"❌ **Ошибка:**\n{result}")

@dp.message()
async def other_messages(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Пожалуйста, введите только число (сумму пополнения в тенге).")

async def main():
    print("Бот запущен. Ожидание данных в тенге...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот выключен")