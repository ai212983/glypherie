"""Order geometric operations by point-axis ownership; report ambiguous graphs."""


def schedule(operations):
    """Operations carry read/write sets of (point, axis), plus a stable id."""
    writers = {}
    conflicts = []
    for i, operation in enumerate(operations):
        for key in operation['writes']:
            writers.setdefault(key, []).append(i)
    for key, owners in sorted(writers.items()):
        if len(owners) > 1:
            conflicts.append(dict(kind='multiple-writers', point_axis=list(key),
                                  operations=[operations[i]['id'] for i in owners]))
    edges = {i: set() for i in range(len(operations))}
    for consumer, operation in enumerate(operations):
        for key in operation['reads']:
            for producer in writers.get(key, []):
                if producer != consumer:
                    edges[consumer].add(producer)
    pending = set(edges)
    order = []
    while pending:
        ready = sorted(i for i in pending if not edges[i] & pending)
        if not ready:
            conflicts.append(dict(kind='dependency-cycle',
                                  operations=[operations[i]['id'] for i in sorted(pending)]))
            break
        order.extend(ready)
        pending.difference_update(ready)
    audit = dict(order=[operations[i]['id'] for i in order], conflicts=conflicts,
                 dependencies=[dict(operation=operations[i]['id'],
                                    after=[operations[j]['id'] for j in sorted(edges[i])])
                               for i in edges])
    return (None if conflicts else order), audit
