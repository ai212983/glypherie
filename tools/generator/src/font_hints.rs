//! Conservative TrueType program check for candidate `FontHintsFirst`.
//!
//! Registry Skrifa 0.48 `Engine::AutoFallback` follows FreeType: any nonzero
//! `maxp.maxSizeOfInstructions`, nonempty `fpgm`, or nonempty `prep` selects the
//! interpreter
//! (<https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html>).
//! A scan-control-only `prep` program therefore blocks automatic fitting even
//! though it carries no outline instructions. Per the `prep` specification, no
//! glyph-associated outline points can be moved by `prep`
//! (<https://learn.microsoft.com/en-us/typography/opentype/spec/prep>), and
//! `SCANCTRL`/`SCANTYPE` only tune scan conversion
//! (<https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control>),
//! which the automatic fitting path does not execute; font scan state is
//! available separately when embedded TrueType fitting is selected.
//!
//! This is a deliberate project policy adaptation, not upstream behavior: when
//! a TrueType font is verified to carry no glyph instruction streams
//! (simple or composite), no `fpgm`, and an absent or scan-control-only
//! `prep`, candidate `FontHintsFirst` uses upstream automatic Mono fitting.
//! Anything else (CFF/CFF2/VARC outlines, present `fpgm`, unrecognized or
//! malformed `prep`, any glyph instructions, malformed tables) conservatively
//! retains upstream engine selection. The decision is font-wide and structural;
//! requested glyphs, sizes, or names never participate. Instruction presence
//! comes from actual glyph data, not `maxp.maxSizeOfInstructions`.

/// Opcodes recognized in a scan-control-only `prep` program.
const PUSHB_MIN: u8 = 0xB0;
const PUSHB_MAX: u8 = 0xB7;
const PUSHW_MIN: u8 = 0xB8;
const PUSHW_MAX: u8 = 0xBF;
const SCANCTRL: u8 = 0x85;
const SCANTYPE: u8 = 0x8D;

/// Composite glyph component flags
/// (<https://learn.microsoft.com/en-us/typography/opentype/spec/glyf>).
const ARG_1_AND_2_ARE_WORDS: u16 = 0x0001;
const WE_HAVE_A_SCALE: u16 = 0x0008;
const MORE_COMPONENTS: u16 = 0x0020;
const WE_HAVE_AN_X_AND_Y_SCALE: u16 = 0x0040;
const WE_HAVE_A_TWO_BY_TWO: u16 = 0x0080;
const WE_HAVE_INSTRUCTIONS: u16 = 0x0100;

/// Decide once per font whether candidate `FontHintsFirst` may use upstream
/// automatic Mono fitting instead of upstream engine selection. Pure function
/// of the raw font bytes: no global state is read or written.
pub(crate) fn use_automatic(data: &[u8]) -> bool {
    let Some(tables) = directory(data) else {
        return false;
    };
    // CFF/CFF2/VARC outlines keep upstream behavior; only TrueType `glyf`
    // fonts are eligible.
    for tag in [b"CFF ", b"CFF2", b"VARC"] {
        if tables.contains_key(tag) {
            return false;
        }
    }
    let (Some(glyf_entry), Some(loca_entry), Some(head_entry), Some(maxp_entry)) = (
        tables.get(b"glyf").copied(),
        tables.get(b"loca").copied(),
        tables.get(b"head").copied(),
        tables.get(b"maxp").copied(),
    ) else {
        return false;
    };
    if let Some(fpgm_entry) = tables.get(b"fpgm").copied() {
        if table_bytes(data, fpgm_entry).is_none_or(|program| !program.is_empty()) {
            return false;
        }
    }
    let max_stack = match tables
        .get(b"maxp")
        .copied()
        .and_then(|entry| table_bytes(data, entry))
    {
        Some(maxp) if maxp.len() >= 26 => {
            u16::from_be_bytes([maxp[24], maxp[25]]).saturating_add(32)
        }
        _ => return false,
    };
    if let Some(prep_entry) = tables.get(b"prep").copied() {
        match table_bytes(data, prep_entry) {
            Some(prep) if prep.is_empty() => {}
            Some(prep) if is_scan_control_only(prep, max_stack) => {}
            _ => return false,
        }
    }
    let (Some(glyf), Some(loca), Some(head), Some(maxp)) = (
        table_bytes(data, glyf_entry),
        table_bytes(data, loca_entry),
        table_bytes(data, head_entry),
        table_bytes(data, maxp_entry),
    ) else {
        return false;
    };
    let Some(ranges) = glyph_ranges(head, loca, maxp, glyf.len()) else {
        return false;
    };
    glyphs_have_no_instructions(glyf, &ranges)
}

