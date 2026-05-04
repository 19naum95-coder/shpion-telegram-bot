from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import ADMIN_IDS
from handlers.lobby import active_games
from database import Database

router = Router()
db = Database()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    total_players = await db.get_total_players()
    total_games = await db.get_total_games()
    active_count = len(active_games)
    
    text = (
        f"📈 **Статистика бота**\n\n"
        f"Всего игроков: {total_players}\n"
        f"Всего игр: {total_games}\n"
        f"Активных игр: {active_count}"
    )
    
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    text = message.text[11:].strip()
    if not text:
        await message.answer("⚠️ Напишите текст после команды")
        return
    
    players = await db.get_all_players()
    success = 0
    
    for player in players:
        try:
            await message.bot.send_message(
                player['user_id'],
                f"📢 **Сообщение от администрации:**\n\n{text}",
                parse_mode="Markdown"
            )
            success += 1
        except:
            pass
    
    await message.answer(f"✅ Отправлено {success}/{len(players)} игрокам")

@router.message(Command("endgame"))
async def cmd_end_game(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    chat_id = message.chat.id
    
    if chat_id in active_games:
        del active_games[chat_id]
        await message.answer("✅ Игра принудительно завершена")
    else:
        await message.answer("⚠️ Нет активной игры в этом чате")
