"""Published 1996 §4.4 recognizers and conservative B05 authored recipes.

This limited baseline recognizes the two published example sequences. Its local
translation recipes are an explicit assumption, not the authors' recovered library.
"""
PUBLISHED_SEQUENCES = {
    'MinchoBarCap': [['HR', 'CH', 'T', 'V', 'T']],
    # The paper figure calls these LC; its category definition calls them LR.
    'RomanSerif': [['T', 'T', 'LR', 'LR', 'LR', 'LR', 'T', 'T']],
}


def recognize_sequence_pool(point_ids, categories, templates):
    """Traverse twice, resetting recognizers after acceptance (§4.4).

    ``subautomata`` on an including template names recognizers that may accept
    without resetting it. Both hits are retained: choosing between them requires
    authored transition predicates or font-specific activation. Simultaneous
    accepting machines are reported together, without an invented priority.
    """
    count = len(point_ids)
    machines = [(name, tuple(sequence)) for name, template in templates.items()
                for sequence in template.get('sequences', ())
                if 0 < len(sequence) <= count]
    for name, template in templates.items():
        unknown = set(template.get('subautomata', ())) - set(templates)
        if unknown:
            raise ValueError(f'{name}: unknown subautomata {sorted(unknown)}')
    states = [[] for _ in machines]
    hits = []
    seen = set()
    for position in range(2 * count):
        point = point_ids[position % count]
        accepted = []
        for index, (name, sequence) in enumerate(machines):
            # Prefix alternatives implement substring recognition, including a
            # new start after a partial match fails. Each start is visited once.
            paths = states[index] + ([[]] if position < count else [])
            active = []
            for path in paths:
                if sequence[len(path)] not in categories[point]:
                    continue
                path = path + [point]
                if len(path) == len(sequence):
                    key = (name, tuple(path))
                    if key not in seen:
                        seen.add(key)
                        accepted.append(dict(name=name, points=path))
                else:
                    active.append(path)
            states[index] = active
        if accepted:
            hits.extend(accepted)
            names = {hit['name'] for hit in accepted}
            for index, (name, _) in enumerate(machines):
                # A specified including automaton survives its child's hit.
                # A machine that has itself accepted always resets.
                if name in names or not names <= set(templates[name].get('subautomata', ())):
                    states[index] = []
    return hits


def recognize_baseline_templates(model, templates=None):
    """Return recognized-but-unconfigured complex features, never constraints."""
    if templates is None:
        templates = {name: dict(sequences=sequences)
                     for name, sequences in PUBLISHED_SEQUENCES.items()}
    hits = []
    categories = {p['id']: p['categories'] for p in model['points']}
    for contour in model['contours']:
        ids = [model['segments'][sid]['start'] for sid in contour]
        # Prepared quadratic subdivision adds plain smooth joins. They are not
        # events in the published serif sequences; extrema and inflections stay.
        ids = [pid for pid in ids if categories[pid] not in (['CT'], ['line'])]
        hits.extend(recognize_sequence_pool(ids, categories, templates))
    return dict(matches=hits,
                unconfigured=[dict(hit, reason='published recognition example; authored constraint recipe unavailable')
                              for hit in hits],
                bindings=[], policy='1996 section 4.4 traversal and reset',
                recipe_coverage='none; complex-feature hinting unsupported',
                classification='conservative limited coverage')



def matched_native_members(model, mapping, hit):
    """All native points from the first matched event through the final event.

    Controls of outgoing segments after the final event belong to the remainder
    of the contour. Wrapping spans follow contour order rather than index order.
    """
    first, last = hit['points'][0], hit['points'][-1]
    contour = next(loop for loop in model['contours']
                   if any(model['segments'][sid]['start'] == first for sid in loop))
    start = next(i for i, sid in enumerate(contour) if model['segments'][sid]['start'] == first)
    members = {mapping[first], mapping[last]}
    for offset in range(len(contour)):
        segment = model['segments'][contour[(start + offset) % len(contour)]]
        if segment['start'] == last:
            break
        native_start = mapping[segment['start']]
        members.update(range(native_start, native_start + len(segment['control']) - 1))
        members.add(mapping[segment['end']])
    return sorted(members)

def instantiate_baseline_templates(model, mapping, points, basic_groups=(), basic_features=()):
    """Instantiate conservative, locally translating recipes for published types.

    2003 §3.5 requires an authored constraint set for each complex feature but
    does not publish these sets. B05's assumption rounds the first sequence point
    on character axes and preserves every other matched point's original offset.
    Existing basic constraints compete through the ordinary published priorities;
    this recipe neither suppresses basic features nor silently claims ownership.
    Controls and skipped smooth joins within the matched span follow the same
    anchor as member attachments. They introduce no new geometric anchors;
    callers must keep template_member constraints outside the representative set.
    """
    from shamir_constraints import relation
    diagnostics = recognize_baseline_templates(model)
    constraints = []
    for hit in diagnostics['matches']:
        ids = [mapping[pid] for pid in hit['points']]
        hit['native_points'] = ids
        hit['native_members'] = matched_native_members(model, mapping, hit)
        hit['recipe'] = 'B05: rounded first point; original unrounded local offsets'
        anchor = ids[0]
        for axis in (0, 1):
            normal = [int(axis == 0), int(axis == 1)]
            constraints.append(relation('Abs', anchor, normal,
                                        value=float(points[anchor, axis]),
                                        feature=hit['name']))
            for point in hit['native_members']:
                if point == anchor:
                    continue
                constraints.append(relation('Dist', point, normal, [anchor],
                                            float(points[point, axis] - points[anchor, axis]),
                                            round=False,
                                            feature=(f"{hit['name']}-member-{anchor}-{axis}" if point not in ids else hit['name']),
                                            template_member=point not in ids))
    diagnostics.update(unconfigured=[],
                       recipe_coverage='two published recognizers; conservative local translation recipes',
                       classification='B05 conservative assumption; author recipe library unavailable')
    return constraints, diagnostics
