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
    starting_pot: i32,
    effective_stack: i32,
    bet_sizes: String,
    raise_sizes: String,
    max_iterations: u32,
    target_exploitability: f32,
    report_every: u32,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum SolveMode {
    Visual,
    Headless,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ActionMix {
    action: String,
    probability: f32,
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
    let card_config = CardConfig {
        range: [
            request.oop_range.parse().map_err(|_| "invalid oopRange")?,
            request.ip_range.parse().map_err(|_| "invalid ipRange")?,
        ],
        flop: flop_from_str(&request.flop).map_err(|_| "invalid flop")?,
        turn: card_from_str(&request.turn).map_err(|_| "invalid turn")?,
        river: NOT_DEALT,
    };
    let sizes =
        BetSizeOptions::try_from((request.bet_sizes.as_str(), request.raise_sizes.as_str()))
            .map_err(|error| error.to_string())?;
    let tree_config = TreeConfig {
        initial_state: BoardState::Turn,
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
    let action_tree = ActionTree::new(tree_config).map_err(|error| error.to_string())?;
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
    emit(
        serde_json::json!({"schemaVersion":"1.0.0","event":"complete","configHash":hash,"mode":request.mode,"iterations":completed_iterations,"exploitability":exploitability,"elapsedMs":started.elapsed().as_millis(),"memoryBytes":memory_bytes,"actions":root_action_mix(&game),"oopEv":oop_ev,"ipEv":ip_ev}),
    );
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
