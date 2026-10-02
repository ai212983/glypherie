const nameKeys = ["family", "style", "full", "postscript", "version", "copyright", "manufacturer", "designer", "description", "vendor_url", "designer_url", "license", "license_url"];
const nullable = (value, predicate) => value === null || predicate(value);
const text = (value) => typeof value === "string" && value.trim().length > 0;
const integer = (value, max) => Number.isSafeInteger(value) && value >= 0 && value <= max;

function check(condition) {
  if (!condition) throw new Error("Invalid extracted font metadata.");
}

function fields(value, keys) {
  check(value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key)));
}

export function validateFontMetadata(metadata) {
  fields(metadata, ["names", "axes", "kerning", "style", "classification", "coverage", "declared_unicode_ranges"]);
  fields(metadata.names, nameKeys);
  check(Object.values(metadata.names).every((value) => nullable(value, text)));
  check(Array.isArray(metadata.axes));
  const tags = new Set();
  for (const axis of metadata.axes) {
    fields(axis, ["tag", "name", "min", "default", "max", "hidden"]);
    check(typeof axis.tag === "string" && /^[\x20-\x7e]{4}$/.test(axis.tag) && !tags.has(axis.tag)
      && nullable(axis.name, text) && [axis.min, axis.default, axis.max].every(Number.isFinite)
      && axis.min <= axis.default && axis.default <= axis.max && typeof axis.hidden === "boolean");
    tags.add(axis.tag);
  }
  fields(metadata.kerning, ["horizontal", "vertical", "sources"]);
  const { horizontal, vertical, sources } = metadata.kerning;
  check(typeof horizontal === "boolean" && typeof vertical === "boolean" && Array.isArray(sources)
    && sources.every((source) => ["GPOS kern", "GPOS vkrn", "kern", "kerx"].includes(source))
    && new Set(sources).size === sources.length && (sources.length > 0) === (horizontal || vertical)
    && (!sources.includes("GPOS kern") || horizontal) && (!sources.includes("GPOS vkrn") || vertical));
  fields(metadata.style, ["slope", "weight_class", "width_class", "italic_angle"]);
  check(nullable(metadata.style.slope, (value) => ["upright", "italic", "oblique"].includes(value))
    && nullable(metadata.style.weight_class, (value) => integer(value, 65535))
    && nullable(metadata.style.width_class, (value) => integer(value, 65535))
    && nullable(metadata.style.italic_angle, Number.isFinite));
  fields(metadata.classification, ["family_class", "panose", "monospaced"]);
  check(nullable(metadata.classification.family_class, (value) => integer(value, 65535))
    && nullable(metadata.classification.panose, (value) => Array.isArray(value) && value.length === 10 && value.every((byte) => integer(byte, 255)))
    && nullable(metadata.classification.monospaced, (value) => typeof value === "boolean"));
  check(nullable(metadata.declared_unicode_ranges, (value) => Array.isArray(value) && value.length === 4 && value.every((word) => integer(word, 0xffffffff))));
  if (metadata.coverage !== null) {
    fields(metadata.coverage, ["character_count", "ranges"]);
    check(integer(metadata.coverage.character_count, 0x110000) && Array.isArray(metadata.coverage.ranges));
    let previousEnd = -2;
    let count = 0;
    for (const range of metadata.coverage.ranges) {
      check(Array.isArray(range) && range.length === 2 && range.every((cp) => integer(cp, 0x10ffff))
        && range[0] <= range[1] && range[0] > previousEnd + 1 && (range[1] < 0xd800 || range[0] > 0xdfff));
      previousEnd = range[1];
      count += range[1] - range[0] + 1;
    }
    check(count === metadata.coverage.character_count);
  }
}

// OpenType OS/2.sFamilyClass (IBM) and PANOSE Family Kind/Serif Style.
// https://learn.microsoft.com/en-us/typography/opentype/spec/ibmfc
// https://monotype.github.io/panose/pan2.htm
const familyClasses = {
  1: "Oldstyle serif", 2: "Transitional serif", 3: "Modern serif", 4: "Clarendon serif",
  5: "Slab serif", 7: "Freeform serif", 8: "Sans serif", 9: "Ornamental", 10: "Script", 12: "Symbol",
};

function classificationLabel(classification) {
  const ibm = classification.family_class === null ? null : familyClasses[classification.family_class >> 8];
  if (ibm) return ibm;
  const panose = classification.panose;
  if (!panose) return "";
  if (panose[0] === 2) {
    if (panose[1] >= 2 && panose[1] <= 10) return "Serif";
    if (panose[1] >= 11 && panose[1] <= 15) return "Sans serif";
    return "Text and display";
  }
  return { 3: "Handwritten", 4: "Decorative", 5: "Symbol" }[panose[0]] ?? "";
}

export function fontMetadataView(metadata) {
  if (!metadata) return { kerningLabel: "Unknown", axesLabel: "Unknown", classificationLabel: "" };
  const { horizontal, vertical } = metadata.kerning;
  const classification = [classificationLabel(metadata.classification)];
  if (metadata.classification.monospaced !== null) classification.push(metadata.classification.monospaced ? "Monospaced" : "Proportional");
  return {
    kerningLabel: horizontal ? (vertical ? "Yes · horizontal and vertical" : "Yes") : (vertical ? "Vertical only" : "No"),
    axesLabel: metadata.axes.length ? metadata.axes.map((axis) => `${axis.name ? `${axis.name} (${axis.tag})` : axis.tag}: ${axis.min}–${axis.max} (default ${axis.default})`).join("; ") : "None · static font",
    classificationLabel: classification.filter(Boolean).join(" · "),
  };
}
