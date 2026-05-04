from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
import asyncio

from models.game import GameState, Role, Question
from handlers.lobby import active_games
from database import Database
from config import TIMER_QUESTIONS, TIMER_VOTING, TIMER_SPY_GUESS

router = Router()
db = Database()

def get_players_keyboard(game, exclude_user_id: int):
    buttons = []
    for player in game.players.values():
        if player.user_id != exclude_user_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"❓ @{player.username}",
                    callback_data=f"ask_{player.user_id}"
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_vote_keyboard(game, exclude_user_id: int):
    buttons = []
    for player in game.players.values():
        if player.user_id != exclude_user_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗳️ @{player.username}",
                    callback_data=f"vote_{player.user_id}"
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def send_questions_keyboard(bot, game):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask_question")],
        [InlineKeyboardButton(text="💬 Ответить", callback_data="answer_question")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="questions_status")],
        [InlineKeyboardButton(text="✅ Завершить (Хост)", callback_data="end_questions")]
    ])
    
    text = f"❓ ФАЗА ВОПРОСОВ\n\nЗадавайте вопросы друг другу!\n\n⏱️ Время: {TIMER_QUESTIONS} сек"
    
    msg = await bot.send_message(game.chat_id, text, reply_markup=keyboard)
    game.timer_task = asyncio.create_task(questions_timer(bot, game, msg.message_id))

async def questions_timer(bot, game, message_id: int):
    try:
        for remaining in range(TIMER_QUESTIONS, 0, -30):
            await asyncio.sleep(30)
            if game.chat_id not in active_games or game.state != GameState.QUESTIONS:
                return
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask_question")],
                [InlineKeyboardButton(text="💬 Ответить", callback_data="answer_question")],
                [InlineKeyboardButton(text="📊 Статус", callback_data="questions_status")],
                [InlineKeyboardButton(text="✅ Завершить (Хост)", callback_data="end_questions")]
            ])
            
            text = f"❓ ФАЗА ВОПРОСОВ\n\nВопросов: {len(game.questions)}\n\n⏱️ Осталось: {remaining} сек"
            
            try:
                await bot.edit_message_text(text=text, chat_id=game.chat_id, message_id=message_id, reply_markup=keyboard)
            except:
                pass
        
        if game.chat_id in active_games and game.state == GameState.QUESTIONS:
            await auto_end_questions(bot, game)
    except asyncio.CancelledError:
        pass

async def auto_end_questions(bot, game):
    min_questions = len(game.players)
    if len(game.questions) < min_questions:
        await bot.send_message(game.chat_id, f"⏱️ Время вышло! Недостаточно вопросов. Игра завершена.")
        del active_games[game.chat_id]
        return
    game.state = GameState.VOTING
    await send_voting_keyboard(bot, game)

@router.callback_query(F.data == "ask_question")
async def ask_question_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    if game.state != GameState.QUESTIONS:
        await callback.answer("⚠️ Сейчас не фаза вопросов!", show_alert=True)
        return
    if callback.from_user.id not in game.players:
        await callback.answer("⚠️ Вы не участвуете!", show_alert=True)
        return
    keyboard = get_players_keyboard(game, callback.from_user.id)
    await callback.message.answer("❓ Кому задать вопрос?", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("ask_"))
async def process_ask_callback(callback: CallbackQuery, state: FSMContext):
    if callback.data == "ask_question":
        return
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    target_id = int(callback.data.split("_")[1])
    await state.update_data(ask_target=target_id)
    target_username = game.players[target_id].username
    await callback.message.edit_text(f"❓ Выбран: @{target_username}\n\nНапишите вопрос:")
    await callback.answer()

@router.message(F.text)
async def process_text_message(message: Message, state: FSMContext):
    chat_id = message.chat.id
    if chat_id not in active_games:
        return
    game = active_games[chat_id]
    if message.from_user.id not in game.players:
        return
    if message.text.startswith('/'):
        return
    
    user_data = await state.get_data()
    
    if game.state == GameState.QUESTIONS and 'ask_target' in user_data:
        target_id = user_data['ask_target']
        question_text = message.text.strip()
        question = Question(from_user=message.from_user.id, to_user=target_id, question=question_text)
        game.questions.append(question)
        game.players[message.from_user.id].questions_asked += 1
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Ответить", callback_data="answer_question")]])
        await message.answer(f"❓ @{message.from_user.username} → @{game.players[target_id].username}:\n\"{question_text}\"\n\n⏳ Ждём ответ...", reply_markup=keyboard)
        return
    
    if game.state == GameState.QUESTIONS and 'answering' in user_data:
        user_questions = [q for q in game.questions if q.to_user == message.from_user.id and q.answer is None]
        if user_questions:
            question = user_questions[-1]
            question.answer = message.text.strip()
            await message.answer(f"💬 @{message.from_user.username} ответил:\n\"{question.answer}\"")
            await state.clear()
        return
    
    if game.state == GameState.SPY_GUESS and 'guessing' in user_data:
        if message.from_user.id != game.spy_id:
            return
        guess = message.text.strip().lower()
        correct_location = game.location['name'].lower()
        location_guessed = guess in correct_location or correct_location in guess
        game.stop_timer()
        if location_guessed:
            await message.answer(f"✅ Верно! Локация: {game.location['name']}")
            await end_game(message.bot, game, spy_wins=False, location_guessed=True)
        else:
            await message.answer(f"❌ Неверно!\nШпион: {guess}\nПравильно: {game.location['name']}")
            await end_game(message.bot, game, spy_wins=False, location_guessed=False)
        await state.clear()

