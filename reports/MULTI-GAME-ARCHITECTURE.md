# Multi-game architecture and Backgammon plan

## 1. Product outcome

Game Train becomes a platform for multiple strategy games with a consistent learning experience and distinct game identities.

- Poker lives at `/poker` and is branded **poker train**.
- Backgammon lives at `/backgammon` and is branded **backgammon train**.
- The title in the header is the game selector. Switching it changes the URL, theme, rules engine, compatible models, saved state, terminology, and content.
- Every game uses the same four primary experiences: **Learn**, **Play**, **Train**, and **Model**.
- Play keeps the shared three-area composition: information on the left, the playable game surface in the center, and strategy/advice on the right. Mobile collapses the side areas beneath the game surface in priority order.

This plan establishes the platform boundary first. It does not implement the Backgammon rules engine or claim that poker and Backgammon should share internal state types.

## 2. Why a refactor is needed

The existing product has the right visual concept but is structurally poker-specific:

- `web/app/game-client.tsx` owns navigation, poker play, training, model analysis, review, persistence coordination, and most data fetching in roughly 3,000 lines.
- `web/app/globals.css` mixes platform, poker table, training, model, and responsive styles in roughly 1,700 lines.
- Both the Next-compatible build and the GitHub Pages build render one root application with no game route.
- Runtime contracts expose poker concepts directly: hand, seat, street, board, hole cards, pot, and betting actions.
- Browser persistence and API routes use poker-oriented names such as `current-hand` and `/v1/hands`.
- Provider selection is not yet governed by a cross-game capability check in the browser.

Backgammon should not be represented as a synthetic poker hand, and the shared shell should not know about points, checkers, dice, cards, blinds, or pots.

## 3. Architecture principles

1. **Share product structure, not game state.** Navigation, layout, persistence adapters, model registry, job status, and responsive behavior are platform concerns. Rules, observations, actions, visual boards, explanations, and metrics remain game-owned.
2. **Use explicit game modules.** Adding a game means registering one module; it must not require adding `if (game === ...)` branches throughout a monolithic client.
3. **Keep engines deterministic and serializable.** Poker and Backgammon each provide versioned state, action, replay, and migration functions.
4. **Route models by capabilities.** A provider declares game, ruleset, player count, action contract, and runtime requirements. Incompatible providers are hidden or rejected, never translated silently.
5. **Keep browser and server runtimes interchangeable.** A game module may use browser-only logic, remote inference, or both through the same game-level service boundary.
6. **Avoid premature universal types.** Platform types may use generics, but poker and Backgammon retain concrete, independently testable contracts.
7. **Preserve poker behavior during extraction.** The first refactor milestone should be behaviorally neutral and protected by existing runtime tests plus visual fixtures.

## 4. URL and navigation design

Recommended route map:

```text
/
  Small game chooser; may offer “Continue poker” using locally remembered preference.

/poker
  Poker Play (default)
/poker/learn
/poker/train
/poker/model
/poker/review/:sessionId   (review remains reached from Play)

/backgammon
  Backgammon Play (default)
/backgammon/learn
/backgammon/train
/backgammon/model
/backgammon/review/:sessionId
```

The game title selector navigates between equivalent workspaces when they exist. For example, switching from `/poker/train` goes to `/backgammon/train`; an unavailable workspace falls back to the selected game's `/play` route.

GitHub Pages must support direct entry and refresh at `/poker` and `/backgammon`. The static build should therefore be a Vite multi-page build that emits real `index.html` files for both route roots rather than relying only on a history-API fallback. Nested workspace URLs can either emit matching static entry files or use a small route bootstrap that normalizes to the game root while preserving the workspace in the path. The Next-compatible entrypoints should import the same shared application and game registry.

## 5. Shared application shell

The reusable shell owns:

- game selector and game-specific title;
- Learn / Play / Train / Model navigation;
- desktop three-pane and mobile stacked layouts;
- loading, error, unsupported-provider, and offline states;
- common dialogs, settings entry, accessibility preferences, and reduced motion;
- session/review navigation;
- platform-level model registry and compatible-provider filtering;
- persistence service, schema migrations, and per-game storage namespaces;
- asynchronous job summaries and artifact metadata;
- shared visual primitives such as probability bars, action lists, charts, tooltips, and responsive panels.

The shell exposes layout slots instead of game concepts:

```ts
type PlayLayoutSlots = {
  primaryInfo: ReactNode;
  gameSurface: ReactNode;
  controls: ReactNode;
  advice: ReactNode;
  result?: ReactNode;
};
```

Poker supplies hand rankings, the table, betting controls, and range/equity advice. Backgammon supplies position information, the board, move controls, and move/evaluation advice.

## 6. Game module contract

The registry holds metadata and view factories. Concrete state and action types stay inside the module.

```ts
type GameId = 'poker' | 'backgammon';
type WorkspaceId = 'learn' | 'play' | 'train' | 'model';

interface GameModule {
  id: GameId;
  slug: string;
  title: string;             // “poker train”
  shortName: string;         // “Poker”
  rulesetId: string;
  theme: GameTheme;
  capabilities: Set<WorkspaceId>;
  createService(): GameService;
  views: Record<WorkspaceId, React.ComponentType<GameViewProps>>;
}
```

