from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from game_trainer.poker import Action, HandState


@dataclass(frozen=True)
class ProviderCapabilities:
    games: frozenset[str]
    player_counts: frozenset[int]
    streets: frozenset[str]
    experimental: bool = False

    def supports(self, request: "StrategyRequest") -> tuple[bool, str | None]:
        if request.game not in self.games:
            return False, f"game {request.game} is unsupported"
        if request.player_count not in self.player_counts:
            return False, f"player count {request.player_count} is unsupported"
        if request.street not in self.streets:
            return False, f"street {request.street} is unsupported"
        return True, None


@dataclass(frozen=True)
class StrategyRequest:
    request_id: str
    game: str
    player_count: int
    street: str
    acting_seat: int
    observation: dict[str, Any]
    trusted_hand: HandState = field(repr=False, compare=False)

    @classmethod
    def from_hand(cls, hand: HandState, acting_seat: int, request_id: str) -> "StrategyRequest":
        if hand.to_act != acting_seat:
            raise ValueError(f"seat {acting_seat} is not acting")
        return cls(
            request_id=request_id,
            game="nlhe",
            player_count=hand.player_count,
            street=hand.street.value,
            acting_seat=acting_seat,
            observation=hand.observation(acting_seat),
            trusted_hand=hand,
        )


@dataclass(frozen=True)
class StrategyAction:
    abstract_action: str
    probability: float
    legal_action: Action | None
    ev_chips: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "abstractAction": self.abstract_action,
            "probability": self.probability,
            "legalAction": None
            if self.legal_action is None
            else {"type": self.legal_action.type.value, "amount": self.legal_action.amount},
            "evChips": self.ev_chips,
        }


@dataclass(frozen=True)
class StrategyResponse:
    request_id: str
    provider_id: str
    provider_version: str
    action_abstraction_version: str
    status: str
    actions: tuple[StrategyAction, ...]
    exact_state: bool
    inference_ms: float
    message: str | None = None
    warnings: tuple[str, ...] = ()
    model_actions: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": "1.0.0",
            "requestId": self.request_id,
            "provider": {
                "modelId": self.provider_id,
                "modelVersion": self.provider_version,
                "actionAbstractionVersion": self.action_abstraction_version,
            },
            "status": self.status,
            "actions": [action.to_dict() for action in self.actions],
            "modelActions": list(self.model_actions) if self.model_actions else [action.to_dict() for action in self.actions],
            "diagnostics": {
                "exactState": self.exact_state,
                "inferenceMs": self.inference_ms,
                "message": self.message,
                "warnings": list(self.warnings),
            },
        }

    @classmethod
    def unsupported(cls, request: StrategyRequest, provider: "StrategyProvider", message: str) -> "StrategyResponse":
        return cls(
            request.request_id,
            provider.provider_id,
            provider.version,
            provider.action_abstraction_version,
            "unsupported",
            (),
            False,
            0.0,
            message,
        )


class StrategyProvider(ABC):
    provider_id: str
    version: str
    action_abstraction_version: str = "engine-native-v1"
    capabilities: ProviderCapabilities

    @abstractmethod
    def strategy(self, request: StrategyRequest) -> StrategyResponse:
        raise NotImplementedError
