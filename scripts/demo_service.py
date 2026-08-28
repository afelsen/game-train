#!/usr/bin/env python3
"""Run a deterministic bot-vs-bot hand through the service/provider boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game_trainer.providers import CheckCallProvider, ProviderRegistry, UniformRandomProvider
from game_trainer.service import GameService


def main() -> None:
    registry = ProviderRegistry()
    registry.register(CheckCallProvider())
    registry.register(UniformRandomProvider())
    service = GameService(registry)
    session = service.create_hand(seed=20260829)

    responses = []
    step = 0
    while not session.hand.terminal:
        response, _ = service.apply_provider_action(
            session.session_id,
            "check-call-hu",
            sample_seed=step,
        )
        responses.append(response.to_dict())
        step += 1

    print(
        json.dumps(
            {
                "sessionId": session.session_id,
                "providerResponses": responses,
                "finalState": session.hand.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

