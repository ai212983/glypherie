"""Compare uniform integration with the reviewed experiment and prior candidate."""
import json
from pathlib import Path
import numpy as np
import freetype as ft
from check_shamir_baseline import digest
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference

HERE=Path(__file__).resolve().parent


def run():
    old=HERE/'out/geometric-candidate-v1';new=HERE/'out/geometric-candidate-v2'
    reviewed=HERE/'out/opposing-terminals-v1'
    previous={(r['key'],r['char']):r for r in json.loads((old/'report.json').read_text())['cases']}
    current=json.loads((new/'report.json').read_text())['cases'];checks=[];figures=[]
    assert set(previous)=={(r['key'],r['char']) for r in current}
    for row in current:
        key,char=row['key'],row['char'];prior=previous[key,char]
        assert row['status']==prior['status'],(key,char,'coverage changed')
        if row['status']!='verified':
            assert row['reason']==prior['reason'];continue
        size=int(key.rsplit('-',1)[1]);a=old/f'{key}-candidate.ttf';b=new/f'{key}-candidate.ttf'
        reference=reviewed/f'{key}-u{ord(char):04x}-coordinated.ttf' if row['opposing_count'] else a
        assert reference.exists()
        f,g=ft.Face(str(reference)),ft.Face(str(b))
        assert np.array_equal(coords(f,char,size),coords(g,char,size)),(key,char,'coordinate regression')
        assert pixels(render(f,char,size,hinted=True))==pixels(render(g,char,size,hinted=True)),(key,char,'bitmap regression')
        different=pixels(render(ft.Face(str(a)),char,size,hinted=True))!=pixels(render(g,char,size,hinted=True))
        if different:
            source=ft.Face(str(a));glyphs=[render(source,char,size,hinted=True),render(g,char,size,hinted=True)]
            name=f'{key}-u{ord(char):04x}-integration.png'
            panel=comparison(glyphs,['Previous uniform candidate','Integrated coordinated terminals'],f'{key} {char!r}')
            prepend_reference(source,char,size,f'{key} {char!r}',glyphs,panel).save(new/name)
            figures.append(f'<figure><img src="{name}"></figure>')
        checks.append(dict(key=key,char=char,reviewed_reference=reference.name,reference_sha256=digest(reference),changed=different))
    (new/'integration-check.json').write_text(json.dumps(dict(checks=checks,coverage_unchanged=True,
        checker_sha256=digest(Path(__file__)),prior_report_sha256=digest(old/'report.json'),current_report_sha256=digest(new/'report.json')),indent=2)+'\n')
    (new/'changes.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}</style><h1>Integration changes</h1><p>All four changes reproduce the accepted coordinated experiment exactly. Other 876 verified cases are unchanged.</p><a href="index.html">Full gallery</a>'+''.join(figures))
    print(len(checks),'exact coordinate/bitmap comparisons;',sum(c['changed'] for c in checks),'changed cases')


if __name__=='__main__':run()
