from __future__ import annotations

import time

from game_trainer.poker import Action

from .base import ProviderCapabilities, StrategyAction, StrategyProvider, StrategyRequest, StrategyResponse


class UniformRandomProvider(StrategyProvider):
    provider_id = "uniform-random-hu"
    version = "1.0.0"
    capabilities = ProviderCapabilities(frozenset({"nlhe"}), frozenset(range(2, 7)), frozenset({"preflop", "flop", "turn", "river"}))

    def strategy(self, request: StrategyRequest) -> StrategyResponse:
        started = time.perf_counter()
        legal = request.trusted_hand.legal_actions()
        probability = 1.0 / len(legal)
        actions = tuple(
            StrategyAction(
                abstract_action=item.type.value,
                probability=probability,
                legal_action=Action(item.type, item.min_amount if item.type.value == "raise-to" else None),
            )
            for item in legal
        )
        return StrategyResponse(
            request.request_id,
            self.provider_id,
            self.version,
            self.action_abstraction_version,
            "ok",
            actions,
            True,
            (time.perf_counter() - started) * 1000,
        )


class CheckCallProvider(StrategyProvider):
    provider_id = "check-call-hu"
    version = "1.0.0"
    capabilities = UniformRandomProvider.capabilities

    def strategy(self, request: StrategyRequest) -> StrategyResponse:
        started = time.perf_counter()
        hand = request.trusted_hand
        action = Action.check() if hand.amount_to_call() == 0 else Action.call()
        return StrategyResponse(
            request.request_id,
            self.provider_id,
            self.version,
            self.action_abstraction_version,
            "ok",
            (StrategyAction("check-call", 1.0, action),),
            True,
            (time.perf_counter() - started) * 1000,
        )
