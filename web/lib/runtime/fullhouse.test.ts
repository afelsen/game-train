import { describe, expect, it } from 'vitest';
import artifact from '../../public/models/fullhouse-v17.json';
import fixtures from './fullhouse-parity.json';
import {
  decodeFullhouseArtifact,
  encodeFullhouseFeatures,
  inferFullhouseFeatures,
  type FullhouseArtifact,
} from './fullhouse';
import type { LegalAction } from './contracts';
import type { BrowserPokerHand } from './poker-engine';

const model = decodeFullhouseArtifact(artifact as FullhouseArtifact);

function rehydrate(input: (typeof fixtures)[number]['hand']) {
  return {
    ...input,
    terminal: false,
    playerCount: input.seats.length,
    amountToCall() {
      const actor = input.seats[input.toAct];
      return Math.max(0, input.currentBet - actor.streetCommitted);
    },
    legalActions() {
      return input.legalActions as LegalAction[];
    },
  } as unknown as BrowserPokerHand;
}

describe('Fullhouse browser runtime parity', () => {
  it.each(fixtures)('$name feature encoder matches Python', (fixture) => {
    const encoded = encodeFullhouseFeatures(rehydrate(fixture.hand), model);
    expect(Array.from(encoded.legal)).toEqual(fixture.expectedLegal);
    const differences = fixture.expectedFeatures.flatMap((expected, index) =>
      Math.abs(encoded.features[index] - expected) > 1e-6
        ? [{ index, browser: encoded.features[index], python: expected }]
        : [],
    );
    expect(differences).toEqual([]);
  });

  it.each(fixtures)('$name strategy matches NumPy inference', (fixture) => {
    const encoded = encodeFullhouseFeatures(rehydrate(fixture.hand), model);
    const strategy = inferFullhouseFeatures(encoded.features, encoded.legal, model);
    fixture.expectedStrategy.forEach((expected, index) => {
      expect(strategy[index], `action ${index}`).toBeCloseTo(expected, 4);
    });
  });
});
