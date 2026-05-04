from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from models.game import Game, GameState
from database import Database
from config import MIN_PLAYERS, MAX_PLAYERS, ADMIN_IDS
import random

router = Router()
db = Database()

active_games = {}

class GameStates(StatesGroup):
    in_game = State()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await db.create_player(message.from_user.id, message.from_user.username)
    
    text = (
        "Привет! Я бот для игры «Шпион». "
        "Соберите от 3 игроков, раздайте роли и вычислите шпиона. "
        "Готовы? Создайте лобби или присоединяйтесь к существующему. "
        "/help — правила и команды."
    )
    await message.answer(text)

@router.message(Command("help"))
async def cmd_help(message: Message):
    text = """
📖 **ПРАВИЛА ИГРЫ:**

Один игрок - Шпион (не знает локацию)
Остальные - Агенты (знают локацию)

🎯 **ЦЕЛЬ:**
• Агенты: вычислить шпиона
• Шпион: остаться незамеченным или угадать локацию

📝 **КАК ИГРАТЬ:**
1. /startgame - создать игру
2. /join - присоединиться (минимум 3 игрока)
3. /begin - начать (только хост)
4. Задавайте вопросы: /ask @username вопрос
5. Отвечайте: /answer текст
6. Голосуйте: /vote @username
7. Шпион угадывает: /guess локация

⚙️ **КОМАНДЫ:**
/startgame - создать игру
/join - присоединиться
/leave - выйти из лобби
/begin - начать игру
/hint - напомнить роль
/status - статус игры
/score - таблица лидеров
/roles - информация о ролях
    """
    await message.answer(text, parse_mode="Markdown")

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
    
    text = (
        f"[Шпион] Лобби #{chat_id} создано хостом @{message.from_user.username}. "
        f"Режим: classic. Игроков: 0. "
        f"Присоединяйтесь: /join. Минимум {MIN_PLAYERS}, максимум {MAX_PLAYERS}."
    )
    await message.answer(text)

@router.message(Command("join"))
async def cmd_join(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        await message.answer("⚠️ Нет активной игры. Создайте: /startgame")
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.LOBBY:
        await message.answer("⚠️ Игра уже началась!")
        return
    
    if game.add_player(message.from_user.id, message.from_user.username):
        remaining = MIN_PLAYERS - len(game.players)
        text = (
            f"[Шпион] @{message.from_user.username} присоединился. "
            f"В лобби {len(game.players)} игроков. "
        )
        if remaining > 0:
            text += f"Ожидаем ещё минимум {remaining}."
        else:
            text += "Можно начинать! /begin"
        
        await message.answer(text)
    else:
        await message.answer("⚠️ Вы уже в игре или лобби переполнено!")

@router.message(Command("leave"))
async def cmd_leave(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if game.remove_player(message.from_user.id):
        await message.answer(f"@{message.from_user.username} покинул лобби.")
        
        if len(game.players) == 0:
            del active_games[chat_id]
            await message.answer("Лобби закрыто (нет игроков).")

@router.message(Command("begin"))
async def cmd_begin(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        await message.answer("⚠️ Нет активной игры!")
        return
    
    game = active_games[chat_id]
    
    if message.from_user.id != game.host_id:
        await message.answer("⚠️ Только хост может начать игру!")
        return
    
    if len(game.players) < MIN_PLAYERS:
        await message.answer(f"⚠️ Недостаточно игроков! Минимум: {MIN_PLAYERS}")
        return
    
    locations = [
        {"name": "Самолёт", "hints": ["— Здесь тесно", "— Много пассажиров"]},
        {"name": "Банк", "hints": ["— Есть сейф", "— Работают с деньгами"]},
        {"name": "Пляж", "hints": ["— Жарко", "— Много песка"]},
        {"name": "Казино", "hints": ["— Азартные игры", "— Шумно"]},
        {"name": "Больница", "hints": ["— Врачи", "— Чисто"]},
    ]
    
    game.assign_roles(locations)
    game.state = GameState.QUESTIONS
    
    await message.answer("🎮 Игра началась! Роли розданы. Проверьте личные сообщения!")
    
    for player in game.players.values():
        try:
            if player.user_id == game.spy_id:
                await message.bot.send_message(
                    player.user_id,
                    "🕵️ Вы — ШПИОН! Вы не знаете локацию. Ваша задача: остаться незамеченным."
                )
            else:
                hints_text = "\n".join(game.get_hints(player))
                await message.bot.send_message(
                    player.user_id,
                    f"🔍 Вы — АГЕНТ.\n\n📍 Локация: {game.location['name']}\n\n{hints_text}"
                )
        except:
            await message.answer(
                f"⚠️ Не могу отправить сообщение @{player.username}. "
                "Убедитесь что начали диалог с ботом: /start"
            )

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
    await message.answer(text, parse_mode="Markdown")