@router.callback_query(F.data == "answer_question")
async def answer_question_callback(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    user_questions = [q for q in game.questions if q.to_user == callback.from_user.id and q.answer is None]
    if not user_questions:
        await callback.answer("⚠️ Нет вопросов к вам!", show_alert=True)
        return
    question = user_questions[-1]
    from_username = game.players[question.from_user].username
    await callback.message.answer(f"💬 Вопрос от @{from_username}:\n\"{question.question}\"\n\nНапишите ответ:")
    await state.update_data(answering=True)
    await callback.answer()

@router.callback_query(F.data == "questions_status")
async def questions_status_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    answered = sum(1 for q in game.questions if q.answer is not None)
    text = f"📊 СТАТУС\n\nВопросов: {len(game.questions)}\nОтвечено: {answered}\nМинимум: {len(game.players)}"
    await callback.answer()
    await callback.message.answer(text)

@router.callback_query(F.data == "end_questions")
async def end_questions_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    if callback.from_user.id != game.host_id:
        await callback.answer("⚠️ Только хост!", show_alert=True)
        return
    min_questions = len(game.players)
    if len(game.questions) < min_questions:
        await callback.answer(f"⚠️ Мало вопросов! Минимум: {min_questions}", show_alert=True)
        return
    game.stop_timer()
    game.state = GameState.VOTING
    await send_voting_keyboard(callback.message.bot, game)
    await callback.answer()

async def send_voting_keyboard(bot, game):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳️ Проголосовать", callback_data="start_vote")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="voting_status")]
    ])
    text = f"🗳️ ФАЗА ГОЛОСОВАНИЯ\n\nГолосуйте за подозреваемого!\n\n⏱️ Время: {TIMER_VOTING} сек"
    msg = await bot.send_message(game.chat_id, text, reply_markup=keyboard)
    game.timer_task = asyncio.create_task(voting_timer(bot, game, msg.message_id))

async def voting_timer(bot, game, message_id: int):
    try:
        for remaining in range(TIMER_VOTING, 0, -15):
            await asyncio.sleep(15)
            if game.chat_id not in active_games or game.state != GameState.VOTING:
                return
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗳️ Проголосовать", callback_data="start_vote")],
                [InlineKeyboardButton(text="📊 Статус", callback_data="voting_status")]
            ])
            text = f"🗳️ ГОЛОСОВАНИЕ\n\nПроголосовало: {len(game.votes)}/{len(game.players)}\n\n⏱️ Осталось: {remaining} сек"
            try:
                await bot.edit_message_text(text=text, chat_id=game.chat_id, message_id=message_id, reply_markup=keyboard)
            except:
                pass
        if game.chat_id in active_games and game.state == GameState.VOTING:
            if len(game.votes) > 0:
                await finish_voting(bot, game)
            else:
                await bot.send_message(game.chat_id, "⏱️ Никто не проголосовал!")
                del active_games[game.chat_id]
    except asyncio.CancelledError:
        pass

@router.callback_query(F.data == "start_vote")
async def start_vote_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    if callback.from_user.id not in game.players:
        await callback.answer("⚠️ Вы не участвуете!", show_alert=True)
        return
    if callback.from_user.id in game.votes:
        await callback.answer("⚠️ Уже проголосовали!", show_alert=True)
        return
    keyboard = get_vote_keyboard(game, callback.from_user.id)
    await callback.message.answer("🗳️ За кого голосуете?", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("vote_"))
async def process_vote_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    target_id = int(callback.data.split("_")[1])
    game.votes[callback.from_user.id] = target_id
    await callback.message.edit_text(f"✅ Голос за: @{game.players[target_id].username}")
    await callback.answer("✅ Голос засчитан!")
    if len(game.votes) == len(game.players):
        game.stop_timer()
        await finish_voting(callback.message.bot, game)
    else:
        remaining = len(game.players) - len(game.votes)
        await callback.message.bot.send_message(chat_id, f"⏳ Ждём ещё {remaining} голос(ов)...")

@router.callback_query(F.data == "voting_status")
async def voting_status_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    text = f"📊 СТАТУС\n\nПроголосовало: {len(game.votes)}/{len(game.players)}\nОсталось: {len(game.players) - len(game.votes)}"
    await callback.answer()
    await callback.message.answer(text)