/// Recognize a `prep` program of pushed scan-control operands consuming every
/// pushed value. Anything outside `PUSHB`/`PUSHW`/`SCANCTRL`/`SCANTYPE`,
/// truncated operands, a control pop with no pushed value, leftover stack
/// values, a program with no control operation, or push depth beyond
/// `max_stack` is unrecognized and retains upstream selection, including its
/// setup errors. The limit mirrors Skrifa's interpreter stack sizing,
/// `maxp.max_stack_elements` saturating-added with 32 per its FreeType
/// heuristic, so an overflowing program keeps failing upstream instead of
/// being silently fitted automatically. See the pinned stack-sizing source:
/// <https://docs.rs/skrifa/0.48.0/src/skrifa/outline/glyf/mod.rs.html>.
fn is_scan_control_only(prep: &[u8], max_stack: u16) -> bool {
    let mut index = 0usize;
    let mut depth = 0usize;
    let mut saw_control = false;
    while index < prep.len() {
        let opcode = prep[index];
        if (PUSHB_MIN..=PUSHB_MAX).contains(&opcode) {
            let count = usize::from(opcode - PUSHB_MIN) + 1;
            index = match index.checked_add(1 + count) {
                Some(next) if next <= prep.len() => next,
                _ => return false,
            };
            depth += count;
            if depth > usize::from(max_stack) {
                return false;
            }
        } else if (PUSHW_MIN..=PUSHW_MAX).contains(&opcode) {
            let count = usize::from(opcode - PUSHW_MIN) + 1;
            index = match index.checked_add(1 + 2 * count) {
                Some(next) if next <= prep.len() => next,
                _ => return false,
            };
            depth += count;
            if depth > usize::from(max_stack) {
                return false;
            }
        } else if opcode == SCANCTRL || opcode == SCANTYPE {
            if depth == 0 {
                return false;
            }
            depth -= 1;
            saw_control = true;
            index += 1;
        } else {
            return false;
        }
    }
    saw_control && depth == 0
}

type TableMap<'a> = std::collections::HashMap<&'a [u8; 4], (usize, usize)>;

/// Read the sfnt table directory into tag-to-(offset, length) entries.
/// Malformed directories (short data, out-of-range entries, duplicate tags)
/// return `None`. Duplicates are rejected because `read-fonts` resolves them
/// by sorted binary search or first match while a map would keep the last,
/// so accepting them could diverge from upstream table selection.
fn directory(data: &[u8]) -> Option<TableMap<'_>> {
    if data.len() < 12 {
        return None;
    }
    let count = u16::from_be_bytes([data[4], data[5]]) as usize;
    if data.len() < 12 + 16 * count {
        return None;
    }
    let mut tables = TableMap::new();
    for i in 0..count {
        let base = 12 + 16 * i;
        let tag: &[u8; 4] = data[base..base + 4].try_into().ok()?;
        let offset = u32::from_be_bytes(data[base + 8..base + 12].try_into().ok()?) as usize;
        let length = u32::from_be_bytes(data[base + 12..base + 16].try_into().ok()?) as usize;
        if offset.checked_add(length)?.gt(&data.len()) {
            return None;
        }
        if tables.insert(tag, (offset, length)).is_some() {
            return None;
        }
    }
    Some(tables)
}

/// Slice a table's bytes with checked bounds; out-of-range entries are
/// malformed and yield `None`.
fn table_bytes(data: &[u8], entry: (usize, usize)) -> Option<&[u8]> {
    data.get(entry.0..entry.0.checked_add(entry.1)?)
}

/// Resolve every glyph byte range from `head`/`loca`/`maxp` against the `glyf`
/// length. Non-monotonic or out-of-range offsets are malformed.
fn glyph_ranges(
    head: &[u8],
    loca: &[u8],
    maxp: &[u8],
    glyf_len: usize,
) -> Option<Vec<(usize, usize)>> {
    if head.len() < 54 || maxp.len() < 6 {
        return None;
    }
    let long = match u16::from_be_bytes([head[50], head[51]]) {
        0 => false,
        1 => true,
        _ => return None,
    };
    let num_glyphs = u16::from_be_bytes([maxp[4], maxp[5]]) as usize;
    if num_glyphs == 0 {
        return None;
    }
    let entry_len = if long { 4 } else { 2 };
    if loca.len() != (num_glyphs + 1).checked_mul(entry_len)? {
        return None;
    }
    let mut offsets = Vec::with_capacity(num_glyphs + 1);
    for i in 0..=num_glyphs {
        let offset = if long {
            u32::from_be_bytes(loca[4 * i..4 * i + 4].try_into().ok()?) as usize
        } else {
            usize::from(u16::from_be_bytes(loca[2 * i..2 * i + 2].try_into().ok()?)) * 2
        };
        if offset > glyf_len {
            return None;
        }
        offsets.push(offset);
    }
    if offsets.windows(2).any(|pair| pair[0] > pair[1]) {
        return None;
    }
    Some(
        offsets
            .windows(2)
            .map(|pair| (pair[0], pair[1]))
            .collect::<Vec<_>>(),
    )
}

