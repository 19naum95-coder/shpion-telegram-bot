from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import random
import asyncio

from models.game import Game, GameState, Player
from database import Database
from config import LOCATIONS

router = Router()
db = Database()
active_games = {}

@router.message(Command("start"))
async def cmd_start_game(message: Message):
    chat_id = message.chat.id
    
    if chat_id in active_games:
        await message.answer("⚠️ Игра уже идёт! Используйте /status")
        return
    
    game = Game(chat_id=chat_id, host_id=message.from_user.id)
    active_games[chat_id] = game
    
    host_player = Player(
        user_id=message.from_user.id,
        username=message.from_user.username or f"User{message.from_user.id}"
    )
    game.add_player(host_player)
    
    await db.ensure_player_exists(
        user_id=message.from_user.id,
        username=host_player.username
    )
    
    await send_lobby_keyboard(message.bot, game)

async def send_lobby_keyboard(bot, game):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(text="➖ Выйти", callback_data="leave_game")],
        [InlineKeyboardButton(text="▶️ Начать игру (Хост)", callback_data="start_game")]
    ])
    
    players_list = "\n".join([f"• @{p.username}" for p in game.players.values()])
    text = f"🎮 НАБОР ИГРОКОВ\n\nИгроков: {len(game.players)}\nМинимум: 3\n\nУчастники:\n{players_list}"
    
    msg = await bot.send_message(game.chat_id, text, reply_markup=keyboard)

@router.callback_query(F.data == "join_game")
async def join_game_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.LOBBY:
        await callback.answer("⚠️ Игра уже началась!", show_alert=True)
        return
    
    if callback.from_user.id in game.players:
        await callback.answer("⚠️ Вы уже в игре!", show_alert=True)
        return
    
    player = Player(
        user_id=callback.from_user.id,
        username=callback.from_user.username or f"User{callback.from_user.id}"
    )
    game.add_player(player)
    
    await db.ensure_player_exists(
        user_id=callback.from_user.id,
        username=player.username
    )
    
    players_list = "\n".join([f"• @{p.username}" for p in game.players.values()])
    text = f"🎮 НАБОР ИГРОКОВ\n\nИгроков: {len(game.players)}\nМинимум: 3\n\nУчастники:\n{players_list}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(text="➖ Выйти", callback_data="leave_game")],
        [InlineKeyboardButton(text="▶️ Начать игру (Хост)", callback_data="start_game")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer(f"✅ @{player.username} присоединился!")

@router.callback_query(F.data == "leave_game")
async def leave_game_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if callback.from_user.id not in game.players:
        await callback.answer("⚠️ Вы не в игре!", show_alert=True)
        return
    
    if callback.from_user.id == game.host_id:
        await callback.answer("⚠️ Хост не может выйти! Используйте /cancel", show_alert=True)
        return
    
    username = game.players[callback.from_user.id].username
    game.remove_player(callback.from_user.id)
    
    players_list = "\n".join([f"• @{p.username}" for p in game.players.values()])
    text = f"🎮 НАБОР ИГРОКОВ\n\nИгроков: {len(game.players)}\nМинимум: 3\n\nУчастники:\n{players_list}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(text="➖ Выйти", callback_data="leave_game")],
        [InlineKeyboardButton(text="▶️ Начать игру (Хост)", callback_data="start_game")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer(f"👋 @{username} вышел!")

@router.callback_query(F.data == "start_game")
async def start_game_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if callback.from_user.id != game.host_id:
        await callback.answer("⚠️ Только хост может начать игру!", show_alert=True)
        return
    
    if len(game.players) < 3:
        await callback.answer("⚠️ Минимум 3 игрока!", show_alert=True)
        return
    
    location = random.choice(LOCATIONS)
    spy_id = random.choice(list(game.players.keys()))
    
    game.start_game(location, spy_id)
    
    for player in game.players.values():
        try:
            if player.user_id == spy_id:
                await callback.message.bot.send_message(player.user_id, "🕵️ Вы — ШПИОН!")
            else:
                hints = "\n".join(game.get_hints(player))
                await callback.message.bot.send_message(
                    player.user_id,
                    f"🔍 АГЕНТ\n📍 Локация: {location['name']}\n\n{hints}"
                )
        except:
            pass
    
    await callback.message.edit_text("✅ Игра началась! Роли отправлены в ЛС.")
    await callback.answer()
    
    from handlers.game import send_questions_keyboard
    await send_questions_keyboard(callback.message.bot, game)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        await message.answer("⚠️ Нет активной игры.")
        return
    
    game = active_games[chat_id]
    
    if message.from_user.id != game.host_id:
        await message.answer("⚠️ Только хост может отменить игру!")
        return
    
    game.stop_timer()
    del active_games[chat_id]
    await message.answer("🛑 Игра отменена.")

@router.callback_query(F.data == "show_leaderboard")
async def show_leaderboard_callback(callback: CallbackQuery):
    leaderboard = await db.get_leaderboard(10)
    
    if not leaderboard:
        await callback.answer("📊 Таблица лидеров пуста.", show_alert=True)
        return
    
    lines = []
    for i, player in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        winrate = (player['total_wins'] / player['total_games'] * 100) if player['total_games'] > 0 else 0
        lines.append(f"{medal} @{player['username']}\n   Очки: {player['total_points']} | Игр: {player['total_games']} | Побед: {player['total_wins']} ({winrate:.0f}%)")
    
    scoreboard = "\n\n".join(lines)
    await callback.message.answer(f"🏆 ТАБЛИЦА ЛИДЕРОВ:\n\n{scoreboard}")
    await callback.answer()
