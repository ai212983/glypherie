use crate::{
    probe::{rasterize, FittedCommand},
    Config, Error,
};

pub(crate) fn render(
    commands: &[FittedCommand],
    config: &Config,
    dropout_enabled: bool,
) -> Result<(Vec<u8>, i32, i32, u32, u32), Error> {
    if commands.is_empty() {
        return Ok((vec![], 0, 0, 0, 0));
    }
    // Approved dropout rasterizes only actually enabled Mono automatic output;
    // all other paths keep the upstream coverage rasterizer and its placement.
    let output = if dropout_enabled {
        crate::dropout::rasterize(commands, config)?
    } else {
        rasterize(commands, config)?
    };
    Ok((
        output.pixels,
        output.left,
        output.top,
        output.width,
        output.height,
    ))
}
