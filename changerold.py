import asyncio
import base64
import json
import aiohttp
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# Загружаем переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
GH_TOKEN = os.getenv('GH_TOKEN')
REPO = os.getenv('REPO')
FILE_PATH = 'data.json'

# Читаем ID админов и превращаем в список чисел
raw_admins = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in raw_admins.split(',') if admin_id.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def update_github_data(new_amount: int):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # ВАЖНО: Отключаем проверку SSL для обхода корпоративных фильтров
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Получаем текущий SHA файла
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                sha = data['sha']
            elif resp.status == 404:
                sha = None
            else:
                return False, f"Ошибка GitHub (GET): {resp.status}"

        # 2. Формируем контент
        content_dict = {"collected": new_amount}
        new_content_str = json.dumps(content_dict, indent=2)
        encoded_content = base64.b64encode(new_content_str.encode()).decode()

        payload = {
            "message": f"📊 Обновление сбора: {new_amount}$",
            "content": encoded_content
        }
        if sha:
            payload["sha"] = sha

        # 3. Отправляем обновление
        async with session.put(url, headers=headers, json=payload) as resp:
            if resp.status in [200, 201]:
                return True, "Успешно"
            else:
                return False, f"Ошибка GitHub (PUT): {resp.status}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("👋 Бот готов к работе. Пришлите число для обновления суммы.")

@dp.message(F.text.regexp(r'^\d+$'))
async def handle_amount(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    new_amount = int(message.text)
    status_msg = await message.answer("⏳ Обновляю данные на GitHub...")

    success, error_msg = await update_github_data(new_amount)

    if success:
        await status_msg.edit_text(f"✅ **Данные успешно обновлены!**\nСумма: ${new_amount:,}")
    else:
        await status_msg.edit_text(f"❌ **Ошибка при обновлении:**\n{error_msg}")

@dp.message()
async def other_messages(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Пожалуйста, введите корректное число.")

async def main():
    print("Бот успешно запущен и использует .env конфигурацию")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот выключен")
