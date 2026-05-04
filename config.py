import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]

MIN_PLAYERS = 3
MAX_PLAYERS = 10

POINTS_AGENTS_WIN = 3
POINTS_AGENTS_LOCATION = 1
POINTS_SPY_HIDDEN = 5
POINTS_SPY_GUESS = 3

DB_PATH = os.getenv('DB_PATH', 'spy_game.db')
