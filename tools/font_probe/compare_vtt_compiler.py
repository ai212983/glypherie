"""Execute Microsoft VTT compiler + control program for flagged diagonal cases."""
import json,html,shutil
from importlib.metadata import version
from pathlib import Path
import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
import vttcompilepy as vtt
from vtt_mapping import commands
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from audit_terminal_coverage import coords
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent
REV='1bd4ed4383f8390b0140e05d330491fcadd3e8e0'


def prepare(path):
    c=vtt.Compiler(TTFont(path));c.import_source_from_binary();f=c.get_ttfont()
    for tag in ('TSI1','TSI3'):f[tag].glyphPrograms={};f[tag].extraPrograms={}
    f['TSI1'].extraPrograms={key:(HERE/'vtt_reference'/name).read_text(encoding='utf-16') for key,name in [('fpgm','fpgmtmpl.txt'),('ppgm','preptmpl.txt'),('cvt','cvttmpl.txt')]}
    f['maxp'].maxTwilightPoints=16;f['maxp'].maxStorage=1024;f['maxp'].maxFunctionDefs=256;f['maxp'].maxStackElements=1024
    for tag in ('GSUB','morx','mort'):
        if tag in f:del f[tag]
    return f


def run():
    out=HERE/'out/vtt-compiler-v1';out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    audit=HERE/'out/diagonal-instability-v1/report.json';data=json.loads(audit.read_text());rows=[];sections=[];inputs={str(audit.relative_to(HERE)):digest(audit)}
    for name in ('vtt_mapping.py','compare_vtt_compiler.py'):shutil.copy2(HERE/name,out/name)
    for row in data['cases']:
        if not row['audit']:continue
        key=row['key'];char=row['char'];size=int(key.rsplit('-',1)[1]);stem=f'{key}-u{ord(char):04x}'
        root=HERE/'out/shamir-representative-comparison';path=root/f'{key}-experiment.ttf';mp=root/f'{key}-model.json'
        for p in (path,mp):inputs[str(p.relative_to(HERE))]=digest(p)
        f=prepare(path);name=f.getBestCmap()[ord(char)];p,e,t=f['glyf'][name].getCoordinates(f['glyf']);record=json.loads(mp.read_text())['records'][char]
        talk,cvts,mapping=commands(p,t,record);entry=dict(key=key,char=char,mapping=mapping);rows.append(entry)
        (out/f'{stem}.vtt').write_text(talk)
        if not mapping['strokes']:entry.update(status='held',reason='no paired strokes mapped');continue
        f['TSI3'].glyphPrograms[name]=talk
        f['TSI1'].extraPrograms['cvt']+='\n'+'\n'.join(f'{1000+i}: {value}' for i,value in enumerate(cvts))+'\n'
        try:
            c=vtt.Compiler(f);c.compile_all();target=out/f'{stem}.ttf';c.save_font(target)
            new=ft.Face(str(target));actual=coords(new,char,size);assert np.isfinite(actual).all()
            with TTFont(target) as compiled:
                cp,ce,ct=compiled['glyf'][name].getCoordinates(compiled['glyf'])
                assert list(cp)==list(p) and list(ce)==list(e) and list(ct)==list(t)
                assembly=compiled['TSI1'].glyphPrograms[name]
                (out/f'{stem}.asm').write_text(assembly)
                assert 'CALL' in assembly
            # Fresh compiler invocation must emit identical executable glyph bytes.
            d=vtt.Compiler(f);d.compile_all();again=d.get_ttfont()
            with TTFont(target) as compiled:
                assert compiled['glyf'][name].program.getBytecode()==again['glyf'][name].program.getBytecode()
            old=ft.Face(str(path))
            uniform_path=HERE/'out/geometric-candidate-v3'/f'{key}-candidate.ttf'
            inputs[str(uniform_path.relative_to(HERE))]=digest(uniform_path)
            glyphs=[render(ft.Face(str(uniform_path)),char,size,hinted=True),render(old,char,size,hinted=True),render(new,char,size,hinted=True)]
            entry.update(status='compiled',max_source_movement_px=float(np.max(np.linalg.norm(actual-np.array(p)*size/f['head'].unitsPerEm,axis=1))),changed_pixels=len(pixels(glyphs[1])^pixels(glyphs[2])))
            np.save(out/f'{stem}-points.npy',actual)
            labels=['Current uniform candidate','Frozen Shamir model','Microsoft VTT execution']
            prior=HERE/'out/diagonal-instability-v1'/f'{stem}-points.npy'
            entry['cardinal_comparison_available']=prior.exists()
            if prior.exists():
                inputs[str(prior.relative_to(HERE))]=digest(prior)
                glyphs.insert(2,render(old,char,size,points=np.load(prior),hinted=True))
                labels.insert(2,'Prior cardinal experiment')
            panel=comparison(glyphs,labels,f'{key} {char!r}')
            prepend_reference(old,char,size,f'{key} {char!r}',glyphs,panel).save(out/f'{stem}.png')
            sections.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p><a href="{stem}.vtt">VTT commands</a> | <a href="{stem}.asm">Compiled instructions</a></p></section>')
        except (vtt.CompileError,ft.FT_Exception) as exc:
            entry.update(status='held',reason=str(exc))
            if (out/f'{stem}.ttf').exists():(out/f'{stem}.ttf').unlink()
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    (out/'report.json').write_text(json.dumps(dict(compiler_revision=REV,compiler_package_version=version("vttcompilepy"),freetype_version=ft.version(),inputs=inputs,sources={n:digest(HERE/n) for n in ('vtt_mapping.py','compare_vtt_compiler.py')},templates={p.name:digest(p) for p in (HERE/'vtt_reference').glob('*.txt')},cases=rows),indent=2)+'\n')
    held=''.join(f'<li>{r["key"]} {html.escape(r["char"])}: {html.escape(r["reason"])}</li>' for r in rows if r['status']=='held')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Microsoft VTT compiler comparison</h1><p>Actual Microsoft compiler and control program, executed by FreeType. Source, current uniform candidate, frozen Shamir model, prior cardinal experiment where available, VTT result. Supported ResXDLink/ResYDLink commands execute paired endpoints through Microsoft functions 118–120. Legacy Diagonal is unavailable with the current template. Automatic feature-to-command mapping remains experimental. This is a diagonal-focused program, not a complete font hinter. All 38 conditioning-flagged cases are attempted.</p><h2>Held cases</h2><ul>'+held+'</ul>'+''.join(sections))
    from collections import Counter
    print(Counter(r['status'] for r in rows))

if __name__=='__main__':run()