/// Verify every nonempty glyph carries no instructions. Simple glyphs expose
/// their instruction length after the contour endpoints; composite glyphs
/// carry trailing instructions when the final component sets
/// `WE_HAVE_INSTRUCTIONS`. Any present instructions or malformed glyph data
/// return `false`.
fn glyphs_have_no_instructions(glyf: &[u8], ranges: &[(usize, usize)]) -> bool {
    for (start, end) in ranges {
        let glyph = match glyf.get(*start..*end) {
            Some(glyph) if glyph.is_empty() => continue,
            Some(glyph) => glyph,
            None => return false,
        };
        if glyph.len() < 10 {
            return false;
        }
        let contours = i16::from_be_bytes([glyph[0], glyph[1]]);
        if contours > 0 {
            let ends = 10usize
                .checked_add(2 * contours as usize)
                .and_then(|end| end.checked_add(2));
            let Some(ends) = ends else { return false };
            if glyph.len() < ends {
                return false;
            }
            if u16::from_be_bytes([glyph[ends - 2], glyph[ends - 1]]) != 0 {
                return false;
            }
        } else if contours == -1 {
            if composite_has_instructions(glyph).is_none_or(|has| has) {
                return false;
            }
        } else {
            return false;
        }
    }
    true
}

/// Walk a composite glyph's component records. Returns `None` on malformed
/// data, otherwise whether trailing instructions are present and nonempty.
fn composite_has_instructions(glyph: &[u8]) -> Option<bool> {
    let mut cursor = 10usize;
    loop {
        let flags = u16::from_be_bytes(glyph.get(cursor..cursor + 2)?.try_into().ok()?);
        cursor += 4;
        cursor = cursor.checked_add(if flags & ARG_1_AND_2_ARE_WORDS != 0 {
            4
        } else {
            2
        })?;
        cursor = cursor.checked_add(if flags & WE_HAVE_A_SCALE != 0 {
            2
        } else if flags & WE_HAVE_AN_X_AND_Y_SCALE != 0 {
            4
        } else if flags & WE_HAVE_A_TWO_BY_TWO != 0 {
            8
        } else {
            0
        })?;
        if cursor > glyph.len() {
            return None;
        }
        if flags & MORE_COMPONENTS == 0 {
            if flags & WE_HAVE_INSTRUCTIONS == 0 {
                return Some(false);
            }
            let count =
                u16::from_be_bytes(glyph.get(cursor..cursor + 2)?.try_into().ok()?) as usize;
            if cursor.checked_add(2 + count)? > glyph.len() {
                return None;
            }
            return Some(count != 0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::is_scan_control_only;

    #[test]
    fn scan_control_programs_are_recognized() {
        // Literata/SourceSans3 `prep`: PUSHW 511, SCANCTRL, PUSHB 4, SCANTYPE.
        assert!(is_scan_control_only(
            &[0xb8, 0x01, 0xff, 0x85, 0xb0, 0x04, 0x8d],
            32
        ));
        assert!(is_scan_control_only(&[0xb0, 0x01, 0x85], 32));
        assert!(!is_scan_control_only(&[], 32));
        assert!(!is_scan_control_only(&[0xb0, 0x01], 32));
        assert!(!is_scan_control_only(&[0x85], 32));
        assert!(!is_scan_control_only(&[0x00], 32));
        assert!(!is_scan_control_only(&[0xb0], 32));
        assert!(!is_scan_control_only(&[0xb8, 0x01], 32));
        assert!(!is_scan_control_only(&[0xb0, 0x01, 0x85, 0x00], 32));
        // Leftover stack values are outside the recognized grammar.
        assert!(!is_scan_control_only(&[0xb0, 0x01, 0xb0, 0x02, 0x85], 32));
        // Push depth beyond the interpreter stack limit is rejected: eight
        // pushes drained by eight controls fit a limit of eight but not seven.
        let mut deep = vec![0xb7, 0, 0, 0, 0, 0, 0, 0, 0];
        deep.extend([0x85; 8]);
        assert!(is_scan_control_only(&deep, 8));
        assert!(!is_scan_control_only(&deep, 7));
    }
}
