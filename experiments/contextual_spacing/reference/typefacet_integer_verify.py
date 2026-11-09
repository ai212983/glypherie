"""Independent check against profiles from the full original process()/UFO run."""
from __future__ import print_function
import hashlib
import json
import math
import os
import sys
from autokern.Autokern import Autokern, TFSMap


def verify(request_path, profile_path, summary_path, output):
    if os.path.exists(output):
        raise ValueError('verification output must be new')
    q = json.load(open(request_path))
    c = json.load(open(profile_path))
    s = json.load(open(summary_path))
    if c['parameters'] != s['selected']['parameters']:
        raise ValueError('independent profiles have different parameters')
    m = Autokern(TFSMap())
    m.profileMinYunits = c['profile_min_y_units']
    m.precision, m.ascender, m.units_per_em = c['precision'], c['ascender'], c['units_per_em']
    unit = float(m.units_per_em)/q['size_px']
    normal = c['parameters']['max_distance_ems']*m.units_per_em
    tolerance = c['parameters']['intrusion_tolerance_ems']*m.units_per_em
    cap = c['parameters']['max_x_extrema_overlap_ems']*m.units_per_em
    checks = 0
    for p in s['selected']['pairs']:
        a, b = [c['profiles'][v] for v in p['pair']]
        minimum = m.findMinProfileAdvance(a['minimum'][1], b['minimum'][0])
        maximum = m.findMinProfileAdvance(a['maximum'][1], b['maximum'][0])
        if minimum is None or maximum is None:
            raise ValueError('the fixed lowercase domain must share profile rows')
        max_a = max(v for v in a['raw'][1] if v is not None)
        min_b = min(v for v in b['raw'][0] if v is not None)
        bound = max_a-min_b-cap
        assert p['first'] == q['bitmap_minimums'][p['pair']]
        assert p['last'] == int(math.ceil(max(minimum,maximum,bound,p['first']*unit)/unit))
        assert [t['step'] for t in p['tested']] == range(p['first'],p['last']+1)
        accepted = []
        for t in p['tested']:
            advance = t['step']*unit
            min_ok, cap_ok = advance >= minimum, advance >= bound
            full = asc = False
            if min_ok and cap_ok:
                full = m.isValidProfileIntrusion(a['maximum'][1],b['maximum'][0],
                    (a['raw'][1],b['raw'][0]),advance,normal,tolerance)
                asc = m.isValidProfileIntrusion(a['maximum'][1],b['maximum'][0],
                    (a['raw'][1],b['raw'][0]),advance,normal,tolerance,withinAscender=True)
            checks += 1
            assert (min_ok,cap_ok,full,asc) == (t['minimum_ok'],t['extrema_ok'],t['full'],t['ascender'])
            if min_ok and cap_ok and full and asc:
                accepted.append(t['step'])
        assert accepted and min(accepted) == p['step_px']
    result = dict(status='passed',chosen_valid_pairs=len(s['selected']['pairs']),postsolve_shift=0,
        full_original_profiles=True,original_predicate_positions=checks,all_smaller_positions_rejected=True,
        summary_sha256=hashlib.sha256(open(summary_path,'rb').read()).hexdigest(),
        profiles_sha256=hashlib.sha256(open(profile_path,'rb').read()).hexdigest())
    with open(output,'w') as f:
        json.dump(result,f,indent=2,sort_keys=True)
    print(json.dumps(result))


if __name__ == '__main__':
    verify(*sys.argv[1:])
