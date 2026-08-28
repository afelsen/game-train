from __future__ import annotations

import math
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from game_trainer.poker import Action, ActionType, HandState, Street
from game_trainer.providers import (
    CheckCallProvider,
    FullhouseExperimentalProvider,
    ProviderCapabilities,
    ProviderRegistry,
    StrategyProvider,
    StrategyRequest,
    StrategyResponse,
    UniformRandomProvider,
)
from game_trainer.providers.action_mapping import map_abstract_action, normalize_mapped_strategy
from game_trainer.service import GameService

ROOT = Path(__file__).resolve().parent.parent


class UnsupportedGameProvider(StrategyProvider):
    provider_id = "leduc-only-test"
    version = "1"
    capabilities = ProviderCapabilities(frozenset({"leduc-holdem"}), frozenset({2}), frozenset({"preflop"}))

    def strategy(self, request: StrategyRequest) -> StrategyResponse:
        raise AssertionError("registry must reject before invocation")


class ActionMappingTests(unittest.TestCase):
    def test_open_pot_sizing_maps_and_clamps_to_legal_raise(self) -> None:
        hand = HandState(seed=31)
        hand.apply(Action.call())
        hand.apply(Action.check())
        self.assertEqual(hand.street, Street.FLOP)
        self.assertEqual(hand.pot, 200)
        self.assertEqual(map_abstract_action(hand, "bet-half-pot"), Action.raise_to(100))
        self.assertEqual(map_abstract_action(hand, "bet-pot"), Action.raise_to(200))

    def test_raise_sizing_uses_pot_after_call(self) -> None:
        hand = HandState(seed=32)
        hand.apply(Action.call())
        hand.apply(Action.check())
        hand.apply(Action.raise_to(100))
        # Pot is 300 including the bet; after a 100 call it would be 400.
        self.assertEqual(map_abstract_action(hand, "bet-half-pot"), Action.raise_to(300))
        self.assertEqual(map_abstract_action(hand, "bet-pot"), Action.raise_to(500))

    def test_illegal_probability_mass_is_removed_and_renormalized(self) -> None:
        hand = HandState(seed=33)
        mapped = normalize_mapped_strategy(
            hand,
            {"fold": 0.1, "check-call": 0.2, "bet-half-pot": 0.3, "bet-pot": 0.4, "all-in": 0.0},
        )
        self.assertTrue(math.isclose(sum(item[1] for item in mapped), 1.0, abs_tol=1e-9))
        for _, _, action in mapped:
            self.assertIn(action.type, {item.type for item in hand.legal_actions()})


class ProviderRegistryTests(unittest.TestCase):
    def test_capability_mismatch_returns_unsupported(self) -> None:
        registry = ProviderRegistry()
        registry.register(UnsupportedGameProvider())
        hand = HandState(seed=34)
        request = StrategyRequest.from_hand(hand, hand.to_act, "request-1")
        response = registry.strategy("leduc-only-test", request)
        self.assertEqual(response.status, "unsupported")
        self.assertIn("game nlhe", response.message)

    def test_experimental_provider_hidden_by_default(self) -> None:
        registry = ProviderRegistry()
        registry.register(CheckCallProvider())
        registry.register(FullhouseExperimentalProvider(ROOT))
        self.assertEqual([provider.provider_id for provider in registry.list()], ["check-call-hu"])
        self.assertEqual(len(registry.list(include_experimental=True)), 2)

    def test_fullhouse_adapter_returns_normalized_legal_strategy_with_warning(self) -> None:
        registry = ProviderRegistry()
        registry.register(FullhouseExperimentalProvider(ROOT))
        hand = HandState(seed=35)
        request = StrategyRequest.from_hand(hand, hand.to_act, "request-2")
        response = registry.strategy("fullhouse-deep-cfr-experimental-hu", request)
        self.assertEqual(response.status, "ok")
        self.assertFalse(response.exact_state)
        self.assertTrue(response.warnings)
        self.assertTrue(math.isclose(sum(item.probability for item in response.actions), 1.0, abs_tol=1e-6))
        legal_types = {item.type for item in hand.legal_actions()}
        self.assertTrue(all(item.legal_action.type in legal_types for item in response.actions))
        schema = json.loads((ROOT / "schemas/strategy-response.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(response.to_dict())


class GameServiceTests(unittest.TestCase):
    def make_service(self) -> GameService:
        registry = ProviderRegistry()
        registry.register(CheckCallProvider())
        registry.register(UniformRandomProvider())
        return GameService(registry)

    def test_service_owns_state_and_generates_monotonic_request_ids(self) -> None:
        service = self.make_service()
        session = service.create_hand(seed=41)
        first = service.strategy(session.session_id, "check-call-hu")
        second = service.strategy(session.session_id, "check-call-hu")
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertEqual(session.hand.to_dict(), service.get(session.session_id).hand.to_dict())

    def test_check_call_provider_completes_a_hand(self) -> None:
        service = self.make_service()
        session = service.create_hand(seed=42)
        step = 0
        while not session.hand.terminal:
            _, state = service.apply_provider_action(session.session_id, "check-call-hu", sample_seed=step)
            step += 1
            self.assertLess(step, 20)
        self.assertEqual(state["street"], "terminal")
        self.assertEqual(state["result"]["reason"], "showdown")
        self.assertEqual(sum(seat["stack"] for seat in state["seats"]), 20_000)

    def test_sampled_uniform_action_is_always_legal_and_replayable(self) -> None:
        service = self.make_service()
        for seed in range(100):
            session = service.create_hand(seed=seed, button=seed % 2)
            steps = 0
            while not session.hand.terminal:
                service.apply_provider_action(session.session_id, "uniform-random-hu", sample_seed=seed * 100 + steps)
                steps += 1
                self.assertLess(steps, 100)
            HandState.replay(session.hand.to_dict())


if __name__ == "__main__":
    unittest.main()
