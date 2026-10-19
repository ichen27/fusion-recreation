use std::io::{self, Read};
fn main() {
    let mut input = String::new();
    let result = io::stdin().take(1_048_577).read_to_string(&mut input);
    let output = if result.is_err() || input.len() > 1_048_576 {
        serde_json::json!({"error":{"code":"request_limit","entity":"request","message":"Expected <= 1 MiB UTF-8 JSON"}})
    } else if std::env::args().nth(1).as_deref() == Some("--explain") {
        match serde_json::from_str::<model_engine::intent::Request>(&input) {
            Ok(request) => match model_engine::intent::explain(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"intent","message":e.to_string()}})
            }
        }
    } else if std::env::args().nth(1).as_deref() == Some("--mesh") {
        match serde_json::from_str::<model_engine::mesh::Request>(&input) {
            Ok(request) => match model_engine::mesh::evaluate(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"mesh","message":e.to_string()}})
            }
        }
    } else {
        match serde_json::from_str::<model_engine::Request>(&input) {
            Ok(request) => match model_engine::evaluate(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"request","message":e.to_string()}})
            }
        }
    };
    println!("{}", output);
    if output.get("error").is_some() {
        std::process::exit(1);
    }
}
