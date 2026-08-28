use postflop_solver::*;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::{self, Read};
use std::time::Instant;

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct SolveRequest {
    schema_version: String,
    mode: SolveMode,
    oop_range: String,
    ip_range: String,
    flop: String,
    turn: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    initial_street: Option<InitialStreet>,
    starting_pot: i32,
    effective_stack: i32,
    bet_sizes: String,
    raise_sizes: String,
    max_iterations: u32,
    target_exploitability: f32,
    report_every: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    max_raises_per_street: Option<u8>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    include_hand_details: Option<bool>,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum SolveMode {
    Visual,
    Headless,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum InitialStreet {
    Flop,
    Turn,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ActionMix {
    action: String,
    probability: f32,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct HandDetail {
    hand: String,
    weight: f32,
    actions: std::collections::BTreeMap<String, f32>,
    action_values: std::collections::BTreeMap<String, f32>,
}

fn abstract_action(action: &Action, starting_pot: i32, effective_stack: i32) -> String {
    match action {
        Action::Check => "check".into(),
        Action::Fold => "fold".into(),
        Action::Call => "call".into(),
        Action::AllIn(_) => "all-in".into(),
        Action::Bet(amount) if *amount == (starting_pot + 1) / 2 => "bet-50".into(),
        Action::Bet(amount) if *amount == starting_pot => "bet-100".into(),
        Action::Bet(amount) if *amount == effective_stack => "all-in".into(),
        Action::Raise(_) => "raise-2.5x".into(),
        _ => format!("{action:?}"),
    }
}

fn is_aggressive(action: Action) -> bool {
    matches!(action, Action::Bet(_) | Action::Raise(_) | Action::AllIn(_))
}

fn collect_excess_raise_lines(
    tree: &mut ActionTree,
    previous: Option<Action>,
    raises: u8,
    maximum: u8,
    lines: &mut Vec<Vec<Action>>,
) -> Result<(), String> {
    if tree.is_terminal_node() {
        return Ok(());
    }
    let actions = tree.available_actions().to_vec();
    for action in actions {
        let is_raise = matches!(action, Action::Raise(_))
            || (matches!(action, Action::AllIn(_)) && previous.is_some_and(is_aggressive));
        if is_raise && raises >= maximum {
            let mut line = tree.history().to_vec();
            line.push(action);
            lines.push(line);
            continue;
        }
        tree.play(action)?;
        if !tree.is_terminal_node() {
            let closes_street = matches!(action, Action::Call)
                && previous.is_some_and(is_aggressive)
                || matches!(action, Action::Check) && matches!(previous, Some(Action::Check));
            collect_excess_raise_lines(
                tree,
                if closes_street { None } else { Some(action) },
                if closes_street {
                    0
                } else {
                    raises + u8::from(is_raise)
                },
                maximum,
                lines,
            )?;
        }
        tree.undo()?;
    }
    Ok(())
}

fn enforce_raise_cap(tree: &mut ActionTree, maximum: u8) -> Result<(), String> {
    let mut lines = Vec::new();
    collect_excess_raise_lines(tree, None, 0, maximum, &mut lines)?;
    for line in lines {
        tree.remove_line(&line)?;
    }
    tree.back_to_root();
    Ok(())
}

fn root_hand_details(
    game: &PostFlopGame,
    request: &SolveRequest,
) -> Result<Vec<HandDetail>, String> {
    let actions = game.available_actions();
    let labels: Vec<String> = actions
        .iter()
        .map(|action| abstract_action(action, request.starting_pot, request.effective_stack))
        .collect();
    let hands = holes_to_strings(game.private_cards(0))?;
    let weights = game.normalized_weights(0);
    let strategy = game.strategy();
    let action_values = game.expected_values_detail(0);
    let hand_count = hands.len();
    Ok(hands
        .into_iter()
        .enumerate()
        .map(|(hand_index, hand)| {
            let mut probabilities = std::collections::BTreeMap::new();
            let mut values = std::collections::BTreeMap::new();
            for (action_index, label) in labels.iter().enumerate() {
                let index = action_index * hand_count + hand_index;
                probabilities.insert(label.clone(), strategy[index]);
                values.insert(label.clone(), action_values[index]);
            }
            HandDetail {
                hand,
                weight: weights[hand_index],
                actions: probabilities,
                action_values: values,
            }
        })
        .collect())
}

fn emit(value: serde_json::Value) {
    println!("{}", serde_json::to_string(&value).unwrap());
}

fn config_hash(request: &SolveRequest) -> String {
    let mut canonical = request.clone();
    canonical.mode = SolveMode::Headless;
    canonical.report_every = 10;
    let bytes = serde_json::to_vec(&canonical).unwrap();
    format!("{:x}", Sha256::digest(bytes))
}

fn root_action_mix(game: &PostFlopGame) -> Vec<ActionMix> {
    let actions = game.available_actions();
    let strategy = game.strategy();
    let weights = game.normalized_weights(0);
    let hand_count = weights.len();
    let total_weight: f32 = weights.iter().sum();
    actions
        .iter()
        .enumerate()
        .map(|(action_index, action)| {
            let chunk = &strategy[action_index * hand_count..(action_index + 1) * hand_count];
            let probability =
                chunk.iter().zip(weights).map(|(p, w)| p * w).sum::<f32>() / total_weight;
            ActionMix {
                action: format!("{action:?}"),
                probability,
            }
        })
        .collect()
}

fn run(request: SolveRequest) -> Result<(), String> {
    if request.schema_version != "1.0.0" {
        return Err("unsupported schemaVersion".into());
    }
    if request.report_every == 0 || request.report_every % 10 != 0 {
        return Err("reportEvery must be a positive multiple of 10".into());
    }
    let initial_state = match request.initial_street.unwrap_or(InitialStreet::Turn) {
        InitialStreet::Flop => BoardState::Flop,
        InitialStreet::Turn => BoardState::Turn,
    };
    let turn = if initial_state == BoardState::Flop {
        NOT_DEALT
    } else {
        card_from_str(&request.turn).map_err(|_| "invalid turn")?
    };
    let card_config = CardConfig {
        range: [
            request.oop_range.parse().map_err(|_| "invalid oopRange")?,
            request.ip_range.parse().map_err(|_| "invalid ipRange")?,
        ],
        flop: flop_from_str(&request.flop).map_err(|_| "invalid flop")?,
        turn,
        river: NOT_DEALT,
    };
    let sizes =
        BetSizeOptions::try_from((request.bet_sizes.as_str(), request.raise_sizes.as_str()))
            .map_err(|error| error.to_string())?;
    let tree_config = TreeConfig {
        initial_state,
        starting_pot: request.starting_pot,
        effective_stack: request.effective_stack,
        rake_rate: 0.0,
        rake_cap: 0.0,
        flop_bet_sizes: [sizes.clone(), sizes.clone()],
        turn_bet_sizes: [sizes.clone(), sizes.clone()],
        river_bet_sizes: [sizes.clone(), sizes],
        turn_donk_sizes: None,
        river_donk_sizes: None,
        add_allin_threshold: 1.5,
        force_allin_threshold: 0.15,
        merging_threshold: 0.1,
    };
    let mut action_tree = ActionTree::new(tree_config).map_err(|error| error.to_string())?;
    if let Some(maximum) = request.max_raises_per_street {
        enforce_raise_cap(&mut action_tree, maximum)?;
    }
    let mut game =
        PostFlopGame::with_config(card_config, action_tree).map_err(|error| error.to_string())?;
    let (memory_bytes, compressed_memory_bytes) = game.memory_usage();
    game.allocate_memory(false);
    game.cache_normalized_weights();
    let hash = config_hash(&request);
    let started = Instant::now();
    if request.mode == SolveMode::Visual {
        emit(
            serde_json::json!({"schemaVersion":"1.0.0","event":"started","configHash":hash,"memoryBytes":memory_bytes,"compressedMemoryBytes":compressed_memory_bytes}),
        );
    }
    let mut exploitability = compute_exploitability(&game);
    let mut completed_iterations = 0;
    for iteration in 0..request.max_iterations {
        if exploitability <= request.target_exploitability {
            break;
        }
        solve_step(&game, iteration);
        completed_iterations = iteration + 1;
        if completed_iterations % 10 == 0 || completed_iterations == request.max_iterations {
            exploitability = compute_exploitability(&game);
            if request.mode == SolveMode::Visual && completed_iterations % request.report_every == 0
            {
                emit(
                    serde_json::json!({"schemaVersion":"1.0.0","event":"progress","configHash":hash,"iteration":completed_iterations,"exploitability":exploitability,"elapsedMs":started.elapsed().as_millis(),"actions":root_action_mix(&game)}),
                );
            }
        }
    }
    finalize(&mut game);
    game.cache_normalized_weights();
    let oop_weights = game.normalized_weights(0);
    let ip_weights = game.normalized_weights(1);
    let oop_ev = compute_average(&game.expected_values(0), oop_weights);
    let ip_ev = compute_average(&game.expected_values(1), ip_weights);
    let hand_details = if request.include_hand_details.unwrap_or(false) {
        Some(root_hand_details(&game, &request)?)
    } else {
        None
    };
    emit(serde_json::json!({
        "schemaVersion":"1.0.0","event":"complete","configHash":hash,"mode":request.mode,
        "iterations":completed_iterations,"exploitability":exploitability,
        "elapsedMs":started.elapsed().as_millis(),"memoryBytes":memory_bytes,
        "actions":root_action_mix(&game),"oopEv":oop_ev,"ipEv":ip_ev,
        "handDetails":hand_details
    }));
    Ok(())
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let result = serde_json::from_str::<SolveRequest>(&input)
        .map_err(|error| error.to_string())
        .and_then(run);
    if let Err(error) = result {
        emit(serde_json::json!({"schemaVersion":"1.0.0","event":"failed","error":error}));
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raise_cap_removes_second_raise_on_each_street() {
        let sizes = BetSizeOptions::try_from(("50%, 100%, a", "2.5x")).unwrap();
        let config = TreeConfig {
            initial_state: BoardState::Flop,
            starting_pot: 22,
            effective_stack: 80,
            flop_bet_sizes: [sizes.clone(), sizes.clone()],
            turn_bet_sizes: [sizes.clone(), sizes.clone()],
            river_bet_sizes: [sizes.clone(), sizes],
            add_allin_threshold: 1.5,
            force_allin_threshold: 0.15,
            merging_threshold: 0.1,
            ..Default::default()
        };
        let mut tree = ActionTree::new(config).unwrap();
        enforce_raise_cap(&mut tree, 1).unwrap();
        let bet = tree
            .available_actions()
            .iter()
            .copied()
            .find(|action| matches!(action, Action::Bet(_)))
            .unwrap();
        tree.play(bet).unwrap();
        let raise = tree
            .available_actions()
            .iter()
            .copied()
            .find(|action| matches!(action, Action::Raise(_) | Action::AllIn(_)))
            .unwrap();
        tree.play(raise).unwrap();
        assert_eq!(tree.available_actions(), &[Action::Fold, Action::Call]);
    }
}
