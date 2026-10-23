pub struct Bitmap<'a> {
    width: usize,
    height: usize,
    ink: &'a [bool],
}

impl<'a> Bitmap<'a> {
    /// Returns `None` if `width * height` overflows or differs from `ink.len()`.
    pub fn new(width: usize, height: usize, ink: &'a [bool]) -> Option<Self> {
        if width.checked_mul(height) == Some(ink.len()) {
            Some(Bitmap { width, height, ink })
        } else {
            None
        }
    }

    /// Counts of `[8-connected ink components, enclosed 4-connected background components]`.
    pub fn counts(&self) -> [usize; 2] {
        let mut visited = vec![false; self.ink.len()];
        let mut queue = Vec::new();
        let mut counts = [0, 0];
        for start in 0..self.ink.len() {
            if visited[start] {
                continue;
            }
            let (color, boundary) = flood_fill(self, start, &mut visited, &mut queue);
            if color {
                counts[0] += 1;
            } else if !boundary {
                counts[1] += 1;
            }
        }
        counts
    }
}

// Complementary adjacency avoids calling a diagonal ink contact both a bridge
// and a background crossing. Enclosed background is measured against the
// actual bitmap boundary, equivalent to a surrounding white frame.
const INK_OFFSETS: [(isize, isize); 8] = [
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
];

const WHITE_OFFSETS: [(isize, isize); 4] = [(0, -1), (-1, 0), (1, 0), (0, 1)];

fn neighbors(
    index: usize,
    width: usize,
    height: usize,
    eight: bool,
) -> impl Iterator<Item = usize> {
    let x = index % width;
    let y = index / width;
    let offsets: &[(isize, isize)] = if eight { &INK_OFFSETS } else { &WHITE_OFFSETS };
    offsets.iter().filter_map(move |(dx, dy)| {
        let xx = x as isize + dx;
        let yy = y as isize + dy;
        if xx < 0 || yy < 0 || xx >= width as isize || yy >= height as isize {
            None
        } else {
            Some(yy as usize * width + xx as usize)
        }
    })
}

fn flood_fill(
    bitmap: &Bitmap<'_>,
    start: usize,
    visited: &mut [bool],
    queue: &mut Vec<usize>,
) -> (bool, bool) {
    let color = bitmap.ink[start];
    queue.clear();
    queue.push(start);
    visited[start] = true;
    let mut next = 0;
    let mut boundary = false;
    while next < queue.len() {
        let p = queue[next];
        next += 1;
        let x = p % bitmap.width;
        let y = p / bitmap.width;
        boundary |= x == 0 || y == 0 || x + 1 == bitmap.width || y + 1 == bitmap.height;
        for q in neighbors(p, bitmap.width, bitmap.height, color) {
            if !visited[q] && bitmap.ink[q] == color {
                visited[q] = true;
                queue.push(q);
            }
        }
    }
    (color, boundary)
}

#[cfg(test)]
mod tests;
