// Canonical scene layer ordering: top-first by paint order, id-tied.
// One rule shared by the layers panel, the document-edit intents and the
// workspace, so a reorder computed anywhere lands on the same neighbors.
import type { DomainPlacementView } from "../../domain/types.js";

export function sortLayersTopFirst(placements: readonly DomainPlacementView[]): DomainPlacementView[] {
  return [...placements].sort(
    (left, right) => right.order - left.order || (left.id < right.id ? 1 : left.id > right.id ? -1 : 0),
  );
}
