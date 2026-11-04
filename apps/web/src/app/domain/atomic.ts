// One outer Drizzle transaction covering graph and auxiliary writes, the same
// shape the legacy importer uses: graph writes go through a transaction-scoped
// store bound to the same handle, so nested store transactions ride savepoints
// and a failed preference write rolls back the graph write with it.

import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { createStore } from "@nicia-ai/typegraph";
import { domainGraph } from "./graph.ts";
import type { AuxDb, DomainBackend } from "./backend.ts";

type TxStore = DomainBackend["store"];

export async function withAtomicDomain<T>(
  backend: DomainBackend,
  run: (txStore: TxStore, txAux: AuxDb) => Promise<T>,
): Promise<T> {
  return backend.db.transaction(async (txDb) => {
    const txStore = createStore(
      domainGraph,
      createPostgresBackend(txDb as never, { vector: false, fulltext: false }),
    ) as TxStore;
    return run(txStore, txDb as unknown as AuxDb);
  });
}
