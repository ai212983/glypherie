"""Uniform candidate adapter: all requested outlines run the same correction path."""
import argparse,html,json,shutil
from array import array
from pathlib import Path
import freetype as ft
import numpy as np
from fontTools import subset
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables.ttProgram import Program
from geometric_candidate import Geometry,correct,finish,STAGES
from shamir_reorientation import Unsupported
from check_shamir_baseline import digest
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from audit_terminal_coverage import coords

HERE=Path(__file__).resolve().parent
REPERTOIRE=tuple(range(33,127))+(176,)


def geometry(record, points, ends, flags, size, em):
    return Geometry(tuple(map(tuple,points)),tuple(ends),tuple(flags),size,em,
                    tuple(record['graph']['constraints']),
                    tuple(a['constraint'] for a in record['attachment_resolution']))


def run(output=None):
    reference=HERE/'out/shamir-representative-comparison'
    output=output or HERE/'out/geometric-candidate-v2';output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('output must be empty')
    (output/'sources').mkdir();sources={p.name:digest(p) for p in HERE.glob('*.py')}
    for name in sources:shutil.copy2(HERE/name,output/'sources'/name)
    rows=[];inputs={};pages=[];focus=[]
    for model_path in sorted(reference.glob('*-model.json')):
        key=model_path.name.removesuffix('-model.json');size=int(key.rsplit('-',1)[1])
        path=reference/f'{key}-experiment.ttf';model=json.loads(model_path.read_text())
        for source in (path,model_path):
            inputs[source.name]=digest(source);shutil.copy2(source,output/source.name)
        font=TTFont(path);cmap=font.getBestCmap();em=font['head'].unitsPerEm
        if 'cvt ' not in font:font['cvt ']=newTable('cvt ');font['cvt '].values=array('h')
        built=[];figures=[]
        for code in REPERTOIRE:
            char=chr(code);row=dict(key=key,char=char,codepoint=code)
            if code not in cmap or char not in model['records']:
                row.update(status='unsupported',reason='missing outline or frozen constraint record')
                rows.append(row);continue
            g=font['glyf'][cmap[code]];points,ends,flags=g.getCoordinates(font['glyf'])
            data=geometry(model['records'][char],points,ends,flags,size,em)
            try:
                result=correct(data)
                assembly,cvts,expected=finish(result,data,len(font['cvt '].values))
            except np.linalg.LinAlgError as exc:
                row.update(status='failed',reason=f'numerical diagnostic failure: {exc}');rows.append(row);continue
            except (Unsupported,ValueError) as exc:
                row.update(status='unsupported',reason=str(exc));rows.append(row);continue
            font['cvt '].values.extend(cvts);g.program=Program();g.program.fromAssembly(assembly)
            row.update(status='verified',stages=result['stages'],parent_changes=result['parent_changes'],
                       serif_count=len(result['serif_audit']),terminal_count=len(result['terminal']),
                       opposing_count=len(result['opposing']),opposing_audit=result['opposing_audit'])
            built.append((row,result,expected));rows.append(row)
        # The candidate exports only verified mappings, never inherited failed cases.
        keep={row['codepoint'] for row,_,_ in built}
        # These are single-outline review fonts; inherited substitutions could
        # select an unprocessed alternate outside the verified repertoire.
        for tag in ('GSUB','morx','mort'):
            if tag in font:del font[tag]
        options=subset.Options();options.recalc_max_context=False
        sub=subset.Subsetter(options=options);sub.populate(unicodes=keep);sub.subset(font)
        # Layout closure may retain additional aliases; trim every encoded map.
        for table in font['cmap'].tables:
            if hasattr(table,'cmap'):
                table.cmap={code:name for code,name in table.cmap.items() if code in keep}
        font['maxp'].maxSizeOfInstructions=max((len(g.program.getBytecode()) if hasattr(g,'program') else 0) for g in (font['glyf'][n] for n in font.getGlyphOrder()))
        font['maxp'].maxStackElements=max(font['maxp'].maxStackElements,16)
        target=output/f'{key}-candidate.ttf';font.save(target);font.close()
        with TTFont(target) as exported:
            assert set(exported.getBestCmap())==keep
            assert not any(tag in exported for tag in ('GSUB','morx','mort'))
        old=ft.Face(str(path));new=ft.Face(str(target))
        for row,result,expected in built:
            char=row['char'];actual=coords(new,char,size);error=float(np.max(abs(actual-expected)))
            if error>1/64+1e-7:raise AssertionError((key,char,error))
            row['native_error_px']=error
            if result['terminal']:
                r,=result['terminal'];before=np.round(np.array(result['preterminal'])*64)/64
                touched={r['top'],r['bottom'],*r['upper'],*r['lower'],*r['tip']}
                assert np.array_equal(actual[:,0],before[:,0])
                assert all(np.array_equal(actual[i],before[i]) for i in range(len(before)) if i not in touched)
                assert actual[r['top'],1]-actual[r['upper_arm'],1]==actual[r['lower_arm'],1]-actual[r['bottom'],1]
            glyphs=[render(f,char,size,hinted=True) for f in (old,new)]
            row['changed_pixels']=len(pixels(glyphs[0])^pixels(glyphs[1]))
            name=f'{key}-u{ord(char):04x}.png'
            panel=comparison(glyphs,['Uniform input','Uniform geometric candidate'],f'{key} {char!r}')
            prepend_reference(old,char,size,f'{key} {char!r}',glyphs,panel).save(output/name)
            figure=f'<figure id="{key}-u{ord(char):04x}"><img loading="lazy" src="{name}" alt="{html.escape(char,quote=True)}"></figure>'
            figures.append(figure)
            if result['terminal']:focus.append(figure)
        excluded=[r for r in rows if r['key']==key and r['status']!='verified']
        failures=''.join(f'<li>{html.escape(r["char"])}: {html.escape(r["reason"])}</li>' for r in excluded)
        (output/f'{key}.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}</style><a href="index.html">Index</a><h1>'+key+'</h1><p>Every candidate uses the same stages. Unsupported cases have no candidate mapping.</p><ul>'+failures+'</ul>'+''.join(figures))
        pages.append(f'<li><a href="{key}.html">{key}</a>: {len(built)} verified, {len(excluded)} unsupported</li>')
        print(key,len(built),'verified',len(excluded),'unsupported',flush=True)
    assert sources=={name:digest(HERE/name) for name in sources}
    assert inputs=={name:digest(reference/name) for name in inputs}
    (output/'report.json').write_text(json.dumps(dict(stages=STAGES,sources=sources,inputs=inputs,cases=rows),indent=2)+'\n')
    (output/'matches.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}</style><a href="index.html">Full coverage</a><h1>Terminal matches after uniform corrections</h1>'+''.join(focus))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>Uniform geometric candidate</h1><p>Unpromoted experimental pipeline. Reorientation, parent placement, serif recognition and paired terminals run for every available constraint record. Unsupported cases are excluded from candidate fonts, with reasons.</p><a href="matches.html">Terminal matches</a><ul>'+''.join(pages)+'</ul>')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    run(parser.parse_args().output)
