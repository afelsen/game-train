# Product ideas

Ideas in this file are recorded for future consideration and are not necessarily implemented.

## Poker table

- When the opponent wins at showdown, reveal and highlight the five cards forming the opponent’s best hand using the same structural-card logic as the hero highlight, but with a distinct red treatment. This should correctly cover board cards shared by both players and compound hands such as two pair and full houses.

## Bug-fix checklist

- Move the “Opponent won the hand” result banner so it never covers the hero’s hole cards.
- Keep “Chance by river · current hand or better” on one line, or shorten the label while preserving its meaning.
- Do not replace the opponent model selector/name with “Winner” at showdown; show winner status separately.
- Rename the opponent to “Villain” throughout the poker interface.
- Prevent the Raise control from overlapping Fold when Raise, Fold, and Call are all available.
- Audit whether Villain is actually using the selected model for every decision. Verify the selected provider is retained between hands, sent when a hand is created, used by each bot action, and represented accurately in the UI and saved history.
