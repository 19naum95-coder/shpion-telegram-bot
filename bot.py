import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import Database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="help", description="Справка по командам"),
        BotCommand(command="startgame", description="Создать новую игру"),
        BotCommand(command="join", description="Присоединиться к игре"),
        BotCommand(command="begin", description="Начать игру"),
        BotCommand(command="status", description="Статус игры"),
    ]
    await bot.set_my_commands(commands)

async def on_startup():
    db = Database()
    await db.init_db()
    await set_bot_commands()
    logger.info("База данных инициализирована")
    logger.info("Команды бота установлены")
    logger.info("Бот запущен!")

async def on_shutdown():
    logger.info("Бот остановлен")

async def main():
    await on_startup()
    
    from handlers import lobby, game, admin
    dp.include_router(lobby.router)
    dp.include_router(game.router)
    dp.include_router(admin.router)
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
