from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import random
import asyncio

class GameState(Enum):
    LOBBY = "lobby"
    QUESTIONS = "questions"
    VOTING = "voting"
    SPY_GUESS = "spy_guess"
    FINISHED = "finished"

class Role(Enum):
    SPY = "spy"
    AGENT = "agent"

@dataclass
class Player:
    user_id: int
    username: str
    role: Optional[Role] = None
    points: int = 0
    voted_for: Optional[int] = None
    questions_asked: int = 0

@dataclass
class Question:
    from_user: int
    to_user: int
    question: str
    answer: Optional[str] = None

@dataclass
class Game:
    chat_id: int
    mode: str = "classic"
    episode: int = 1
    state: GameState = GameState.LOBBY
    players: Dict[int, Player] = field(default_factory=dict)
    location: Optional[Dict] = None
    spy_id: Optional[int] = None
    questions: List[Question] = field(default_factory=list)
    votes: Dict[int, int] = field(default_factory=dict)
    host_id: Optional[int] = None
    timer_task: Optional[asyncio.Task] = None
    time_left: int = 0
    
    def add_player(self, player: Player) -> bool:
        if player.user_id not in self.players:
            self.players[player.user_id] = player
            if self.host_id is None:
                self.host_id = player.user_id
            return True
        return False
    
    def remove_player(self, user_id: int) -> bool:
        if user_id in self.players and self.state == GameState.LOBBY:
            del self.players[user_id]
            if user_id == self.host_id and self.players:
                self.host_id = list(self.players.keys())[0]
            return True
        return False
    
    def start_game(self, location: Dict, spy_id: int):
        self.location = location
        self.spy_id = spy_id
        self.state = GameState.QUESTIONS
        
        for player in self.players.values():
            if player.user_id == spy_id:
                player.role = Role.SPY
            else:
                player.role = Role.AGENT
    
    def get_hints(self, player: Player) -> List[str]:
        if not self.location or player.role == Role.SPY:
            return []
        return self.location.get('roles', [])
    
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
        suspects = [uid for uid, votes in vote_counts.items() if votes == max_votes]
        if len(suspects) > 1:
            return None
        return suspects[0]
    
    def calculate_points(self, agents_win: bool, location_guessed: bool = False):
        for player in self.players.values():
            if player.role == Role.SPY:
                if not agents_win:
                    player.points += 10
                elif location_guessed:
                    player.points += 5
            else:
                if agents_win:
                    player.points += 5
                    if not location_guessed:
                        player.points += 3
                
                if player.questions_asked >= 2:
                    player.points += 2
    
    def stop_timer(self):
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
