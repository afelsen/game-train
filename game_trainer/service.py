from __future__ import annotations

import random
from dataclasses import dataclass
from uuid import uuid4

from game_trainer.poker import Action, HandState
from game_trainer.providers import ProviderRegistry, StrategyRequest, StrategyResponse


@dataclass
class GameSession:
    session_id: str
    hand: HandState
    next_request_number: int = 1


class GameService:
    """In-memory authority for hands and provider requests."""

    def __init__(self, providers: ProviderRegistry) -> None:
        self.providers = providers
        self._sessions: dict[str, GameSession] = {}

    def create_hand(self, *, seed: int, button: int = 0, starting_stacks: tuple[int, ...] = (10_000,) * 6) -> GameSession:
        session_id = f"hand-{uuid4().hex[:12]}"
        session = GameSession(session_id, HandState(seed=seed, button=button, starting_stacks=starting_stacks))
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> GameSession:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise KeyError(f"unknown session: {session_id}") from error

    def observation(self, session_id: str, seat: int) -> dict:
        return self.get(session_id).hand.observation(seat)

    def apply_action(self, session_id: str, action: Action) -> dict:
        session = self.get(session_id)
        session.hand.apply(action)
        return session.hand.to_dict()

    def strategy(self, session_id: str, provider_id: str) -> StrategyResponse:
        session = self.get(session_id)
        if session.hand.to_act is None:
            raise ValueError("hand has no acting player")
        request_id = f"{session_id}-strategy-{session.next_request_number:06d}"
        session.next_request_number += 1
        request = StrategyRequest.from_hand(session.hand, session.hand.to_act, request_id)
        return self.providers.strategy(provider_id, request)

    def apply_provider_action(self, session_id: str, provider_id: str, *, sample_seed: int) -> tuple[StrategyResponse, dict]:
        response = self.strategy(session_id, provider_id)
        if response.status != "ok" or not response.actions:
            raise ValueError(response.message or f"provider returned {response.status}")
        draw = random.Random(sample_seed).random()
        cumulative = 0.0
        selected = response.actions[-1]
        for candidate in response.actions:
            cumulative += candidate.probability
            if draw < cumulative:
                selected = candidate
                break
        if selected.legal_action is None:
            raise ValueError("selected strategy action has no legal mapping")
        state = self.apply_action(session_id, selected.legal_action)
        return response, state
