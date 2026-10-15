#![forbid(unsafe_code)]
use std::io::{self, Read};

fn run() -> Result<(), String> {
    let mut bytes = vec![];
    io::stdin()
        .take(boundary_clip::MAX_REQUEST_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("read failed: {e}"))?;
    if bytes.len() as u64 > boundary_clip::MAX_REQUEST_BYTES {
        return Err("request exceeds 1 MiB".into());
    }
    let request = serde_json::from_slice(&bytes).map_err(|e| format!("invalid request: {e}"))?;
    let reply = boundary_clip::clip(request)?;
    println!(
        "{}",
        serde_json::to_string(&reply).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{}", serde_json::json!({"error": error}));
        std::process::exit(2);
    }
}
