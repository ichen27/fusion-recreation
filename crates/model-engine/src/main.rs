use std::io::{self, Read, Write};
const MAX_REQUEST: usize = 1_048_576;
const MAX_RESPONSE: usize = 16 * 1_048_576;
fn failure(code: &str, message: &str) -> serde_json::Value {
    serde_json::json!({"error":{"code":code,"entity":"request","message":message}})
}
fn dispatch(mode: Option<&str>, input: &str) -> serde_json::Value {
    if mode == Some("--interference") {
        match serde_json::from_str::<model_engine::interference::Request>(input) {
            Ok(request) => match model_engine::interference::inspect(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"interference","message":e.to_string()}})
            }
        }
    } else if mode == Some("--edge") {
        match serde_json::from_str::<model_engine::edge_measure::Request>(input) {
            Ok(request) => match model_engine::edge_measure::measure(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"edge","message":e.to_string()}})
            }
        }
    } else if mode == Some("--explain") {
        match serde_json::from_str::<model_engine::intent::Request>(input) {
            Ok(request) => match model_engine::intent::explain(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"intent","message":e.to_string()}})
            }
        }
    } else if mode == Some("--measure") {
        match serde_json::from_str::<model_engine::measure::Request>(input) {
            Ok(request) => match model_engine::measure::measure(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"measurement","message":e.to_string()}})
            }
        }
    } else if mode == Some("--topology") {
        match serde_json::from_str::<model_engine::topology::Request>(input) {
            Ok(request) => match model_engine::topology::inspect(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"topology","message":e.to_string()}})
            }
        }
    } else if mode == Some("--mesh") {
        match serde_json::from_str::<model_engine::mesh::Request>(input) {
            Ok(request) => match model_engine::mesh::evaluate(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"mesh","message":e.to_string()}})
            }
        }
    } else {
        match serde_json::from_str::<model_engine::Request>(input) {
            Ok(request) => match model_engine::evaluate(request) {
                Ok(value) => serde_json::json!({"result":value}),
                Err(error) => serde_json::json!({"error":error}),
            },
            Err(e) => {
                serde_json::json!({"error":{"code":"invalid_request","entity":"request","message":e.to_string()}})
            }
        }
    }
}
// Serial, stateless framed requests. The host owns deadlines, process lifetime,
// document history and job cancellation. Each payload is evaluated independently.
fn worker() -> io::Result<()> {
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    loop {
        let mut header = [0u8; 5];
        match input.read(&mut header[..1])? {
            0 => return Ok(()),
            _ => input.read_exact(&mut header[1..])?,
        }
        let size = u32::from_be_bytes(header[1..].try_into().unwrap()) as usize;
        if size > MAX_REQUEST {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Worker request exceeds 1 MiB",
            ));
        }
        let mut bytes = vec![0; size];
        input.read_exact(&mut bytes)?;
        let reply = match std::str::from_utf8(&bytes) {
            Err(_) => failure("request_limit", "Expected <= 1 MiB UTF-8 JSON"),
            Ok(text) => match header[0] {
                0 => dispatch(None, text),
                1 => dispatch(Some("--mesh"), text),
                2 => dispatch(Some("--explain"), text),
                3 => dispatch(Some("--measure"), text),
                4 => dispatch(Some("--topology"), text),
                5 => dispatch(Some("--edge"), text),
                6 => dispatch(Some("--interference"), text),
                _ => failure("invalid_request", "Unknown worker operation"),
            },
        };
        let mut response = serde_json::to_vec(&reply)?;
        if response.len() > MAX_RESPONSE {
            response =
                serde_json::to_vec(&failure("response_limit", "Worker response exceeds 16 MiB"))?;
        }
        output.write_all(&(response.len() as u32).to_be_bytes())?;
        output.write_all(&response)?;
        output.flush()?;
    }
}
fn main() {
    let mode = std::env::args().nth(1);
    if mode.as_deref() == Some("--worker") {
        if worker().is_err() {
            std::process::exit(1);
        }
        return;
    }
    let mut input = String::new();
    let result = io::stdin()
        .take((MAX_REQUEST + 1) as u64)
        .read_to_string(&mut input);
    let output = if result.is_err() || input.len() > MAX_REQUEST {
        failure("request_limit", "Expected <= 1 MiB UTF-8 JSON")
    } else {
        dispatch(mode.as_deref(), &input)
    };
    println!("{}", output);
    if output.get("error").is_some() {
        std::process::exit(1);
    }
}