Each game service implements a transport-neutral session contract:

```ts
interface GameService<State, Observation, Action, Result> {
  create(config?: unknown): Promise<GameSession<Observation>>;
  restore(): Promise<GameSession<Observation> | null>;
  observe(sessionId: string): Promise<Observation>;
  legalActions(sessionId: string): Promise<Action[]>;
  act(sessionId: string, action: Action): Promise<GameSession<Observation>>;
  serialize(sessionId: string): Promise<VersionedState<State>>;
  review(sessionId: string): Promise<GameReplay<Observation, Action, Result>>;
}
```

This is a TypeScript shape for application organization, not a requirement that all serialized state share one schema. Poker and Backgammon each version and validate their own payload.

## 7. Strategy and model contract

The platform model registry should require these compatibility fields:

- `gameId` and `rulesetId`;
- player count and supported variants;
- observation/encoder version;
- action-space version;
- supported phases or state coverage;
- model kind: policy, evaluator, solver, heuristic, or baseline;
- browser, worker, or server runtime;
- artifact version/checksum and license metadata;
- validation status and any approximation warnings.

Game modules translate provider output into their own legal actions. The shared UI renders a generic ranked/mixed action list, while the game supplies action labels, notation, EV units, and explanations.

Poker providers may return fold/check/call/raise distributions and chip EV. Backgammon providers may return complete legal move sequences, equity or winning chances, cube decisions later, and position evaluation. These must not be coerced into one action enum.

## 8. Suggested source layout

```text
web/
  platform/
    app-shell/
      GameApp.tsx
      GameHeader.tsx
      WorkspaceNav.tsx
      PlayLayout.tsx
    games/
      registry.ts
      contracts.ts
    models/
      registry.ts
      capabilities.ts
    persistence/
      storage.ts
      migrations.ts
    routing/
      routes.ts
      static-entry.tsx
    styles/
      platform.css

  games/
    poker/
      module.ts
      contracts.ts
      runtime/
      providers/
      views/
        PokerLearn.tsx
        PokerPlay.tsx
        PokerTrain.tsx
        PokerModel.tsx
      components/
      poker.css

    backgammon/
      module.ts
      contracts.ts
      runtime/
      providers/
      views/
        BackgammonLearn.tsx
        BackgammonPlay.tsx
        BackgammonTrain.tsx
        BackgammonModel.tsx
      components/
      backgammon.css
```

The exact folder names may change during extraction, but dependencies should point inward as follows:

```text
platform shell -> game registry -> selected game module
game views -> that game's runtime/providers/components
game modules -> shared platform primitives
platform code -X-> poker or Backgammon state internals
```

## 9. Theming and identity

The selected module places `data-game="poker"` or `data-game="backgammon"` on the application root and supplies semantic tokens:

```css
[data-game='poker'] {
  --game-surface: #174f3b;
  --game-accent: #d9ab55;
  --game-panel: #f7f4ed;
}

[data-game='backgammon'] {
  --game-surface: #6f3f2b;
  --game-accent: #d7b77a;
  --game-panel: #f4eadb;
}
```

Shared components consume semantic tokens. Each game may add its own textures, animation geometry, pieces, and board layout. The game selector shows the current train icon/title and offers the other registered games without turning the header into a large global menu.

Document titles, descriptions, social metadata, and accessible labels change with the selected route.

## 10. Persistence and history

Use local storage for the browser MVP with explicit game namespaces:

```text
game-train.platform.preferences.v1
game-train.poker.current-session.v1
game-train.poker.history.v1
game-train.backgammon.current-session.v1
game-train.backgammon.history.v1
```

Every stored record includes `gameId`, `rulesetId`, `schemaVersion`, and timestamps. A game module owns migration or rejection of old state. Switching games never overwrites the other game's session. Reset affects only the selected game unless the user explicitly clears all local data.

Later account sync can implement the same storage interface without changing game views.

## 11. Backgammon MVP design

### Initial ruleset

- Standard two-player Backgammon starting position.
- Deterministic seeded dice and reproducible match history.
- Correct legal move-sequence generation, including doubles, bar priority, blocked points, bearing off, and forced use of dice.
- Single-game scoring initially; gammons/backgammons recorded correctly.
- Defer the doubling cube and match-play/Crawford rules until normal checker play and evaluation are validated.

### Play layout

- **Left — Position info:** pip counts, borne-off/bar counts, race/contact classification, turn/dice, and concise concepts relevant to the current position.
- **Center — Board:** responsive board, draggable or tap-select checkers, legal destinations, dice, undo-before-submit, move-sequence confirmation, animations, and result state.
- **Right — Strategy:** ranked legal move sequences with probabilities or equity differences, selected provider, evaluation summary, and an expandable explanation.
- **Mobile:** board and move controls first, then compact Strategy, then Position info, matching the poker information priority.

### Provider sequence

