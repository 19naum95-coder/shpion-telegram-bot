from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
import re

from models.game import GameState, Role, Question
from handlers.lobby import active_games
from database import Database

router = Router()
db = Database()

# Генерация клавиатуры с игроками (для вопросов)
def get_players_keyboard(game, exclude_user_id: int):
    buttons = []
    for player in game.players.values():
        if player.user_id != exclude_user_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"❓ {player.username}",
                    callback_data=f"ask_{player.user_id}"
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Генерация клавиатуры для голосования
def get_vote_keyboard(game, exclude_user_id: int):
    buttons = []
    for player in game.players.values():
        if player.user_id != exclude_user_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗳️ {player.username}",
                    callback_data=f"vote_{player.user_id}"
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("hint"))
async def cmd_hint(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id not in active_games:
        await message.answer("⚠️ Нет активной игры.")
        return
    
    game = active_games[chat_id]
    
    if user_id not in game.players:
        await message.answer("⚠️ Вы не участвуете в игре!")
        return
    
    player = game.players[user_id]
    
    try:
        if player.user_id == game.spy_id:
            await message.bot.send_message(
                user_id,
                "🕵️ Вы — ШПИОН! Локация вам неизвестна."
            )
        else:
            hints_text = "\n".join(game.get_hints(player))
            await message.bot.send_message(
                user_id,
                f"🔍 Вы — АГЕНТ\n📍 Локация: {game.location['name']}\n\n{hints_text}"
            )
        
        await message.answer("✅ Проверьте личные сообщения!")
    except:
        await message.answer("⚠️ Не могу отправить вам сообщение. Напишите боту /start")

@router.message(Command("ask"))
async def cmd_ask(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.QUESTIONS:
        await message.answer("⚠️ Сейчас не фаза вопросов!")
        return
    
    if message.from_user.id not in game.players:
        return
    
    # Показываем кнопки с игроками
    keyboard = get_players_keyboard(game, message.from_user.id)
    
    await message.answer(
        "❓ Кому хотите задать вопрос?",
        reply_markup=keyboard
    )

# Обработка нажатия на кнопку выбора игрока для вопроса
@router.callback_query(F.data.startswith("ask_"))
async def process_ask_callback(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена")
        return
    
    game = active_games[chat_id]
    target_id = int(callback.data.split("_")[1])
    
    # Сохраняем выбранного игрока в состояние
    await state.update_data(ask_target=target_id)
    
    target_username = game.players[target_id].username
    
    await callback.message.edit_text(
        f"❓ Вы выбрали: @{target_username}\n\n"
        f"Теперь напишите ваш вопрос:"
    )
    
    await callback.answer()

# Обработка текстового вопроса после выбора игрока
@router.message(F.text, lambda m: m.chat.id in active_games and active_games[m.chat.id].state == GameState.QUESTIONS)
async def process_question_text(message: Message, state: FSMContext):
    chat_id = message.chat.id
    game = active_games[chat_id]
    
    if message.from_user.id not in game.players:
        return
    
    # Проверяем есть ли выбранный игрок
    user_data = await state.get_data()
    target_id = user_data.get('ask_target')
    
    if not target_id:
        await message.answer("⚠️ Сначала выберите игрока командой /ask")
        return
    
    question_text = message.text.strip()
    
    if not question_text or question_text.startswith('/'):
        return
    
    question = Question(
        from_user=message.from_user.id,
        to_user=target_id,
        question=question_text
    )
    game.questions.append(question)
    
    # Очищаем состояние
    await state.clear()
    
    await message.answer(
        f"❓ @{message.from_user.username} → @{game.players[target_id].username}:\n"
        f'"{question_text}"\n\n'
        f"Ожидаем ответ..."
    )

@router.message(Command("answer"))
async def cmd_answer(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.QUESTIONS:
        await message.answer("⚠️ Сейчас не фаза вопросов!")
        return
    
    user_questions = [
        q for q in game.questions 
        if q.to_user == message.from_user.id and q.answer is None
    ]
    
    if not user_questions:
        await message.answer("⚠️ Нет вопросов к вам!")
        return
    
    question = user_questions[-1]
    answer_text = message.text[8:].strip()
    
    if not answer_text:
        await message.answer("⚠️ Напишите ответ после команды!")
        return
    
    question.answer = answer_text
    
    await message.answer(
        f"💬 @{message.from_user.username} ответил:\n"
        f'"{answer_text}"'
    )

@router.message(Command("vote"))
async def cmd_vote(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.VOTING:
        await message.answer("⚠️ Сейчас не фаза голосования! Используйте /endquestions")
        return
    
    if message.from_user.id not in game.players:
        return
    
    # Показываем кнопки с игроками
    keyboard = get_vote_keyboard(game, message.from_user.id)
    
    await message.answer(
        "🗳️ За кого голосуете?",
        reply_markup=keyboard
    )

# Обработка голосования через кнопку
@router.callback_query(F.data.startswith("vote_"))
async def process_vote_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена")
        return
    
    game = active_games[chat_id]
    target_id = int(callback.data.split("_")[1])
    
    game.votes[callback.from_user.id] = target_id
    
    await callback.message.edit_text(
        f"✅ Ваш голос принят: @{game.players[target_id].username}"
    )
    
    await callback.answer("✅ Голос засчитан!")
    
    # Проверяем все ли проголосовали
    if len(game.votes) == len(game.players):
        await finish_voting(callback.message, game)
    else:
        remaining = len(game.players) - len(game.votes)
        await callback.message.chat.send_message(
            f"Ожидаем ещё {remaining} голос(ов)..."
        )

async def finish_voting(message: Message, game):
    suspected_spy_id = game.get_suspected_spy()
    
    if not suspected_spy_id:
        await message.answer("⚠️ Ничья! Никто не получил голосов.")
        await end_game(message, game, spy_wins=True)
        return
    
    vote_counts = game.count_votes()
    
    results = "\n".join([
        f"@{game.players[uid].username}: {count} голос(ов)"
        for uid, count in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
    ])
    
    await message.answer(f"📊 Результаты голосования:\n\n{results}")
    
    if suspected_spy_id == game.spy_id:
        game.state = GameState.SPY_GUESS
        
        try:
            await message.bot.send_message(
                game.spy_id,
                "🎯 Вас раскрыли! Попробуйте угадать локацию: /guess название"
            )
        except:
            pass
        
        await message.answer(
            f"🎯 @{game.players[suspected_spy_id].username} - это шпион! "
            f"Ожидаем попытку угадать локацию..."
        )
    else:
        await message.answer(
            f"❌ Вы обвинили невиновного!\n"
            f"@{game.players[suspected_spy_id].username} был агентом.\n"
            f"Настоящий шпион: @{game.players[game.spy_id].username}"
        )
        await end_game(message, game, spy_wins=True)

@router.message(Command("guess"))
async def cmd_guess(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.SPY_GUESS:
        await message.answer("⚠️ Команда недоступна!")
        return
    
    if message.from_user.id != game.spy_id:
        await message.answer("⚠️ Только шпион может угадывать!")
        return
    
    guess = message.text[7:].strip().lower()
    
    if not guess:
        await message.answer("⚠️ Напишите локацию после команды!")
        return
    
    correct_location = game.location['name'].lower()
    
    location_guessed = guess in correct_location or correct_location in guess
    
    if location_guessed:
        await message.answer(f"✅ Верно! Шпион угадал: {game.location['name']}")
        await end_game(message, game, spy_wins=False, location_guessed=True)
    else:
        await message.answer(
            f"❌ Неверно!\n"
            f"Шпион угадал: {guess}\n"
            f"Правильно: {game.location['name']}"
        )
        await end_game(message, game, spy_wins=False, location_guessed=False)

async def end_game(message: Message, game, spy_wins: bool, location_guessed: bool = False):
    game.state = GameState.FINISHED
    game.calculate_points(not spy_wins, location_guessed)
    
    for player in game.players.values():
        role = 'spy' if player.user_id == game.spy_id else 'agent'
        won = (spy_wins and role == 'spy') or (not spy_wins and role == 'agent')
        
        await db.update_player_stats(
            user_id=player.user_id,
            role=role,
            won=won,
            points=player.points
        )
    
    scoreboard = "\n".join([
        f"• @{p.username}: {p.points} очков"
        for p in sorted(game.players.values(), key=lambda x: x.points, reverse=True)
    ])
    
    result_msg = "🏆 Победа агентов!" if not spy_wins else "🕵️ Победа шпиона!"
    
    await message.answer(f"{result_msg}\n\n📊 Итоги:\n{scoreboard}")
    
    del active_games[game.chat_id]

@router.message(Command("endquestions"))
async def cmd_end_questions(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        return
    
    game = active_games[chat_id]
    
    if game.state != GameState.QUESTIONS:
        return
    
    min_questions = len(game.players)
    if len(game.questions) < min_questions:
        await message.answer(f"⚠️ Недостаточно вопросов! Минимум: {min_questions}")
        return
    
    game.state = GameState.VOTING
    
    await message.answer(
        "🗳️ Фаза голосования началась!\n"
        "Проголосуйте за подозреваемого: /vote"
    )

@router.message(Command("status"))
async def cmd_status(message: Message):
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        await message.answer("⚠️ Нет активной игры.")
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
        f"📊 Статус игры\n\n"
        f"Состояние: {state_names[game.state]}\n"
        f"Игроков: {len(game.players)}\n\n"
        f"Участники:\n{players_list}\n\n"
        f"Вопросов: {len(game.questions)}\n"
        f"Проголосовало: {len(game.votes)}/{len(game.players)}"
    )
    
    await message.answer(text)

@router.message(Command("score"))
async def cmd_score(message: Message):
    leaderboard = await db.get_leaderboard(10)
    
    if not leaderboard:
        await message.answer("📊 Таблица лидеров пуста.")
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
    
    await message.answer(f"🏆 Таблица лидеров:\n\n{scoreboard}")
