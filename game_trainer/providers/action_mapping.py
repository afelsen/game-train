from __future__ import annotations

from game_trainer.poker import Action, ActionType, HandState, LegalAction


def _legal_by_type(hand: HandState) -> dict[ActionType, LegalAction]:
    return {action.type: action for action in hand.legal_actions()}


def map_abstract_action(hand: HandState, abstract_action: str) -> Action | None:
    """Map the shared five-action abstraction into the engine's exact legal set."""
    legal = _legal_by_type(hand)
    if abstract_action == "fold":
        if ActionType.FOLD in legal:
            return Action.fold()
        return None
    if abstract_action == "check-call":
        if ActionType.CHECK in legal:
            return Action.check()
        if ActionType.CALL in legal:
            return Action.call()
        return None
    if abstract_action == "all-in":
        if ActionType.ALL_IN in legal:
            return Action.all_in()
        if ActionType.CALL in legal and hand.seats[hand.to_act].stack <= hand.amount_to_call():
            return Action.call()
        return None
    if abstract_action in ("bet-half-pot", "bet-pot"):
        raise_action = legal.get(ActionType.RAISE_TO)
        if raise_action is None:
            return None
        fraction = 0.5 if abstract_action == "bet-half-pot" else 1.0
        actor = hand.seats[hand.to_act]
        to_call = hand.amount_to_call()
        if to_call == 0:
            target = actor.street_committed + round(hand.pot * fraction)
        else:
            pot_after_call = hand.pot + min(to_call, actor.stack)
            target = hand.current_bet + round(pot_after_call * fraction)
        target = max(raise_action.min_amount, min(target, raise_action.max_amount))
        return Action.raise_to(target)
    return None


def normalize_mapped_strategy(
    hand: HandState, probabilities: dict[str, float]
) -> tuple[tuple[str, float, Action], ...]:
    mapped: list[tuple[str, float, Action]] = []
    for name, probability in probabilities.items():
        if probability < 0:
            raise ValueError("strategy probabilities cannot be negative")
        action = map_abstract_action(hand, name)
        if action is not None and probability > 0:
            mapped.append((name, float(probability), action))
    total = sum(item[1] for item in mapped)
    if total <= 0:
        fallback = map_abstract_action(hand, "check-call")
        if fallback is None:
            raise ValueError("provider has no probability mass on a legal action")
        return (("check-call", 1.0, fallback),)
    return tuple((name, probability / total, action) for name, probability, action in mapped)
