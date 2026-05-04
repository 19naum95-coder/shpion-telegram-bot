import aiosqlite
import os

class Database:
    def __init__(self):
        self.db_path = os.getenv('DB_PATH', 'spy_game.db')
    
    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    total_games INTEGER DEFAULT 0,
                    total_wins INTEGER DEFAULT 0,
                    total_points INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS game_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    won INTEGER,
                    points INTEGER,
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS active_games (
                    chat_id INTEGER PRIMARY KEY,
                    state TEXT,
                    game_data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
    
    async def create_player(self, user_id: int, username: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO players (user_id, username)
                VALUES (?, ?)
            ''', (user_id, username))
            await db.commit()
    
    async def get_player(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM players WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def update_player_stats(self, user_id: int, role: str, won: bool, points: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE players 
                SET total_games = total_games + 1,
                    total_wins = total_wins + ?,
                    total_points = total_points + ?
                WHERE user_id = ?
            ''', (1 if won else 0, points, user_id))
            
            await db.execute('''
                INSERT INTO game_history (user_id, role, won, points)
                VALUES (?, ?, ?, ?)
            ''', (user_id, role, 1 if won else 0, points))
            
            await db.commit()
    
    async def get_leaderboard(self, limit: int = 10):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM players 
                ORDER BY total_points DESC 
                LIMIT ?
            ''', (limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def save_active_game(self, chat_id: int, state: str, game_data: dict):
        import json
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO active_games (chat_id, state, game_data)
                VALUES (?, ?, ?)
            ''', (chat_id, state, json.dumps(game_data)))
            await db.commit()
    
    async def delete_active_game(self, chat_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM active_games WHERE chat_id = ?', (chat_id,))
            await db.commit()
    
    async def get_total_players(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT COUNT(*) FROM players') as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def get_total_games(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT COUNT(*) FROM game_history') as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def get_all_players(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM players') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
