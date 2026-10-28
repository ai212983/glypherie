//! Native counterpart for the Playdate WASM parity smoke test.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 3 {
        return Err("usage: playdate_reference FONT REQUEST.json OUTPUT.fnt".into());
    }
    let request = serde_json::from_slice(&std::fs::read(&args[1])?)?;
    let bytes = font_generator::playdate::export(&std::fs::read(&args[0])?, &request)?;
    std::fs::write(&args[2], bytes)?;
    Ok(())
}
