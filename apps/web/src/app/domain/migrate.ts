// One-way legacy migration trigger. Runs from the font library boot path:
// if the legacy Dexie database holds rows and the domain has no completion
// marker for that exact snapshot, the snapshot crosses to the domain worker
// in one RPC and commits atomically there. Dexie is only ever read.

import { callDomain } from "./runtime.ts";
import { legacyCounts, readLegacySnapshot } from "../legacy-database.ts";

let migrationInFlight: Promise<{ imported: boolean }> | null = null;

async function migrateInner(): Promise<{ imported: boolean }> {
  // A storage failure here is recoverable, not an empty library: let it throw
  // so boot shows the migration notice and a later boot retries.
  const counts = await legacyCounts();
  if (counts.fonts === 0 && counts.variants === 0 && counts.palettes === 0) return { imported: false };
  const snapshot = await readLegacySnapshot();
  const result = await callDomain("importLegacySnapshot", [snapshot]);
  if (!result.skipped && result.skippedVariantIds.length > 0) {
    throw new Error(`Legacy import skipped ${result.skippedVariantIds.length} variants with missing fonts.`);
  }
  return { imported: !result.skipped };
}

export function ensureDomainMigrated(): Promise<{ imported: boolean }> {
  if (!migrationInFlight) {
    migrationInFlight = migrateInner().finally(() => {
      migrationInFlight = null;
    });
  }
  return migrationInFlight;
}