async def finish_voting(bot, game):
    suspected_spy_id = game.get_suspected_spy()
    if not suspected_spy_id:
        await bot.send_message(game.chat_id, "⚠️ Ничья!")
        await end_game(bot, game, spy_wins=True)
        return
    vote_counts = game.count_votes()
    results = "\n".join([f"@{game.players[uid].username}: {count}" for uid, count in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)])
    await bot.send_message(game.chat_id, f"📊 РЕЗУЛЬТАТЫ:\n\n{results}")
    if suspected_spy_id == game.spy_id:
        game.state = GameState.SPY_GUESS
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎯 Угадать", callback_data="spy_guess")]])
        try:
            await bot.send_message(game.spy_id, f"🎯 ВАС РАСКРЫЛИ!\n\nУгадайте локацию!\n⏱️ {TIMER_SPY_GUESS} сек", reply_markup=keyboard)
        except:
            pass
        await bot.send_message(game.chat_id, f"🎯 @{game.players[suspected_spy_id].username} - шпион!\n⏳ Ждём попытку...")
        game.timer_task = asyncio.create_task(spy_guess_timer(bot, game))
    else:
        await bot.send_message(game.chat_id, f"❌ Ошиблись!\n@{game.players[suspected_spy_id].username} - агент.\nШпион: @{game.players[game.spy_id].username}")
        await end_game(bot, game, spy_wins=True)

async def spy_guess_timer(bot, game):
    try:
        await asyncio.sleep(TIMER_SPY_GUESS)
        if game.chat_id in active_games and game.state == GameState.SPY_GUESS:
            await bot.send_message(game.chat_id, "⏱️ Время вышло!")
            await end_game(bot, game, spy_wins=False, location_guessed=False)
    except asyncio.CancelledError:
        pass

@router.callback_query(F.data == "spy_guess")
async def spy_guess_callback(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    if chat_id not in active_games:
        await callback.answer("⚠️ Игра не найдена", show_alert=True)
        return
    game = active_games[chat_id]
    if callback.from_user.id != game.spy_id:
        await callback.answer("⚠️ Только шпион!", show_alert=True)
        return
    await callback.message.edit_text("🎯 Напишите локацию:")
    await state.update_data(guessing=True)
    await callback.answer()

async def end_game(bot, game, spy_wins: bool, location_guessed: bool = False):
    game.state = GameState.FINISHED
    game.stop_timer()
    game.calculate_points(not spy_wins, location_guessed)
    for player in game.players.values():
        role = 'spy' if player.user_id == game.spy_id else 'agent'
        won = (spy_wins and role == 'spy') or (not spy_wins and role == 'agent')
        await db.update_player_stats(user_id=player.user_id, role=role, won=won, points=player.points)
    scoreboard = "\n".join([f"• @{p.username}: {p.points}" for p in sorted(game.players.values(), key=lambda x: x.points, reverse=True)])
    result_msg = "🏆 Победа агентов!" if not spy_wins else "🕵️ Победа шпиона!"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Новая игра", callback_data="new_game")],
        [InlineKeyboardButton(text="🏆 Лидеры", callback_data="show_leaderboard")]
    ])
    await bot.send_message(game.chat_id, f"{result_msg}\n\n📊 ИТОГИ:\n{scoreboard}", reply_markup=keyboard)
    del active_games[game.chat_id]

@router.callback_query(F.data == "new_game")
async def new_game_callback(callback: CallbackQuery):
    from handlers.lobby import cmd_start_game
    message = callback.message
    message.from_user = callback.from_user
    await cmd_start_game(message)
    await callback.answer()

@router.message(Command("hint"))
async def cmd_hint(message: Message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        return
    game = active_games[chat_id]
    if message.from_user.id not in game.players:
        return
    player = game.players[message.from_user.id]
    try:
        if player.user_id == game.spy_id:
            await message.bot.send_message(message.from_user.id, "🕵️ Вы — ШПИОН!")
        else:
            hints = "\n".join(game.get_hints(player))
            await message.bot.send_message(message.from_user.id, f"🔍 АГЕНТ\n📍 {game.location['name']}\n\n{hints}")
        await message.answer("✅ Проверьте ЛС!")
await message.answer("⚠️ Не могу отправить ЛС. Напишите боту /start")

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
    text = f"📊 СТАТУС ИГРЫ\n\nСостояние: {state_names[game.state]}\nИгроков: {len(game.players)}\n\nУчастники:\n{players_list}\n\nВопросов: {len(game.questions)}\nПроголосовало: {len(game.votes)}/{len(game.players)}"
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
        lines.append(f"{medal} @{player['username']}\n   Очки: {player['total_points']} | Игр: {player['total_games']} | Побед: {player['total_wins']} ({winrate:.0f}%)")
    scoreboard = "\n\n".join(lines)
    await message.answer(f"🏆 ТАБЛИЦА ЛИДЕРОВ:\n\n{scoreboard}")
