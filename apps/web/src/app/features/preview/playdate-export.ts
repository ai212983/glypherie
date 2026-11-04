// Standalone Playdate export adapter. Structured coverage is the product
// model; the single string conversion lives in domain/font-export.ts.
import type { PlaydateExportRequest } from "../../renderer/renderer-types.ts";
import type { VariantSettings } from "../../variants/model.ts";
import {
  CoverageError,
  coverageCount,
  resolveCoverage,
  splitCoverageByAvailability,
  type CharacterCoverage,
  type CodepointRange,
} from "../../domain/coverage.ts";
import { playdateFileName, playdateRequestForSettings, splitExportWindow } from "../../domain/font-export.ts";

export { playdateFileName };

// Printable ASCII expectation helper for coverage tests; product state
// carries presets and ranges, never this string.
export const PLAYDATE_ASCII = Array.from({ length: 95 }, (_, i) => String.fromCodePoint(i + 32)).join("");

export function playdateRequest(settings: VariantSettings, coverage: CharacterCoverage): PlaydateExportRequest {
  return playdateRequestForSettings(settings, coverage);
}

export interface PlaydateCoveredSplit {
  covered: CodepointRange[];
  // Null when font coverage is unknown: the full requested set generates.
  missing: CodepointRange[] | null;
  supported: CodepointRange[];
  unsupported: CodepointRange[];
}

// The scene/ZIP availability preflight for the standalone exporter: only the
// font-covered set generates, missing ranges stay visible, and the window
// split reports characters outside the Playdate subset instead of dropping
// them. The requested selection is never modified here.
export function splitPlaydateCoverage(
  coverage: CharacterCoverage,
  availableRanges?: readonly CodepointRange[],
): PlaydateCoveredSplit {
  const requested = resolveCoverage(coverage);
  const availability = availableRanges ? splitCoverageByAvailability(requested, availableRanges) : null;
  const covered = availability ? availability.covered : requested;
  const window = splitExportWindow(covered);
  return {
    covered,
    missing: availability ? availability.missing : null,
    supported: window.supported,
    unsupported: window.unsupported,
  };
}

export function playdateCoveredRequest(
  settings: VariantSettings,
  coverage: CharacterCoverage,
  availableRanges?: readonly CodepointRange[],
): PlaydateExportRequest {
  const split = splitPlaydateCoverage(coverage, availableRanges);
  if (split.unsupported.length > 0) {
    throw new CoverageError(
      `Coverage holds ${coverageCount(split.unsupported)} characters outside the Playdate export subset.`,
    );
  }
  return playdateRequestForSettings(settings, { presetIds: [], extraRanges: split.supported });
}
