from __future__ import annotations

import sys
import time
from pathlib import Path

from .action_mapping import map_abstract_action, normalize_mapped_strategy
from .base import ProviderCapabilities, StrategyAction, StrategyProvider, StrategyRequest, StrategyResponse

ACTIONS = ("fold", "check-call", "bet-half-pot", "bet-pot", "all-in")


class FullhouseExperimentalProvider(StrategyProvider):
    """Serve the pretrained six-player Fullhouse checkpoint."""

    provider_id = "fullhouse-deep-cfr-experimental-hu"
    version = "e504793"
    action_abstraction_version = "fullhouse-5-action-v1"
    capabilities = ProviderCapabilities(
        frozenset({"nlhe"}),
        frozenset({2, 6}),
        frozenset({"preflop", "flop", "turn", "river"}),
        experimental=True,
    )

    def __init__(self, repository_root: Path) -> None:
        vendor = repository_root / "vendor/fullhouse-bot"
        if not (vendor / "data/deep_cfr_model.npz").exists():
            raise FileNotFoundError("Fullhouse artifacts are missing; run scripts/bootstrap_models.sh")
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        from bot.deep_cfr_lookup import DeepCFRLookup

        self._lookup = DeepCFRLookup(vendor / "data/deep_cfr_model.npz")

    def strategy(self, request: StrategyRequest) -> StrategyResponse:
        started = time.perf_counter()
        hand = request.trusted_hand
        actor = hand.seats[request.acting_seat]
        legal_raise = next((item for item in hand.legal_actions() if item.type.value == "raise-to"), None)
        action_log = []
        type_map = {
            "small-blind": "small_blind",
            "big-blind": "big_blind",
            "raise-to": "raise",
            "all-in": "all_in",
        }
        for record in hand.actions:
            action_log.append({"action": type_map.get(record["type"], record["type"]), "seat": record["seat"], "amount": record["amount"]})
        state = {
            "your_cards": list(actor.hole_cards),
            "community_cards": list(hand.board),
            "pot": hand.pot,
            "your_stack": actor.stack,
            "your_bet_this_street": actor.street_committed,
            "amount_owed": hand.amount_to_call(),
            "min_raise_to": legal_raise.min_amount if legal_raise else 0,
            "can_check": hand.amount_to_call() == 0,
            "seat_to_act": request.acting_seat,
            "dealer": hand.button,
            "street": hand.street.value,
            "hand_num": hand.seed,
            "current_bet": hand.current_bet,
            "action_log": action_log,
            "players": [
                {
                    "seat": seat.seat,
                    "stack": seat.stack,
                    "is_folded": seat.status.value == "folded",
                    "is_all_in": seat.status.value == "all-in",
                    "bet_this_street": seat.street_committed,
                }
                for seat in hand.seats
            ],
        }
        raw = self._lookup.get_strategy(state)
        raw_probabilities = dict(zip(ACTIONS, map(float, raw)))
        mapped = normalize_mapped_strategy(hand, raw_probabilities)
        actions = tuple(StrategyAction(name, probability, action) for name, probability, action in mapped)
        model_actions = tuple(
            {
                "abstractAction": name,
                "probability": probability,
                "available": (legal_action := map_abstract_action(hand, name)) is not None,
                "legalAction": None
                if legal_action is None
                else {"type": legal_action.type.value, "amount": legal_action.amount},
            }
            for name, probability in raw_probabilities.items()
        )
        return StrategyResponse(
            request.request_id,
            self.provider_id,
            self.version,
            self.action_abstraction_version,
            "ok",
            actions,
            False,
            (time.perf_counter() - started) * 1000,
            warnings=(() if request.player_count == 6 else (
                "Checkpoint was trained for six-player NLHE; heads-up strategy quality is unvalidated.",
            )),
            model_actions=model_actions,
        )
