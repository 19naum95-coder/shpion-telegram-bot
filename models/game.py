from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import random

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
    
    def add_player(self, user_id: int, username: str) -> bool:
        from config import MAX_PLAYERS
        
        if len(self.players) >= MAX_PLAYERS:
            return False
        if user_id not in self.players:
            self.players[user_id] = Player(user_id, username)
            if self.host_id is None:
                self.host_id = user_id
            return True
        return False
    
    def remove_player(self, user_id: int) -> bool:
        if user_id in self.players and self.state == GameState.LOBBY:
            del self.players[user_id]
            if user_id == self.host_id and self.players:
                self.host_id = list(self.players.keys())[0]
            return True
        return False
    
    def assign_roles(self, locations_data: List[Dict]):
        player_list = list(self.players.values())
        random.shuffle(player_list)
        
        spy = player_list[0]
        spy.role = Role.SPY
        self.spy_id = spy.user_id
        
        for player in player_list[1:]:
            player.role = Role.AGENT
        
        self.location = random.choice(locations_data)
    
    def get_hints(self, player: Player) -> List[str]:
        if not self.location:
            return []
        return self.location.get('hints', [])
    
    def count_votes(self) -> Dict[int, int]:
        vote_counts = {}
        for voted_for in self.votes.values():
            vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
        return vote_counts
    
    def get_suspected_spy(self) -> Optional[int]:
        vote_counts = self.count_votes()
        if not vote_counts:
            return None
        return max(vote_counts.items(), key=lambda x: x[1])[0]
    
    def calculate_points(self, spy_caught: bool, location_guessed: bool = False):
        from config import (
            POINTS_AGENTS_WIN, POINTS_AGENTS_LOCATION,
            POINTS_SPY_HIDDEN, POINTS_SPY_GUESS
        )
        
        for player in self.players.values():
            if player.role == Role.SPY:
                if not spy_caught:
                    player.points += POINTS_SPY_HIDDEN
                elif location_guessed:
                    player.points += POINTS_SPY_GUESS
            else:
                if spy_caught:
                    player.points += POINTS_AGENTS_WIN
                    if not location_guessed:
                        player.points += POINTS_AGENTS_LOCATION
                
                if player.questions_asked >= 3:
                    player.points += 1
