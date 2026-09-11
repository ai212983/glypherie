"""Explicit overlap assumption for Shamir 2003 sections 3.5–3.6.

The source specifies dominant segment representatives, ordinary priorities and
point-cycle resolution, followed by member attachments. It leaves points with
both roles unspecified. We include links targeting an existing representative in
its reduced graph so they receive those published conflict/cycle rules. Ordinary
members remain in the later phase. This is an interpretation, not a recovered
author implementation; no new points or constraint kinds are introduced.
"""


def close_shared_roles(dominant_constraints, attachments, representatives):
    """Partition member links after segment dominance, preserving provenance.

    The caller passes the returned reduced candidates to the point resolver and
    the late attachments to member completion. All original attachment metadata
    survives so selected/rejected outcomes can still identify each proposal.
    """
    representatives = set(representatives)
    reduced = [dict(c, sources=list(c['sources'])) for c in dominant_constraints]
    for c in reduced:
        if c['point'] not in representatives or not set(c['sources']) <= representatives:
            raise ValueError('dominant relation outside representative graph')
    shared, late = [], []
    for proposal in attachments:
        c = dict(proposal, sources=list(proposal['sources']))
        if not set(c['sources']) <= representatives:
            raise ValueError('member attachment source is not a representative')
        if c['point'] in representatives:
            c['shared_role_assumption'] = 'B11-representative-role-closure'
            shared.append(c)
        else:
            late.append(c)
    return dict(reduced_candidates=reduced+shared, shared_attachments=shared,
                late_attachments=late, assumption='B11-representative-role-closure')
