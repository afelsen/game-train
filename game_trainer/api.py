from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from game_trainer.poker import Action, ActionType, IllegalAction
from game_trainer.providers import (
    CheckCallProvider,
    FullhouseExperimentalProvider,
    ProviderRegistry,
    UniformRandomProvider,
)
from game_trainer.service import GameService


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

    def __init__(self, service: GameService, hero_seat: int = 0, bot_provider: str = "check-call-hu") -> None:
        self.service = service
        self.hero_seat = hero_seat
        self.bot_provider = bot_provider

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
            return ApiResult(HTTPStatus.OK, {"status": "ok", "engine": "nlhe-hu-v1"})
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
        if method == "POST" and parts == ["v1", "hands"]:
            seed = body.get("seed", secrets.randbits(63))
            if type(seed) is not int:
                raise ValueError("seed must be an integer")
            session = self.service.create_hand(seed=seed, button=int(body.get("button", 0)))
            self._play_bot_until_hero(session.session_id)
            return ApiResult(HTTPStatus.CREATED, self._hand_payload(session.session_id))
        if len(parts) >= 3 and parts[:2] == ["v1", "hands"]:
            session_id = parts[2]
            if method == "GET" and len(parts) == 3:
                query = parse_qs(parsed.query)
                seat = int(query.get("seat", [self.hero_seat])[0])
                return ApiResult(HTTPStatus.OK, self._hand_payload(session_id, seat))
            if method == "POST" and parts[3:] == ["actions"]:
                action = self._parse_action(body)
                session = self.service.get(session_id)
                if session.hand.to_act != self.hero_seat:
                    raise ValueError("it is not the hero's turn")
                self.service.apply_action(session_id, action)
                self._play_bot_until_hero(session_id)
                return ApiResult(HTTPStatus.OK, self._hand_payload(session_id))
            if method == "POST" and parts[3:] == ["strategy"]:
                provider_id = str(body.get("providerId", "fullhouse-deep-cfr-experimental-hu"))
                session = self.service.get(session_id)
                if session.hand.to_act != self.hero_seat:
                    raise ValueError("strategy is available only on the hero's turn")
                response = self.service.strategy(session_id, provider_id)
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
            self.service.apply_provider_action(session_id, self.bot_provider, sample_seed=sample_seed)
            step += 1
            if step > 20:
                raise RuntimeError("bot action loop exceeded safety limit")

    def _hand_payload(self, session_id: str, seat: int | None = None) -> dict[str, Any]:
        if seat is None:
            seat = self.hero_seat
        session = self.service.get(session_id)
        return {
            "sessionId": session_id,
            "observation": session.hand.observation(seat),
        }


def encode_json(result: ApiResult) -> bytes:
    return json.dumps(result.body, separators=(",", ":"), sort_keys=True).encode("utf-8")

