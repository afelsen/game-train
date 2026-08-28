import copy
import hashlib
import json
import unittest

from game_trainer.nlhe_evaluation import evaluate_policy, heldout_information_sets


def artifact_hash(artifact):
    return hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def candidate_and_reference(count=50):
    actions = {"check": 0.7, "bet-50": 0.2, "bet-100": 0.08, "all-in": 0.02}
    candidate = [
        {"informationSet": f"state-{index}", "actions": dict(actions)}
        for index in range(count)
    ]
    reference = {
        "schemaVersion": "1.0.0",
        "id": "synthetic-compatible-reference",
        "abstractionId": "restricted-hu-nlhe-flop-cfr-v1",
        "spots": [
            {
                "informationSet": f"state-{index}",
                "weight": 1,
                "actions": dict(actions),
                "actionValuesBb": {"check": 1.0, "bet-50": 0.9, "bet-100": 0.7, "all-in": -1.0},
            }
            for index in range(count)
        ],
    }
    return candidate, reference


class NlheEvaluationTests(unittest.TestCase):
    def test_heldout_information_sets_are_unique_and_deterministic(self):
        first = heldout_information_sets()
        self.assertEqual(first, heldout_information_sets())
        self.assertEqual(len(first), 50)
        self.assertEqual(len(set(first)), 50)

    def test_matching_policy_passes_all_gates(self):
        candidate, reference = candidate_and_reference()
        result = evaluate_policy(candidate, reference, duplicate_artifact_hash=artifact_hash(candidate))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["metrics"]["meanActionL1"], 0)
        self.assertEqual(result["metrics"]["weightedEvLossBb"], 0)

    def test_bad_policy_is_rejected(self):
        candidate, reference = candidate_and_reference()
        for node in candidate:
            node["actions"] = {"check": 0.0, "bet-50": 0.0, "bet-100": 0.0, "all-in": 1.0}
        result = evaluate_policy(candidate, reference, duplicate_artifact_hash=artifact_hash(candidate))
        self.assertEqual(result["status"], "rejected")
        self.assertGreater(result["metrics"]["meanActionL1"], 0.18)
        self.assertGreater(result["metrics"]["weightedEvLossBb"], 0.08)

    def test_missing_or_nondeterministic_policy_cannot_pass(self):
        candidate, reference = candidate_and_reference()
        incomplete = evaluate_policy(candidate[:-1], reference, duplicate_artifact_hash=artifact_hash(candidate[:-1]))
        self.assertEqual(incomplete["status"], "incomplete")
        nondeterministic = evaluate_policy(candidate, reference, duplicate_artifact_hash="0" * 64)
        self.assertEqual(nondeterministic["status"], "rejected")

    def test_invalid_reference_is_rejected(self):
        candidate, reference = candidate_and_reference()
        invalid = copy.deepcopy(reference)
        invalid["spots"][0]["actions"]["check"] = 0.5
        with self.assertRaises(ValueError):
            evaluate_policy(candidate, invalid)


if __name__ == "__main__":
    unittest.main()
