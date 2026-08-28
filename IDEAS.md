# Product ideas

Ideas in this file are recorded for future consideration and are not necessarily implemented.

## Bug-fix queue

- [x] Prevent Raise from overlapping Fold by tightening the compact sizing controls at desktop widths.
- [x] Allow the Villain model to be changed during an active hand; an acknowledged change applies to Villain's next decision.

## Roadmap

- [ ] Estimate Villain's range from observed behavior, starting with a simple action-weighted model; allow equity to use the estimated range or uniform-random Monte Carlo.
- [ ] Expose objective, cost/utility, sampling, and training parameters that can produce different bot styles without enforcing fixed personality presets.
- [ ] Add multiplayer poker for two through six seats, including multiway pots and provider capability checks.
- [ ] Add Human Training modes for generated situations and manually entered situations with range, equity, and model analysis.
- [ ] Show deduplicated next-card outs beside hand-ranking improvement percentages.
- [ ] Reveal Villain's folded cards by default in the educational interface.

## Completed

- [x] Highlight Villain’s winning best-five cards in red at showdown, including shared board cards and compound hands.
- [x] Keep the showdown result banner clear of the hero’s hole cards.
- [x] Keep the shorter chance-by-river label on one line.
- [x] Preserve the model selector name at showdown and show winner status separately.
- [x] Use “Villain” throughout the player-facing poker interface.
- [x] Prevent Raise from overlapping Fold and Call.
- [x] Verify selected-model use: the provider is retained per hand, passed to every Villain action, returned to the UI, persisted in history, and covered by a regression test.
