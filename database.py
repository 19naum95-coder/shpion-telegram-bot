import asyncpg
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self, database_url: str):
        try:
            self.pool = await asyncpg.create_pool(database_url, min_size=5, max_size=20)
            logger.info("✅ Подключение к базе данных установлено")
            await self.create_tables()
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("База данных отключена")
    
    async def create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT NOT NULL,
                    total_points INTEGER DEFAULT 0,
                    season_points INTEGER DEFAULT 0,
                    total_games INTEGER DEFAULT 0,
                    total_wins INTEGER DEFAULT 0,
                    spy_games INTEGER DEFAULT 0,
                    spy_wins INTEGER DEFAULT 0,
                    agent_games INTEGER DEFAULT 0,
                    agent_wins INTEGER DEFAULT 0,
                    questions_asked INTEGER DEFAULT 0,
                    warnings INTEGER DEFAULT 0,
                    banned BOOLEAN DEFAULT FALSE,
                    ban_reason TEXT,
                    ban_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES players(user_id),
                    achievement_id TEXT NOT NULL,
                    unlocked_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, achievement_id)
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    chat_id BIGINT PRIMARY KEY,
                    current_episode INTEGER DEFAULT 1,
                    completed_episodes INTEGER[] DEFAULT ARRAY[]::INTEGER[],
                    unlocked_features TEXT[] DEFAULT ARRAY[]::TEXT[],
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS campaign_progress (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT,
                    user_id BIGINT REFERENCES players(user_id),
                    campaign_points INTEGER DEFAULT 0,
                    episodes_won INTEGER DEFAULT 0,
                    UNIQUE(chat_id, user_id)
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS game_history (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    game_mode TEXT NOT NULL,
                    episode INTEGER,
                    location TEXT NOT NULL,
                    spy_id BIGINT NOT NULL,
                    winner TEXT NOT NULL,
                    duration INTEGER,
                    questions_count INTEGER,
                    played_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS game_participants (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES game_history(id),
                    user_id BIGINT REFERENCES players(user_id),
                    role TEXT NOT NULL,
                    points_earned INTEGER DEFAULT 0,
                    questions_asked INTEGER DEFAULT 0,
                    warnings INTEGER DEFAULT 0
                )
            """)
            
            logger.info("✅ Таблицы созданы/проверены")
    
    async def ensure_player_exists(self, user_id: int, username: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO players (user_id, username, last_active)
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET username = $2, last_active = NOW()
            """, user_id, username)
    
    async def is_banned(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT banned, ban_until FROM players
                WHERE user_id = $1
            """, user_id)
            
            if not result:
                return False
            
            if not result['banned']:
                return False
            
            if result['ban_until'] and datetime.now() > result['ban_until']:
                await conn.execute("""
                    UPDATE players SET banned = FALSE, ban_until = NULL
                    WHERE user_id = $1
                """, user_id)
                return False
            
            return True
    
    async def ban_player(self, user_id: int, banned_by: int, reason: str = None, days: int = None):
        async with self.pool.acquire() as conn:
            expires_at = None
            if days:
                expires_at = datetime.now() + timedelta(days=days)
            
            await conn.execute("""
                UPDATE players 
                SET banned = TRUE, ban_reason = $2, ban_until = $3
                WHERE user_id = $1
            """, user_id, reason, expires_at)
    
    async def unban_player(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players 
                SET banned = FALSE, ban_reason = NULL, ban_until = NULL
                WHERE user_id = $1
            """, user_id)
    
    async def update_player_stats(self, user_id: int, role: str, won: bool, points: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET total_games = total_games + 1,
                    total_wins = total_wins + $2,
                    total_points = total_points + $3,
                    season_points = season_points + $3,
                    spy_games = spy_games + $4,
                    spy_wins = spy_wins + $5,
                    agent_games = agent_games + $6,
                    agent_wins = agent_wins + $7,
                    last_active = NOW()
                WHERE user_id = $1
            """, 
                user_id,
                1 if won else 0,
                points,
                1 if role == 'spy' else 0,
                1 if role == 'spy' and won else 0,
                1 if role != 'spy' else 0,
                1 if role != 'spy' and won else 0
            )
    
    async def add_questions_asked(self, user_id: int, count: int = 1):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET questions_asked = questions_asked + $2
                WHERE user_id = $1
            """, user_id, count)
    
    async def add_warning(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players
                SET warnings = warnings + 1
                WHERE user_id = $1
            """, user_id)
    
    async def get_player_stats(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM players WHERE user_id = $1
            """, user_id)
            return dict(row) if row else None
    
    async def get_leaderboard(self, limit: int = 10, season: bool = True) -> List[Dict]:
        async with self.pool.acquire() as conn:
            field = "season_points" if season else "total_points"
            rows = await conn.fetch(f"""
                SELECT user_id, username, total_points, season_points, 
                       total_games, total_wins, spy_wins, agent_wins
                FROM players
                WHERE banned = FALSE
                ORDER BY {field} DESC
                LIMIT $1
            """, limit)
            return [dict(row) for row in rows]
    
    async def unlock_achievement(self, user_id: int, achievement_id: str):
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO achievements (user_id, achievement_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                """, user_id, achievement_id)
                return True
            except:
                return False
    
    async def get_achievements(self, user_id: int) -> List[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT achievement_id FROM achievements
                WHERE user_id = $1
            """, user_id)
            return [row['achievement_id'] for row in rows]
    
    async def save_game_history(self, chat_id: int, game_mode: str, episode: int,
                                location: str, spy_id: int, winner: str,
                                duration: int, questions_count: int) -> int:
        async with self.pool.acquire() as conn:
            game_id = await conn.fetchval("""
                INSERT INTO game_history 
                (chat_id, game_mode, episode, location, spy_id, winner, duration, questions_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """, chat_id, game_mode, episode, location, spy_id, winner, duration, questions_count)
            return game_id
    
    async def save_game_participant(self, game_id: int, user_id: int, role: str,
                                    points_earned: int, questions_asked: int, warnings: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO game_participants 
                (game_id, user_id, role, points_earned, questions_asked, warnings)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, game_id, user_id, role, points_earned, questions_asked, warnings)
    
    async def get_campaign_progress(self, chat_id: int, user_id: int) -> Dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM campaign_progress
                WHERE chat_id = $1 AND user_id = $2
            """, chat_id, user_id)
            if row:
                return dict(row)
            await conn.execute("""
                INSERT INTO campaign_progress (chat_id, user_id)
                VALUES ($1, $2)
            """, chat_id, user_id)
            return {'campaign_points': 0, 'episodes_won': 0}
    
    async def update_campaign_progress(self, chat_id: int, user_id: int, points: int, won: bool):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE campaign_progress
                SET campaign_points = campaign_points + $3,
                    episodes_won = episodes_won + $4
                WHERE chat_id = $1 AND user_id = $2
            """, chat_id, user_id, points, 1 if won else 0)
    
    async def reset_season(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE players SET season_points = 0
            """)
            logger.info("🔄 Сезонные очки сброшены")
