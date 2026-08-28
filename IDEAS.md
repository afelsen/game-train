# Product ideas

Ideas in this file are recorded for future consideration and are not necessarily implemented.

## Bug-fix queue

- [ ] Raise still overlaps Fold in some action states; slightly reduce the relevant control width or spacing while preserving the compact betting bar.
- [ ] Allow the Villain model to be changed at any time. Define and expose whether a mid-hand change takes effect on Villain's next decision or at the next hand boundary.

## Completed

- [x] Highlight Villain’s winning best-five cards in red at showdown, including shared board cards and compound hands.
- [x] Keep the showdown result banner clear of the hero’s hole cards.
- [x] Keep the shorter chance-by-river label on one line.
- [x] Preserve the model selector name at showdown and show winner status separately.
- [x] Use “Villain” throughout the player-facing poker interface.
- [x] Prevent Raise from overlapping Fold and Call.
- [x] Verify selected-model use: the provider is retained per hand, passed to every Villain action, returned to the UI, persisted in history, and covered by a regression test.
