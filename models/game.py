from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import time
import asyncio
import random

class GameState(Enum):
    LOBBY = "lobby"
    QUESTIONS = "questions"
    VOTING = "voting"
    SPY_GUESS = "spy_guess"
    FINISHED = "finished"

class GameMode(Enum):
    CLASSIC = "classic"
    CAMPAIGN = "campaign"

class Role(Enum):
    SPY = "spy"
    AGENT = "agent"
    ANALYST = "analyst"
    COUNTER_INTEL = "counter_intel"
    MISINFORMER = "misinformer"

@dataclass
class Player:
    user_id: int
    username: str
    role: Optional[Role] = None
    points: int = 0
    questions_asked: int = 0
    warnings: int = 0
    hints: List[str] = field(default_factory=list)

@dataclass
class Question:
    from_user: int
    to_user: int
    question: str
    answer: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

class Game:
    def __init__(self, chat_id: int, host_id: int, mode: GameMode = GameMode.CLASSIC):
        self.chat_id = chat_id
        self.host_id = host_id
        self.mode = mode
        self.state = GameState.LOBBY
        
        self.players: Dict[int, Player] = {}
        self.location: Optional[Dict] = None
        self.spy_id: Optional[int] = None
        self.special_roles: Dict[str, int] = {}
        
        self.questions: List[Question] = []
        self.votes: Dict[int, int] = {}
        
        self.episode: int = 1
        self.timer_task: Optional[asyncio.Task] = None
        self.start_time: Optional[float] = None
    
    def add_player(self, player: Player, max_players: int) -> bool:
        if len(self.players) >= max_players:
            return False
        self.players[player.user_id] = player
        return True
    
    def remove_player(self, user_id: int) -> bool:
        if user_id in self.players:
            del self.players[user_id]
            return True
        return False
    
    def start_game(self, location: Dict, spy_id: int, special_roles: Dict[str, int] = None):
        self.location = location
        self.spy_id = spy_id
        self.special_roles = special_roles or {}
        self.state = GameState.QUESTIONS
        self.start_time = time.time()
        
        for player in self.players.values():
            if player.user_id == spy_id:
                player.role = Role.SPY
            elif player.user_id == special_roles.get('analyst'):
                player.role = Role.ANALYST
            elif player.user_id == special_roles.get('counter_intel'):
                player.role = Role.COUNTER_INTEL
            elif player.user_id == special_roles.get('misinformer'):
                player.role = Role.MISINFORMER
            else:
                player.role = Role.AGENT
    
    def get_hints(self, player: Player) -> List[str]:
        if not self.location or player.role == Role.SPY:
            return []
        
        hints = self.location.get('hints', [])
        
        if player.role == Role.ANALYST:
            return random.sample(hints, min(3, len(hints)))
        elif player.role == Role.COUNTER_INTEL:
            return random.sample(hints, min(2, len(hints)))
        elif player.role == Role.MISINFORMER:
            wrong_hints = ["Здесь много людей", "Это закрытое помещение", "Здесь есть техника"]
            return random.sample(wrong_hints, 2)
        else:
            return random.sample(hints, min(2, len(hints)))
    
    def add_warning(self, user_id: int) -> int:
        if user_id in self.players:
            self.players[user_id].warnings += 1
            return self.players[user_id].warnings
        return 0
    
    def count_votes(self) -> Dict[int, int]:
        vote_counts = {}
        for voted_for in self.votes.values():
            vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
        return vote_counts
    
    def get_suspected_spy(self) -> Optional[int]:
        vote_counts = self.count_votes()
        if not vote_counts:
            return None
        
        max_votes = max(vote_counts.values())
        suspects = [user_id for user_id, count in vote_counts.items() if count == max_votes]
        
        if len(suspects) == 1:
            return suspects[0]
        return None
    
    def calculate_points(self, agents_win: bool, location_guessed: bool = False):
        from config import (
            POINTS_AGENTS_WIN, POINTS_SPY_SURVIVE, 
            POINTS_SPY_GUESS_LOCATION, POINTS_ACTIVE_PLAYER,
            PENALTY_DIRECT_LOCATION
        )
        
        for player in self.players.values():
            if player.role == Role.SPY:
                if not agents_win:
                    player.points += POINTS_SPY_SURVIVE
                elif location_guessed:
                    player.points += POINTS_SPY_GUESS_LOCATION
            else:
                if agents_win:
                    player.points += POINTS_AGENTS_WIN
            
            if player.questions_asked > 0:
                player.points += POINTS_ACTIVE_PLAYER
            
            player.points -= player.warnings * PENALTY_DIRECT_LOCATION
            player.points = max(0, player.points)
    
    def stop_timer(self):
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
    
    def reset(self):
        self.stop_timer()
        self.state = GameState.FINISHED
        self.questions.clear()
        self.votes.clear()
