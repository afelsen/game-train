# Product ideas

Ideas in this file are recorded for future consideration and are not necessarily implemented.

## Bug-fix queue

- [x] Prevent Raise from overlapping Fold by tightening the compact sizing controls at desktop widths.
- [x] Allow the Villain model to be changed during an active hand; an acknowledged change applies to Villain's next decision.
- [x] Make every workspace vertically scrollable and responsive under browser zoom and reduced viewport height. Fixed-height play controls, cards, Convergence, Run Configuration, and “Your turn” remain reachable without clipping or inaccessible overflow.

## Roadmap

- [x] Estimate Villain's range from observed behavior with a transparent action-weighted legal-combo model; allow equity to use the estimated range or uniform-random Monte Carlo.
- [ ] Replace the heuristic Villain-range estimator with a proper calibrated prediction model trained and evaluated on action sequences, positions, stack depth, bet sizing, board texture, and showdown evidence. Preserve uncertainty, blocker legality, and a transparent fallback when evidence is sparse.
- [ ] Expose objective, cost/utility, sampling, and training parameters that can produce different bot styles without enforcing fixed personality presets.
- [ ] Add multiplayer poker for two through six seats, including multiway pots and provider capability checks.
- [ ] Add Human Training modes for generated situations and manually entered situations with range, equity, and model analysis.
- [x] Show exact final-hand by-river runout combinations beside each hand-ranking probability, so “Flush” counts only runouts whose final best hand is a flush rather than stronger categories.
- [x] Reveal Villain's folded cards by default in the educational interface.
- [x] Animate poker-chip movement when betting, raising, or calling so the action and pot change are easy to perceive; support reduced motion.
- [x] Highlight hand-ranking probabilities above a sampled random-legal-hand baseline for the same board context, with the baseline named for the learner.
- [x] Add a simplified mobile learning layout: prioritize table and actions, show compact current-hand and strategy summaries, and reveal full details only when tapped.
- [ ] Add bot-versus-bot play in the Play tab, with independent model selection for each seat, play/pause/step controls, adjustable pacing, and a readable action history. Enforce provider compatibility with the active game and ruleset.

## Completed

- [x] Use contextual poker terminology for current hands, including pocket/over/top/middle/bottom pairs, sets versus trips, ranked two pair, full houses, quads, and high-card strength for straights, flushes, and unpaired hands.
- [x] Highlight Villain’s winning best-five cards in red at showdown, including shared board cards and compound hands.
- [x] Keep the showdown result banner clear of the hero’s hole cards.
- [x] Keep the shorter chance-by-river label on one line.
- [x] Preserve the model selector name at showdown and show winner status separately.
- [x] Use “Villain” throughout the player-facing poker interface.
- [x] Prevent Raise from overlapping Fold and Call.
- [x] Verify selected-model use: the provider is retained per hand, passed to every Villain action, returned to the UI, persisted in history, and covered by a regression test.
