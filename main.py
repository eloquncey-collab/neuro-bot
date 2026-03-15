import os
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import asyncio

from database import db
from dotenv import load_dotenv

# Загружаем конфиг
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

# Настройка логирования (Senior level logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- States (Состояния) ---
class Form(StatesGroup):
    add_prompt_name = State()
    add_prompt_text = State()
    add_channel = State()

# --- Middleware (Проверка админки) ---
async def admin_check(handler, event, data):
    if event.from_user.id in ADMIN_IDS:
        return await handler(event, data)
    else:
        await event.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

# --- Клавиатуры ---
def get_main_keyboard():
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить Промпт", callback_data="add_prompt")],
        [InlineKeyboardButton(text="📝 Выбрать Промпт", callback_data="list_prompts")],
        [InlineKeyboardButton(text="📢 Добавить Канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="📊 Список Каналов", callback_data="list_channels")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- OpenAI Service (Заглушка для примера) ---
async def generate_comment(post_text: str, prompt: str) -> str:
    """
    Генерация комментария. Здесь можно интегрировать OpenAI, Claude или local LLM.
    """
    # Эмуляция задержки (чтобы не спамить)
    await asyncio.sleep(1)
    
    # Пример запроса к OpenAI
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Напиши короткий комментарий к посту: {post_text}"}
        ],
        "max_tokens": 50
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    json_data = await resp.json()
                    return json_data['choices'][0]['message']['content'].strip()
                else:
                    logger.error(f"OpenAI Error: {resp.status}")
                    return "Интересный пост!"
    except Exception as e:
        logger.error(f"AI Generation failed: {e}")
        return "Крутой контент!"

# --- Handlers ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Бот работает только для администраторов.")
        return
    
    await message.answer("👋 Панель управления нейро-комментатором.", reply_markup=get_main_keyboard())

# --- Логика Промптов ---
@dp.callback_query(F.data == "add_prompt")
async def ask_prompt_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.add_prompt_name)
    await callback.message.edit_text("📝 Введите название для нового промпта:")

@dp.message(Form.add_prompt_name)
async def save_prompt_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(Form.add_prompt_text)
    await message.answer("✍️ Теперь введите текст самого промпта (инструкцию для ИИ):")

@dp.message(Form.add_prompt_text)
async def save_prompt_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await db.add_prompt(data['name'], message.text)
    await state.clear()
    await message.answer("✅ Промпт сохранен!", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "list_prompts")
async def list_prompts(callback: types.CallbackQuery):
    prompts = await db.list_prompts()
    if not prompts:
        await callback.answer("Промптов нет.")
        return
    
    buttons = []
    for p in prompts:
        status = "✅" if p['is_active'] else "⚪"
        buttons.append([InlineKeyboardButton(text=f"{status} {p['name']}", callback_data=f"activate_prompt_{p['id']}")])
    
    await callback.message.edit_text("Выберите активный промпт:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("activate_prompt_"))
async def activate_prompt(callback: types.CallbackQuery):
    prompt_id = int(callback.data.split("_")[2])
    await db.set_active_prompt(prompt_id)
    await callback.answer("Промпт активирован!")
    await list_prompts(callback)

# --- Логика Каналов ---
@dp.callback_query(F.data == "add_channel")
async def ask_channel(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.add_channel)
    await callback.message.edit_text("🔗 Перешлите любое сообщение из канала или введите его ID (например, -100123456789):")

@dp.message(Form.add_channel)
async def save_channel(message: types.Message, state: FSMContext):
    channel_id = None
    
    # Если пересланное сообщение
    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
    else:
        # Если ввели ID вручную
        try:
            channel_id = int(message.text)
        except ValueError:
            await message.answer("❌ Некорректный ID. Попробуйте еще раз.")
            return

    try:
        chat = await bot.get_chat(channel_id)
        await db.add_channel(str(channel_id), chat.title)
        await message.answer(f"✅ Канал **{chat.title}** добавлен в отслеживание.", parse_mode="Markdown")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка доступа к каналу. Убедитесь, что бот добавлен в администраторы канала.\nError: {e}")

@dp.callback_query(F.data == "list_channels")
async def list_channels(callback: types.CallbackQuery):
    channels = await db.get_channels()
    text = "📊 Отслеживаемые каналы:\n\n" + "\n".join(channels) if channels else "Каналов нет."
    await callback.message.edit_text(text)

# --- Фоновая задача (Комментинг) ---
async def comment_worker():
    """
    Фоновый процесс, который проверяет каналы и пишет комментарии.
    ВАЖНО: Бот должен быть АДМИНОМ в каналах.
    """
    while True:
        try:
            prompt = await db.get_active_prompt()
            channels = await db.get_channels()
            
            if not prompt or not channels:
                await asyncio.sleep(60)
                continue

            # Здесь должна быть логика отслеживания новых постов.
            # Для упрощения примера, мы просто берем случайный канал (демонстрация)
            # В реальном проекте нужно хранить ID последних постов в БД.
            
            target_channel_id = random.choice(channels)
            logger.info(f"Checking channel: {target_channel_id}")
            
            # В реальной жизни здесь мы получаем последние сообщения, смотрим, комментировали ли мы их.
            # И если нет - вызываем generate_comment и bot.send_message.
            
            # Имитация работы:
            # await bot.send_message(target_channel_id, await generate_comment("Тестовый пост", prompt))
            
        except Exception as e:
            logger.error(f"Worker error: {e}")
        
        # Спим случайное время от 30 мин до 2 часов (Anti-Ban /人性化)
        sleep_time = random.randint(1800, 7200)
        await asyncio.sleep(sleep_time)

# --- Запуск ---
async def main():
    # Запускаем фоновую задачу
    asyncio.create_task(comment_worker())
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")