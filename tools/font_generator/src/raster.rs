use crate::{fail, Config, Error};
use skrifa::outline::OutlinePen;
use zeno::{Command, Format, Mask, Point};

#[derive(Default)]
pub(crate) struct Pen {
    commands: Vec<Command>,
}
impl OutlinePen for Pen {
    fn move_to(&mut self, x: f32, y: f32) {
        self.commands.push(Command::MoveTo(Point::new(x, -y)));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.commands.push(Command::LineTo(Point::new(x, -y)));
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        self.commands
            .push(Command::QuadTo(Point::new(x1, -y1), Point::new(x, -y)));
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        self.commands.push(Command::CurveTo(
            Point::new(x1, -y1),
            Point::new(x2, -y2),
            Point::new(x, -y),
        ));
    }
    fn close(&mut self) {
        self.commands.push(Command::Close);
    }
}
// Curve control points bound the path, permitting allocation checks before rasterization.
pub(crate) fn render(pen: &Pen, config: &Config) -> Result<(Vec<u8>, i32, i32, u32, u32), Error> {
    if pen.commands.is_empty() {
        return Ok((vec![], 0, 0, 0, 0));
    }
    let mut min = Point::new(f32::INFINITY, f32::INFINITY);
    let mut max = Point::new(f32::NEG_INFINITY, f32::NEG_INFINITY);
    let mut point = |p: Point| -> Result<(), Error> {
        if !p.x.is_finite() || !p.y.is_finite() || p.x.abs() > 32768.0 || p.y.abs() > 32768.0 {
            return Err(fail("outline coordinate exceeds supported bounds"));
        }
        min.x = min.x.min(p.x);
        min.y = min.y.min(p.y);
        max.x = max.x.max(p.x);
        max.y = max.y.max(p.y);
        Ok(())
    };
    for command in &pen.commands {
        match *command {
            Command::MoveTo(p) | Command::LineTo(p) => point(p)?,
            Command::QuadTo(a, b) => {
                point(a)?;
                point(b)?;
            }
            Command::CurveTo(a, b, c) => {
                point(a)?;
                point(b)?;
                point(c)?;
            }
            Command::Close => {}
        }
    }
    let width = max.x.ceil() - min.x.floor();
    let height = max.y.ceil() - min.y.floor();
    if width * height > 4_194_304.0 {
        return Err(fail("glyph bitmap exceeds 4 Mi pixels"));
    }
    let (coverage, placement) = Mask::new(pen.commands.as_slice())
        .format(Format::Alpha)
        .render();
    let levels = (1u16 << config.output_bits) - 1;
    let pixels = coverage
        .into_iter()
        .map(|v| {
            if config.output_bits == 1 {
                u8::from(v >= config.mono_threshold)
            } else {
                ((v as f32 / 255.0).powf(config.gray_gamma) * levels as f32).round() as u8
            }
        })
        .collect();
    Ok((
        pixels,
        placement.left,
        placement.top,
        placement.width,
        placement.height,
    ))
}
