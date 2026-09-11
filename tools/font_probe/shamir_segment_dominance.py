"""Select one dominant relation per segment before the representative point DAG.

Shamir 2003 §3.6 simplifies segments to their dominant relations. Published
priorities apply within each segment; declaration order breaks ties explicitly.
Metric and template relations have separate ownership and pass through unchanged.
"""
from shamir_constraints import priority


def dominant_relations(candidates):
    groups = {}
    for i, c in enumerate(candidates):
        if 'segment_owner' in c:
            groups.setdefault(c['segment_owner'], []).append((i, c))
    keep, rejected, warnings = set(), [], []
    for owner, members in groups.items():
        selected = max(members, key=lambda item: (priority(item[1]), -item[0]))
        keep.add(selected[0])
        for i, c in members:
            if i == selected[0]:
                continue
            rejected.append(dict(constraint=c, reason='superseded segment relation',
                                 selected_feature=selected[1].get('feature')))
            if priority(c) == priority(selected[1]):
                warnings.append(dict(kind='segment priority tie', segment_owner=owner,
                                     selected_feature=selected[1].get('feature'),
                                     discarded_feature=c.get('feature')))
    return ([c for i, c in enumerate(candidates) if 'segment_owner' not in c or i in keep],
            dict(rejected=rejected, warnings=warnings))
