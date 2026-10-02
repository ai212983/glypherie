use crate::{
    probe::{rasterize, FittedCommand},
    Config, Error,
};

pub(crate) fn render(
    commands: &[FittedCommand],
    config: &Config,
) -> Result<(Vec<u8>, i32, i32, u32, u32), Error> {
    if commands.is_empty() {
        return Ok((vec![], 0, 0, 0, 0));
    }
    let output = rasterize(commands, config)?;
    Ok((
        output.pixels,
        output.left,
        output.top,
        output.width,
        output.height,
    ))
}
