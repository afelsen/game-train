from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from game_trainer.history import HandHistoryRepository
from game_trainer.equity import calculate_equity, calculate_hand_chances
from game_trainer.poker import Action, ActionType, IllegalAction
from game_trainer.providers import (
    CheckCallProvider,
    FullhouseExperimentalProvider,
    ProviderRegistry,
    UniformRandomProvider,
)
from game_trainer.service import GameService
from game_trainer.solver_jobs import SolverJobManager
from game_trainer.training_spots import curated_spots, seeded_random_spots
from game_trainer.training_jobs import TrainingJobManager


@dataclass(frozen=True)
class ApiResult:
    status: int
    body: dict[str, Any]


def build_service(repository_root: Path, include_fullhouse: bool = True) -> GameService:
    registry = ProviderRegistry()
    registry.register(CheckCallProvider())
    registry.register(UniformRandomProvider())
    if include_fullhouse:
        try:
            registry.register(FullhouseExperimentalProvider(repository_root))
        except FileNotFoundError:
            pass
    return GameService(registry)


class ApiApplication:
    """Transport adapter kept separate from the HTTP server for direct tests."""

    def __init__(self, service: GameService, hero_seat: int = 0, bot_provider: str = "check-call-hu", history: HandHistoryRepository | None = None, solver_jobs: SolverJobManager | None = None, training_jobs: TrainingJobManager | None = None) -> None:
        self.service = service
        self.hero_seat = hero_seat
        self.bot_provider = bot_provider
        self.history = history
        self._pending_strategies: dict[str, dict[str, Any]] = {}
        self._bot_providers: dict[str, str] = {}
        self.solver_jobs = solver_jobs
        self.training_jobs = training_jobs

    def handle(self, method: str, raw_path: str, body: dict[str, Any] | None = None) -> ApiResult:
        try:
            return self._handle(method.upper(), raw_path, body or {})
        except KeyError as error:
            return ApiResult(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except (ValueError, IllegalAction) as error:
            return ApiResult(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def _handle(self, method: str, raw_path: str, body: dict[str, Any]) -> ApiResult:
        parsed = urlparse(raw_path)
        parts = [part for part in parsed.path.split("/") if part]
        if method == "GET" and parts == ["v1", "health"]:
            return ApiResult(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "engine": "nlhe-hu-v1",
                    "solver": "available" if self.solver_jobs is not None else "unavailable",
                    "training": "available" if self.training_jobs is not None else "unavailable",
                },
            )
        if method == "GET" and parts == ["v1", "providers"]:
            providers = self.service.providers.list(include_experimental=True)
            return ApiResult(
                HTTPStatus.OK,
                {
                    "providers": [
                        {
                            "id": provider.provider_id,
                            "version": provider.version,
                            "experimental": provider.capabilities.experimental,
                        }
                        for provider in providers
                    ]
                },
            )
        if method == "GET" and parts == ["v1", "history"]:
            if self.history is None:
                return ApiResult(HTTPStatus.OK, {"hands": []})
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", [20])[0])
            return ApiResult(HTTPStatus.OK, {"hands": self.history.recent(limit)})
        if method == "GET" and parts == ["v1", "training", "spots"]:
            query = parse_qs(parsed.query)
            source = query.get("source", ["curated"])[0]
            if source == "curated":
                spots = curated_spots()
            elif source == "random":
                seed = int(query.get("seed", [secrets.randbits(63)])[0])
                count = int(query.get("count", [1])[0])
                spots = seeded_random_spots(seed, count)
            else:
                raise ValueError("source must be curated or random")
            return ApiResult(HTTPStatus.OK, {"spots": spots})
        if method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "history"]:
            if self.history is None:
                raise KeyError("hand history is disabled")
            return ApiResult(HTTPStatus.OK, self.history.detail(parts[2]))
        if method == "POST" and parts == ["v1", "equity"]:
            hole_cards = body.get("holeCards")
            board = body.get("board", [])
            if not isinstance(hole_cards, list) or not all(isinstance(card, str) for card in hole_cards):
                raise ValueError("holeCards must be a list of cards")
            if not isinstance(board, list) or not all(isinstance(card, str) for card in board):
                raise ValueError("board must be a list of cards")
            return ApiResult(HTTPStatus.OK, calculate_equity(hole_cards, board))
        if method == "POST" and parts == ["v1", "hand-chances"]:
            hole_cards = body.get("holeCards")
            board = body.get("board", [])
            if not isinstance(hole_cards, list) or not all(isinstance(card, str) for card in hole_cards):
                raise ValueError("holeCards must be a list of cards")
            if not isinstance(board, list) or not all(isinstance(card, str) for card in board):
                raise ValueError("board must be a list of cards")
            return ApiResult(HTTPStatus.OK, calculate_hand_chances(hole_cards, board))
        if method == "POST" and parts == ["v1", "solver", "jobs"]:
            if self.solver_jobs is None:
                raise ValueError("solver worker is unavailable; build it with scripts/build_solver_worker.sh")
            return ApiResult(HTTPStatus.ACCEPTED, self.solver_jobs.submit(body))
        if method == "GET" and len(parts) == 4 and parts[:3] == ["v1", "solver", "jobs"]:
            if self.solver_jobs is None:
                raise KeyError("solver worker is unavailable")
            return ApiResult(HTTPStatus.OK, self.solver_jobs.snapshot(parts[3]))
        if method == "POST" and len(parts) == 5 and parts[:3] == ["v1", "solver", "jobs"] and parts[4] == "cancel":
            if self.solver_jobs is None:
                raise KeyError("solver worker is unavailable")
            return ApiResult(HTTPStatus.OK, self.solver_jobs.cancel(parts[3]))
        if method == "POST" and parts == ["v1", "training", "jobs"]:
            if self.training_jobs is None:
                raise ValueError("model training is unavailable")
            return ApiResult(HTTPStatus.ACCEPTED, self.training_jobs.submit(body))
        if method == "GET" and parts == ["v1", "training", "jobs"]:
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", [20])[0])
            return ApiResult(HTTPStatus.OK, {"jobs": self.training_jobs.recent(limit)})
        if method == "GET" and parts == ["v1", "training", "models"]:
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            return ApiResult(HTTPStatus.OK, {"models": self.training_jobs.models()})
        if method == "GET" and len(parts) == 4 and parts[:3] == ["v1", "training", "jobs"]:
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            return ApiResult(HTTPStatus.OK, self.training_jobs.snapshot(parts[3]))
        if method == "POST" and len(parts) == 5 and parts[:3] == ["v1", "training", "jobs"] and parts[4] == "cancel":
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            return ApiResult(HTTPStatus.OK, self.training_jobs.cancel(parts[3]))
        if method == "GET" and len(parts) == 5 and parts[:3] == ["v1", "training", "jobs"] and parts[4] == "checkpoint":
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            return ApiResult(HTTPStatus.OK, self.training_jobs.checkpoint(parts[3]))
        if method == "POST" and len(parts) == 5 and parts[:3] == ["v1", "training", "jobs"] and parts[4] == "resume":
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            return ApiResult(
                HTTPStatus.ACCEPTED,
                self.training_jobs.resume(
                    parts[3],
                    iterations=body.get("iterations"),
                    mode=str(body.get("mode", "visual")),
                    report_every=body.get("reportEvery", 100),
                ),
            )
        if method == "POST" and len(parts) == 5 and parts[:3] == ["v1", "training", "jobs"] and parts[4] == "register":
            if self.training_jobs is None:
                raise KeyError("model training is unavailable")
            name = body.get("name")
            if name is not None and not isinstance(name, str):
                raise ValueError("model name must be a string")
            return ApiResult(
                HTTPStatus.CREATED,
                self.training_jobs.register_model(parts[3], name),
            )
        if method == "POST" and parts == ["v1", "hands"]:
            seed = body.get("seed", secrets.randbits(63))
            if type(seed) is not int:
                raise ValueError("seed must be an integer")
            starting_stacks = body.get("startingStacks", [10_000, 10_000])
            if not isinstance(starting_stacks, list) or len(starting_stacks) != 2 or any(type(value) is not int or value <= 0 for value in starting_stacks):
                raise ValueError("startingStacks must contain two positive chip amounts")
            bot_provider = str(body.get("botProvider", self.bot_provider))
            self.service.providers.get(bot_provider)
            session = self.service.create_hand(seed=seed, button=int(body.get("button", 0)), starting_stacks=tuple(starting_stacks))
            self._bot_providers[session.session_id] = bot_provider
            if self.history is not None:
                self.history.create_hand(session.session_id, self._history_state(session.session_id))
            self._play_bot_until_hero(session.session_id)
            if self.history is not None:
                self.history.append_event(session.session_id, session.hand.observation(self.hero_seat))
                self.history.update_hand(session.session_id, self._history_state(session.session_id))
            return ApiResult(HTTPStatus.CREATED, self._hand_payload(session.session_id))
        if len(parts) >= 3 and parts[:2] == ["v1", "hands"]:
            session_id = parts[2]
            if method == "GET" and len(parts) == 3:
                return ApiResult(HTTPStatus.OK, self._hand_payload(session_id, self.hero_seat))
            if method == "POST" and parts[3:] == ["bot-provider"]:
                provider_id = str(body.get("providerId", ""))
                self.service.providers.get(provider_id)
                self.service.get(session_id)
                self._bot_providers[session_id] = provider_id
                if self.history is not None:
                    self.history.update_hand(session_id, self._history_state(session_id))
                return ApiResult(
                    HTTPStatus.OK,
                    {"sessionId": session_id, "botProvider": provider_id},
                )
            if method == "POST" and parts[3:] == ["actions"]:
                action = self._parse_action(body)
                session = self.service.get(session_id)
                if session.hand.to_act != self.hero_seat:
                    raise ValueError("it is not the hero's turn")
                strategy = self._pending_strategies.pop(session_id, None)
                self.service.apply_action(session_id, action)
                if self.history is not None:
                    self.history.append_event(
                        session_id,
                        session.hand.observation(self.hero_seat),
                        actor_seat=self.hero_seat,
                        action=session.hand.actions[-1],
                        strategy=strategy,
                    )
                self._play_bot_until_hero(session_id)
                if self.history is not None:
                    self.history.update_hand(session_id, self._history_state(session_id))
                return ApiResult(HTTPStatus.OK, self._hand_payload(session_id))
            if method == "POST" and parts[3:] == ["strategy"]:
                provider_id = str(body.get("providerId", "fullhouse-deep-cfr-experimental-hu"))
                session = self.service.get(session_id)
                if session.hand.to_act != self.hero_seat:
                    raise ValueError("strategy is available only on the hero's turn")
                response = self.service.strategy(session_id, provider_id)
                self._pending_strategies[session_id] = response.to_dict()
                return ApiResult(HTTPStatus.OK, response.to_dict())
        return ApiResult(HTTPStatus.NOT_FOUND, {"error": "route not found"})

    def _parse_action(self, body: dict[str, Any]) -> Action:
        action_type = ActionType(str(body.get("type")))
        if action_type == ActionType.RAISE_TO:
            amount = body.get("amount")
            if type(amount) is not int:
                raise ValueError("raise-to amount must be an integer")
            return Action.raise_to(amount)
        return Action(action_type)

    def _play_bot_until_hero(self, session_id: str) -> None:
        session = self.service.get(session_id)
        step = 0
        while not session.hand.terminal and session.hand.to_act != self.hero_seat:
            sample_seed = session.hand.seed ^ (len(session.hand.actions) << 16) ^ step
            provider_id = self._bot_providers.get(session_id, self.bot_provider)
            self.service.apply_provider_action(session_id, provider_id, sample_seed=sample_seed)
            if self.history is not None:
                self.history.append_event(
                    session_id,
                    session.hand.observation(self.hero_seat),
                    actor_seat=1 - self.hero_seat,
                    action=session.hand.actions[-1],
                )
            step += 1
            if step > 20:
                raise RuntimeError("bot action loop exceeded safety limit")

    def _hand_payload(self, session_id: str, seat: int | None = None) -> dict[str, Any]:
        if seat is None:
            seat = self.hero_seat
        session = self.service.get(session_id)
        return {
            "sessionId": session_id,
            "botProvider": self._bot_providers.get(session_id, self.bot_provider),
            "observation": session.hand.observation(seat),
        }

    def _history_state(self, session_id: str) -> dict[str, Any]:
        state = self.service.get(session_id).hand.to_dict()
        state["botProvider"] = self._bot_providers.get(session_id, self.bot_provider)
        return state


def encode_json(result: ApiResult) -> bytes:
    return json.dumps(result.body, separators=(",", ":"), sort_keys=True).encode("utf-8")