1. Legal random baseline for engine/UI testing.
2. Simple heuristic evaluator for transparent educational explanations.
3. Research and integrate a permissively licensed validated Backgammon engine or checkpoint behind the provider contract.
4. Compare candidate providers on fixed positions before using them for grading.

Backgammon should not be described as CFR-driven by default. Expectiminimax, neural position evaluation, temporal-difference learning, and search are all plausible provider implementations; the product contract should remain algorithm-neutral.

### Train and Model

- **Train:** random legal positions, curated opening replies, running-game decisions, bearing-off drills, and user-entered positions; require a move before revealing advice.
- **Model:** compare evaluators on identical positions, inspect move distributions/equities, benchmark latency and coverage, and later run bounded lookahead or rollout experiments.
- **Learn:** movement rules, legal-dice usage, board notation, pip count, blots/anchors/prime concepts, race versus contact, bearing off, gammons, and later cube strategy.

## 12. Delivery plan

### Phase 0 — Freeze contracts and add safety tests

- Capture current poker routes, responsive screenshots, persistence behavior, runtime tests, and Play interactions as refactor gates.
- Define `GameModule`, route metadata, capability manifest, storage adapter, and shell slot contracts.
- Decide the first Backgammon ruleset ID, recommended `backgammon-standard-money-v1`.

Exit: contracts compile and poker remains unchanged.

### Phase 1 — Extract the shared shell

- Split the 3,000-line client into platform header/navigation/layout and poker views.
- Split platform CSS from poker table/theme CSS.
- Rename current workspaces to Learn / Play / Train / Model; keep review inside Play.
- Register poker as the first module without changing behavior.

Exit: `/poker` visually and behaviorally matches the current application, and platform code contains no card/bet-specific rendering.

### Phase 2 — Add real game routing and identity

- Add the registry, `/`, `/poker`, and `/backgammon` route entries.
- Add the selectable **poker train** header and a Backgammon placeholder branded **backgammon train**.
- Namespace poker persistence and migrate existing browser state once.
- Update static deployment so direct URL entry and refresh work on GitHub Pages.

Exit: both URLs load directly, switching games preserves each game independently, and poker remains fully usable.

### Phase 3 — Build the Backgammon engine

- Implement typed board state, seeded dice, legal move sequences, scoring, serialization, replay, and invariants.
- Add property/fixture tests for checker conservation, legal dice use, blocked points, bar entry, doubles, and bearing off.
- Add random and heuristic providers.

Exit: thousands of seeded games complete without invariant failures and replay deterministically.

### Phase 4 — Backgammon Play

- Implement the responsive board and controls in the shared Play layout.
- Add move animation, legal highlighting, bot turns, advice reveal, persistence, history, and review.
- Validate desktop, zoomed desktop, and iPhone 15 layouts.

Exit: a learner can complete and resume a full game locally or on GitHub Pages.

### Phase 5 — Backgammon Learn, Train, and Model

- Add initial lessons and reference content.
- Add curated/random training positions and delayed feedback.
- Add provider comparison, position explorer, evaluation evidence, and bounded rollout analysis.

Exit: Backgammon supports the same four product experiences without copying the poker implementation.

## 13. Acceptance criteria for the platform refactor

- Direct navigation and refresh work at `/poker` and `/backgammon` on GitHub Pages.
- The header title is route-derived, selectable, keyboard accessible, and changes metadata/theme.
- Poker passes all existing runtime tests and visual checks after extraction.
- Poker and Backgammon state cannot collide in persistence or history.
- A provider incompatible with the selected game/ruleset cannot be selected or queried.
- Shared shell files contain no poker or Backgammon rules logic.
- Game modules can provide different observation/action/result schemas without `any`-typed state crossing the engine boundary.
- Desktop and mobile retain the center-game / advice / information hierarchy.
- A third game can be registered without modifying poker or Backgammon modules.

## 14. Recommended decisions

1. Use `/` as a small game chooser rather than silently redirecting; offer a one-click “Continue” action using the remembered game.
2. Use nested canonical workspace paths (`/poker/train`, `/backgammon/model`) while keeping `/poker` and `/backgammon` as Play defaults.
3. Ship Backgammon checker play before the doubling cube.
4. Keep histories, settings, and current sessions isolated per game; share only platform accessibility preferences.
5. Extract poker into a module before building the Backgammon board. Do not perform a full rewrite—the tested browser poker runtime should move with minimal internal change.
6. Keep provider algorithms opaque to the shell. Backgammon is not required to use CFR merely because poker experiments do.

## 15. Open product choices before Phase 3

- Whether Backgammon MVP is a single money game, a race to a fixed match score, or both. Recommendation: single money game first.
- Whether the first release includes the doubling cube. Recommendation: defer it, but include cube ownership/value fields in the state schema so the ruleset can evolve cleanly.
- Whether checker movement is drag-first or tap-first. Recommendation: support both, with tap-select as the accessible/mobile baseline.
- Which external Backgammon provider meets licensing, browser/server runtime, and validation requirements. This needs a focused provider research milestone before advice is labeled authoritative.

