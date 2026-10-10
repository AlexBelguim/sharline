//! Inspect an authored map without starting Bevy or touching user placements.
use std::{env, path::PathBuf, process::ExitCode};

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    let map = args.next().unwrap_or_else(|| "showhome_v3".to_owned());
    let assets = args
        .next()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets"));
    match vetf_sim::build_mode::inspect_map(&assets, &map) {
        Ok(report) => {
            println!("{}", serde_json::to_string_pretty(&report).expect("inspection serializes"));
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("Map inspection failed: {error}");
            ExitCode::FAILURE
        }
    }
}
