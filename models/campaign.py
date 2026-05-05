from dataclasses import dataclass
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class Achievement:
    id: str
    name: str
    description: str
    icon: str
    condition: str

ACHIEVEMENTS = [
    Achievement(
        id="first_win",
        name="Первая победа",
        description="Выиграйте первую игру",
        icon="🏆",
        condition="total_wins >= 1"
    ),
    Achievement(
        id="spy_master",
        name="Мастер шпионажа",
        description="Победите 10 раз в роли шпиона",
        icon="🕵️",
        condition="spy_wins >= 10"
    ),
    Achievement(
        id="agent_elite",
        name="Элитный агент",
        description="Победите 20 раз в роли агента",
        icon="🔍",
        condition="agent_wins >= 20"
    ),
    Achievement(
        id="interrogator",
        name="Следователь",
        description="Задайте 5 вопросов за одну игру",
        icon="❓",
        condition="questions_in_game >= 5"
    ),
    Achievement(
        id="perfect_agent",
        name="Безупречный агент",
        description="Победите без предупреждений",
        icon="⭐",
        condition="win_without_warnings == True"
    ),
    Achievement(
        id="campaign_veteran",
        name="Ветеран кампании",
        description="Пройдите все 5 эпизодов",
        icon="📖",
        condition="episodes_completed >= 5"
    ),
    Achievement(
        id="legend",
        name="Легенда",
        description="Наберите 1000 очков",
        icon="👑",
        condition="total_points >= 1000"
    )
]

@dataclass
class Episode:
    number: int
    title: str
    description: str
    location_pool: List[str]
    special_rules: Dict
    unlocks: List[str]

@dataclass
class CampaignProgress:
    chat_id: int
    current_episode: int = 1
    completed_episodes: List[int] = None
    unlocked_features: List[str] = None
    
    def __post_init__(self):
        if self.completed_episodes is None:
            self.completed_episodes = []
        if self.unlocked_features is None:
            self.unlocked_features = []

def load_episodes() -> List[Dict]:
    try:
        with open('data/episodes.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("❌ Файл episodes.json не найден!")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга episodes.json: {e}")
        return []

def get_episode(number: int) -> Optional[Dict]:
    episodes = load_episodes()
    for episode in episodes:
        if episode['number'] == number:
            return episode
    return None

def get_achievement(achievement_id: str) -> Optional[Achievement]:
    for achievement in ACHIEVEMENTS:
        if achievement.id == achievement_id:
            return achievement
    return None

def check_achievement_unlocked(achievement_id: str, player_stats: Dict) -> bool:
    achievement = get_achievement(achievement_id)
    if not achievement:
        return False
    
    try:
        return eval(achievement.condition, {"__builtins__": {}}, player_stats)
    except Exception as e:
        logger.error(f"❌ Ошибка проверки достижения {achievement_id}: {e}")
        return False
