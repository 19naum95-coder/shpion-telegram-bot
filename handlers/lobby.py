from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio

from models.game import Game, GameState
from database import Database
from config import MIN_PLAYERS, MAX_PLAYERS, ADMIN_IDS, TIMER_LOBBY, TIMER_QUESTIONS
import random

router = Router()
db = Database()

active_games = {}

class GameStates(StatesGroup):
    in_game = State()

# Клавиатура для лобби
def get_lobby_keyboard(is_host: bool, can_start: bool):
    buttons = [
        [InlineKeyboardButton(text="➕ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(text="➖ Выйти", callback_data="leave_game")]
    ]
    if is_host and can_start:
        buttons.append([InlineKeyboardButton(text="▶️ Начать игру", callback_data="begin_game")])
    buttons.append([InlineKeyboardButton(text="📊 Статус", callback_data="game_status")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Описание игры
GAME_DESCRIPTION = """
🕵️ **ИГРА "ШПИОН"**

**Суть игры:**
Один из игроков — Шпион (не знает локацию)
Остальные — Агенты (знают локацию)

**Цель Агентов:** Вычислить Шпиона через вопросы
**Цель Шпиона:** Остаться незамеченным или угадать локацию

**Как играть:**
1️⃣ Игроки по очереди задают вопросы друг другу
2️⃣ Вопросы должны быть нейтральными (не выдавать локацию напрямую)
3️⃣ После раунда вопросов — голосование
4️⃣ Если Шпион раскрыт — он может попытаться угадать локацию

**Таймеры:**
⏱️ Сбор игроков: 1 минута
⏱️ Фаза вопросов: 3 минуты
⏱️ Голосование: 1 минута
⏱️ Угадывание: 30 секунд

Готовы? Присоединяйтесь! 🎮
"""

@router.message(Command("start"))
async def cmd_start(message: Message):
    await db.create_player(message.from_user.id, message.from_user.username)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Правила игры", callback_data="show_rules")],
        [InlineKeyboardButton(text="🎭 Роли в игре", callback_data="show_roles")],
        [InlineKeyboardButton(text="🏆 Таблица лидеров", callback_data="show_leaderboard")]
    ])
    
    text = (
        "Привет! Я бот для игры «Шпион». "
        "Соберите от 3 игроков, раздайте роли и вычислите шпиона. "
        "Готовы? Создайте лобби или присоединяйтесь к существующему."
    )
    await message.answer(text, reply_markup=keyboard)

@router.callback_query(F.data == "show_rules")
async def show_rules(callback: CallbackQuery):
    text = """
📖 **ПРАВИЛА ИГРЫ:**

Один игрок - Шпион (не знает локацию)
Остальные - Агенты (знают локацию)

🎯 **ЦЕЛЬ:**
• Агенты: вычислить шпиона
• Шпион: остаться незамеченным или угадать локацию

📝 **КАК ИГРАТЬ:**
1. /startgame - создать игру
2. Присоединиться через кнопку
3. Хост запускает игру
4. Задавайте вопросы через кнопки
5. Голосуйте за подозреваемого
6. Шпион может угадать локацию

⚙️ **КОМАНДЫ:**
/startgame - создать игру
/status - статус игры
/score - таблица лидеров
/help - справка
    """
    await callback.message.edit_text(text)
    await callback.answer()

@router.callback_query(F.data == "show_roles")
async def show_roles(callback: CallbackQuery):
    text = """
🎭 **РОЛИ В ИГРЕ:**

**🕵️ Шпион**
• Не знает локацию
• Должен остаться незамеченным
• Может угадать локацию при вскрытии
• Получает 5 очков за победу

**🔍 Агент**
• Знает локацию
• Должен вычислить шпиона
• Задаёт нейтральные вопросы
• Получает 3 очка за победу

**💡 Советы:**
Агентам: Задавайте вопросы, связанные с локацией, но не очевидные
Шпиону: Слушайте внимательно и пытайтесь понять где вы
    """
    await callback.message.edit_text(text)
    await callback.answer()

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(GAME_DESCRIPTION)

@router.message(Command("startgame"))
async def cmd_start_game(message: Message):
    chat_id = message.chat.id
    
    if chat_id in active_games:
        await message.answer("⚠️ В этом чате уже есть активная игра!")
        return
    
    game = Game(
        chat_id=chat_id,
        mode="classic",
        episode=1,
        host_id=message.from_user.id
    )
    
    active_games[chat_id] = game
    
    keyboard = get_lobby_keyboard(
        is_host=True,
        can_start=False
    )
    
    text = (
        f"🎮 **ЛОББИ СОЗДАНО**\n\n"
        f"{GAME_DESCRIPTION}\n\n"
        f"**Хост:** @{message.from_user.username}\n"
        f"**Игроков:** 0/{MAX_PLAYERS}\n"
        f"**Минимум:** {MIN_PLAYERS}\n\n"
        f"⏱️ Таймер: {TIMER_LOBBY} сек"
    )
    
    msg = await message.answer(text, reply_markup=keyboard)
    
    # Запускаем таймер лобби
    game.timer_task = asyncio.create_task(
        lobby_timer(message.bot, chat_id, msg.message_id)
    )

async def lobby_timer(bot, chat_id: int, message_id: int):
    try:
        for remaining in range(TIMER_LOBBY, 0, -10):
            await asyncio.sleep(10)
            
            if chat_id not in active_games:
                return
            
            game = active_games[chat_id]
            
            keyboard = get_lobby_keyboard(
                is_host=True,
                can_start=len(game.players) >= MIN_PLAYERS
            )
            
            players_text = "\n".join([f"• @{p.username}" for p in game.players.values()])
            
            text = (
                f"🎮 **ЛОББИ**\n\n"
                f"**Игроков:** {len(game.players)}/{MAX_PLAYERS}\n"
                f"{players_text}\n\n"
                f"⏱️ Осталось: {remaining} сек"
            )
            
            try:
                await bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=keyboard
                )
            except:
                pass
        
        # Таймер истёк
        if chat_id in active_games:
            game = active_games[chat_id]
            if len(game.players) >= MIN_PLAYERS:
                # Автостарт
                await auto_start_game(bot, chat_id)
            else:
                await bot.send_message(
                    chat_id,
                    "⏱️ Время вышло! Недостаточно игроков. Лобби закрыто."
                )
                del active_games[chat_id]
    except asyncio.CancelledError:
        pass

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
    
    if game.add_player(callback.from_user.id, callback.from_user.username):
        await callback.answer(f"✅ Вы присоединились!", show_alert=False)
        
        keyboard = get_lobby_keyboard(
            is_host=callback.from_user.id == game.host_id,
            can_start=len(game.players) >= MIN_PLAYERS
        )
        
        players_text = "\n".join([f"• @{p.username}" for p in game.players.values()])
        
        text = (
            f"🎮 **ЛОББИ**\n\n"
            f"**Игроков:** {len(game.players)}/{MAX_PLAYERS}\n"
            f"{players_text}"
        )
        
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except:
            pass
    else:
        await callback.answer("⚠️ Вы уже в игре или лобби переполнено!", show_alert=True)

@router.callback_query(F.data == "leave_game")
async def leave_game_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.remove_player(callback.from_user.id):
        await callback.answer("✅ Вы покинули лобби", show_alert=False)
        
        if len(game.players) == 0:
            game.stop_timer()
            del active_games[chat_id]
            await callback.message.edit_text("Лобби закрыто (нет игроков)")
        else:
            keyboard = get_lobby_keyboard(
                is_host=callback.from_user.id == game.host_id,
                can_start=len(game.players) >= MIN_PLAYERS
            )
            
            players_text = "\n".join([f"• @{p.username}" for p in game.players.values()])
            
            text = (
                f"🎮 **ЛОББИ**\n\n"
                f"**Игроков:** {len(game.players)}/{MAX_PLAYERS}\n"
                f"{players_text}"
            )
            
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except:
                pass
    else:
        await callback.answer("⚠️ Вы не в лобби", show_alert=True)

@router.callback_query(F.data == "begin_game")
async def begin_game_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if callback.from_user.id != game.host_id:
        await callback.answer("⚠️ Только хост может начать игру!", show_alert=True)
        return
    
    if len(game.players) < MIN_PLAYERS:
        await callback.answer(f"⚠️ Недостаточно игроков! Минимум: {MIN_PLAYERS}", show_alert=True)
        return
    
    await start_game(callback.message.bot, game)
    await callback.answer()

async def auto_start_game(bot, chat_id: int):
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    await start_game(bot, game)

async def start_game(bot, game):
    locations = [
        {"name": "Самолёт", "hints": ["— Здесь тесно", "— Много пассажиров", "— В небе"]},
        {"name": "Банк", "hints": ["— Есть сейф", "— Работают с деньгами", "— Охрана"]},
        {"name": "Пляж", "hints": ["— Жарко", "— Много песка", "— Вода рядом"]},
        {"name": "Казино", "hints": ["— Азартные игры", "— Шумно", "— Много денег"]},
        {"name": "Больница", "hints": ["— Врачи", "— Чисто", "— Лекарства"]},
        {"name": "Ресторан", "hints": ["— Еда", "— Официанты", "— Меню"]},
        {"name": "Школа", "hints": ["— Дети", "— Уроки", "— Доска"]},
        {"name": "Кинотеатр", "hints": ["— Темно", "— Экран", "— Попкорн"]},
    ]
    
    game.stop_timer()
    game.assign_roles(locations)
    game.state = GameState.QUESTIONS
    
    await bot.send_message(
        game.chat_id,
        "🎮 Игра началась! Роли розданы. Проверьте личные сообщения!"
    )
    
    for player in game.players.values():
        try:
            if player.user_id == game.spy_id:
                await bot.send_message(
                    player.user_id,
                    "🕵️ **ВЫ — ШПИОН!**\n\n"
                    "Вы не знаете локацию.\n"
                    "Ваша задача: остаться незамеченным или угадать локацию.\n\n"
                    "💡 Слушайте вопросы внимательно!"
                )
            else:
                hints_text = "\n".join(game.get_hints(player))
                await bot.send_message(
                    player.user_id,
                    f"🔍 **ВЫ — АГЕНТ**\n\n"
                    f"📍 **Локация:** {game.location['name']}\n\n"
                    f"**Подсказки:**\n{hints_text}\n\n"
                    f"💡 Задавайте нейтральные вопросы!"
                )
        except:
            await bot.send_message(
                game.chat_id,
                f"⚠️ Не могу отправить сообщение @{player.username}. "
                "Начните диалог с ботом: /start"
            )
    
    # Импортируем функцию для отправки кнопок вопросов
    from handlers.game import send_questions_keyboard
    await send_questions_keyboard(bot, game)

@router.message(Command("roles"))
async def cmd_roles(message: Message):
    text = """
🎭 **РОЛИ В ИГРЕ:**

**🕵️ Шпион**
• Не знает локацию
• Должен остаться незамеченным
• Может угадать локацию при вскрытии

**🔍 Агент**
• Знает локацию
• Должен вычислить шпиона
• Задаёт нейтральные вопросы
    """
    await message.answer(text)

@router.callback_query(F.data == "game_status")
async def game_status_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Нет активной игры", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    state_names = {
        GameState.LOBBY: "Набор игроков",
        GameState.QUESTIONS: "Фаза вопросов",
        GameState.VOTING: "Голосование",
        GameState.SPY_GUESS: "Шпион угадывает",
        GameState.FINISHED: "Завершена"
    }
    
    players_list = "\n".join([f"• @{p.username}" for p in game.players.values()])
    
    text = (
        f"📊 **СТАТУС ИГРЫ**\n\n"
        f"**Состояние:** {state_names[game.state]}\n"
        f"**Игроков:** {len(game.players)}\n\n"
        f"**Участники:**\n{players_list}\n\n"
        f"**Вопросов:** {len(game.questions)}\n"
        f"**Проголосовало:** {len(game.votes)}/{len(game.players)}"
    )
    
    await callback.answer()
    await callback.message.answer(text)

@router.callback_query(F.data == "show_leaderboard")
async def show_leaderboard_callback(callback: CallbackQuery):
    leaderboard = await db.get_leaderboard(10)
    
    if not leaderboard:
        await callback.answer("📊 Таблица лидеров пуста", show_alert=True)
        return
    
    lines = []
    for i, player in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        winrate = (player['total_wins'] / player['total_games'] * 100) if player['total_games'] > 0 else 0
        
        lines.append(
            f"{medal} @{player['username']}\n"
            f"   Очки: {player['total_points']} | "
            f"Игр: {player['total_games']} | "
            f"Побед: {player['total_wins']} ({winrate:.0f}%)"
        )
    
    scoreboard = "\n\n".join(lines)
    
    await callback.message.answer(f"🏆 **ТАБЛИЦА ЛИДЕРОВ:**\n\n{scoreboard}")
    await callback.answer()
