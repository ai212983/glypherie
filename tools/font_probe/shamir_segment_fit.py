"""Prepared-segment Shamir experiment, with native TrueType constraints.

Project policies: nearest non-overlapping side pair, recurring clusters within
0.01em with three distinct glyph votes, contour-bracket Ratio interpolation. Prepared coordinates round to font units.
Serif automata, counter ladders and compound-junction templates remain open.
"""
from array import array
from collections import Counter
import numpy as np
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph,GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from shamir_geometry import from_font,unit
from shamir_features import recognize
from shamir_prototype import push,select_constraints


def selected_features(model):
    found=recognize(model);accepted=[];used=set()
    # Resolve alternate partners before statistics: one relation per side.
    for f in sorted(found['features'],key=lambda f:(f['width'],f['id'])):
        if f['width']>.18*model['em']:continue
        keys=[('s',i) for i in f.get('sides',[])]+[('p',i,f.get('axis')) for i in f.get('points',[])]
        if any(k in used for k in keys):continue
        used.update(keys);accepted.append(f)
    return found,accepted


def prepared_glyph(model):
    coords=[];flags=[];ends=[];mapping={};members={}
    for loop in model['contours']:
        for sid in loop:
            s=model['segments'][sid];mapping[s['start']]=len(coords)
            ids=[]
            for j,p in enumerate(s['control'][:-1]):
                ids.append(len(coords));coords.append(p);flags.append(1 if j==0 else 0)
            members[sid]=ids
        ends.append(len(coords)-1)
    g=Glyph();g.numberOfContours=len(ends);g.coordinates=GlyphCoordinates(np.rint(coords).astype(int).tolist())
    g.flags=array('B',flags);g.endPtsOfContours=ends;g.program=Program();g.program.fromAssembly([])
    for sid in members:members[sid].append(mapping[model['segments'][sid]['end']])
    return g,mapping,members


def clusters(samples,em,baseline=False):
    if baseline:
        # §3.4 counts feature occurrences, retaining distinct frequent values
        # (Table II includes adjacent heights 36 and 37). Six occurrences is a
        # conservative setting drawn from that example, not a universal rule.
        # Quantization matches the integer font-unit representation of the CVT.
        result={}
        for kind in sorted({s[0] for s in samples}):
            counts=Counter(round(value) for category,value,char in samples if category==kind)
            result[kind]=[float(value) for value,count in sorted(counts.items()) if count>=6]
        return result
    result={}
    for kind in sorted({s[0] for s in samples}):
        groups=[]
        for _,value,char in sorted((s for s in samples if s[0]==kind),key=lambda s:s[1]):
            if groups and abs(value-np.mean([v for v,c in groups[-1]]))<=.01*em:groups[-1].append((value,char))
            else:groups.append([(value,char)])
        result[kind]=[float(np.median([v for v,c in g])) for g in groups if len({c for v,c in g})>=3]
    return result


def anchor_curved_strokes(constraints, strokes):
    """Keep an outer height anchor and derive its paired inner edge by width.

    A pair of maxima has the outer edge at the larger coordinate; a pair of
    minima has it at the smaller coordinate. Only recognized curved pairs with
    an existing outer anchor participate. Tangent links retain their dependency
    on the inner representative, so they follow the preserved stroke width.
    """
    constraints=[dict(c) for c in constraints];changes=[]
    anchors={c['point'] for c in constraints if c['kind']=='PAbs'}
    for feature,outer,inner in strokes:
        if outer not in anchors:continue
        relation=next((c for c in constraints if c.get('feature')==feature and
                       c['kind'] in ('PDist','Dist') and c.get('round',True) and
                       {c['point'],c.get('source')}=={outer,inner}),None)
        if relation is None:continue
        relation.update(point=inner,source=outer)
        # A flat tangent can have several representatives at the same height.
        # Re-root the whole linked side; an alternate anchor must not pull its
        # controls back to the discarded independently rounded height.
        group={inner}
        links=[c for c in constraints if c['kind']=='Dist' and not c.get('round',True)]
        while True:
            expanded=group|{p for c in links if c['point'] in group or c.get('source') in group
                            for p in (c['point'],c['source'])}
            if expanded==group:break
            group=expanded
        if outer in group:raise ValueError('opposite curve sides share alignment group')
        removed=[c for c in constraints if
                 (c['kind'] in ('Abs','PAbs') and c['point'] in group) or
                 (c in links and c['point'] in group)]
        constraints=[c for c in constraints if c not in removed]
        constraints.extend(dict(kind='Dist',point=p,source=inner,value=None,priority=35,round=False)
                           for p in sorted(group-{inner}))
        changes.append(dict(feature=feature,outer=outer,inner=inner,inner_group=sorted(group),removed=removed))
    return constraints,changes


def build_font(source,output,chars):
    font=TTFont(source,recalcTimestamp=False)
    if 'glyf' not in font or 'fvar' in font:raise ValueError('instantiated static quadratic font required')
    em=font['head'].unitsPerEm;cmap=font.getBestCmap();glyf=font['glyf']
    models={};samples=[]
    for char in dict.fromkeys(chars):
        m=from_font(font,char);found,features=selected_features(m);models[char]=(m,found,features)
        samples.extend((f['kind'],f['width'],char) for f in features)
        for p in m['points']:
            if '1' in p['extrema']:
                kind='height-'+('round' if p['kind']=='curve' else 'flat')+'-'+p['extrema']['1']
                samples.append((kind,p['position'][1],char))
    tables=clusters(samples,em);cvt=[];records={}
    def cvt_id(v):
        v=round(v)
        if v not in cvt:cvt.append(v)
        return cvt.index(v)
    for tag in ('fpgm','prep','cvt ','hdmx','LTSH','VDMX','gasp'):
        if tag in font:del font[tag]
    for name in font.getGlyphOrder():
        g=glyf[name];g.program=Program();g.program.fromAssembly([])
    for char,(m,found,features) in models.items():
        g,mapping,members=prepared_glyph(m);glyf[cmap[ord(char)]]=g
        points=np.asarray(g.coordinates,dtype=float).reshape(-1,2)
        assembly=['RTG[ ]']+push(6400)+['SCVTCI[ ]'];touched=[set(),set()];axes=[[],[]];diagonals=[];curved_strokes=[]
        def near(kind,value):
            values=[v for v in tables.get(kind,[]) if abs(v-value)<=.01*em]
            return min(values,key=lambda v:abs(v-value)) if values else None
        for f in features:
            groups=[]
            for pid in f.get('points',[]):
                rep=mapping[pid];axis=f['axis'];group=[rep]
                for seg in m['segments']:
                    if pid in (seg['start'],seg['end']):
                        group.extend(i for i in members[seg['id']] if abs(points[i,axis]-points[rep,axis])<=1)
                groups.append(sorted(set(group)))
            for sid in f.get('sides',[]):
                side=found['sides'][sid];groups.append(sorted(set(i for s in side['segments'] for i in members[s])))
            if len(groups)!=2:continue
            n=unit(np.asarray(f['b'])-f['a'])
            if f['kind']=='slant':
                side=found['sides'][f['sides'][0]];d=np.asarray(side['direction']);n=np.array([-d[1],d[0]])
            else:
                axis=f.get('axis',0 if f['kind']=='stem' else 1);n=np.eye(2)[axis]
            # Representative nearest the middle of the measured support.
            reps=[min(ids,key=lambda i:np.linalg.norm(points[i]-np.asarray(pos))) for ids,pos in zip(groups,(f['a'],f['b']))]
            if (points[reps[1]]-points[reps[0]])@n<0:groups.reverse();reps.reverse()
            width=float((points[reps[1]]-points[reps[0]])@n);shared=near(f['kind'],width)
            relation=dict(kind='PDist' if shared is not None else 'Dist',point=reps[1],source=reps[0],value=shared,priority=30 if shared is not None else 25,feature=f['id'])
            if f['kind']=='slant':diagonals.append((n,groups,reps,relation));continue
            if f['kind']=='arc':
                extremum=m['points'][f['points'][0]]['extrema']['1']
                outer,inner=(reps[1],reps[0]) if extremum=='max' else (reps[0],reps[1])
                curved_strokes.append((f['id'],outer,inner))
            axes[axis].extend([dict(kind='Abs',point=reps[0],priority=10),relation])
            for ids,rep in zip(groups,reps):
                for p in ids:
                    if p!=rep:axes[axis].append(dict(kind='Dist',point=p,source=rep,value=None,priority=20,feature=f['id'],round=False))
        for p in m['points']:
            if '1' not in p['extrema']:continue
            value=near('height-'+('round' if p['kind']=='curve' else 'flat')+'-'+p['extrema']['1'],p['position'][1])
            if value is not None:
                rep=mapping[p['id']];axes[1].append(dict(kind='PAbs',point=rep,value=value,priority=40))
                for seg in m['segments']:
                    if p['id'] in (seg['start'],seg['end']):
                        for i in members[seg['id']]:
                            if i!=rep and abs(points[i,1]-points[rep,1])<=1:
                                axes[1].append(dict(kind='Dist',point=i,source=rep,value=None,priority=35,round=False))
        axes[1],anchor_changes=anchor_curved_strokes(axes[1],curved_strokes)
        diagnostics=[]
        for axis in (0,1):
            ordered,rejected=select_constraints(axes[axis]);diagnostics.append(dict(axis=axis,selected=ordered,rejected=rejected))
            assembly.append(f'SVTCA[{1-axis}]')
            for c in ordered:
                p=c['point'];kind=c['kind']
                if kind=='Abs':assembly+=push(p)+['MDAP[1]']
                elif kind=='PAbs':assembly+=push(p,cvt_id(c['value']))+['MIAP[1]']
                else:
                    s=c['source']
                    if s not in touched[axis]:assembly+=push(s)+['MDAP[1]'];touched[axis].add(s)
                    assembly+=push(s)+['SRP0[ ]']
                    if kind=='PDist':assembly+=push(p,cvt_id(c['value']))+['MIRP[01100]']
                    else:assembly+=push(p)+['MDRP[00100]' if c.get('round',True) else 'MDRP[00000]']
                touched[axis].add(p)
        # Projected distances use their actual normal; preserve tangential position.
        # Preserve existing height/width ownership through the freedom vector.
        applied=0
        for n,groups,reps,c in diagonals:
            ids=set(groups[0]+groups[1])
            owned=[bool(ids&t) for t in touched]
            if all(owned):continue
            freedom=0 if owned[1] else 1 if owned[0] else None
            if freedom is not None and abs(n[freedom])<.2:continue
            vector=np.rint(n*16384).astype(int)
            assembly+=push(*vector)+['SPVFS[ ]']
            assembly+=['SFVTPV[ ]' if freedom is None else f'SFVTCA[{1-freedom}]']
            assembly+=push(reps[0])+['MDAP[1]']
            assembly+=push(reps[0])+['SRP0[ ]']
            if c['kind']=='PDist':assembly+=push(reps[1],cvt_id(c['value']))+['MIRP[01100]']
            else:assembly+=push(reps[1])+['MDRP[00100]']
            for group,rep in zip(groups,reps):
                assembly+=push(rep)+['SRP0[ ]']
                for p in group:
                    if p!=rep:assembly+=push(p)+['MDRP[00000]']
            for axis,t in enumerate(touched):
                if freedom is None or axis==freedom:t.update(ids)
            applied+=1
        # Explicit Ratio constraints: bracket each free coordinate by key points.
        ratios=0
        for axis in (0,1):
            assembly.append(f'SVTCA[{1-axis}]')
            start=0
            for end in g.endPtsOfContours:
                ids=list(range(start,end+1));start=end+1
                refs=[r for r in ids if r in touched[axis]]
                if not refs:continue
                for p in ids:
                    if p in touched[axis]:continue
                    a=next((r for r in reversed(refs) if r<p),refs[-1])
                    b=next((r for r in refs if r>p),refs[0])
                    if points[a,axis]>points[b,axis]:a,b=b,a
                    if points[p,axis]<=points[a,axis]:b=a
                    elif points[p,axis]>=points[b,axis]:a=b
                    if points[a,axis]==points[b,axis]:assembly+=push(a)+['SRP0[ ]']+push(p)+['MDRP[00000]']
                    else:assembly+=push(a)+['SRP1[ ]']+push(b)+['SRP2[ ]']+push(p)+['IP[ ]'];ratios+=1
        g.program.fromAssembly(assembly)
        records[char]=dict(features=features,candidate_count=len(found['features']),constraints=diagnostics,stroke_anchor_changes=anchor_changes,diagonals_applied=applied,ratios=ratios,composite_decomposed=m['composite'])
    font['cvt ']=newTable('cvt ');font['cvt '].values=array('h',cvt)
    maxp=font['maxp'];maxp.maxZones=2;maxp.maxTwilightPoints=0;maxp.maxStorage=0
    maxp.maxFunctionDefs=0;maxp.maxInstructionDefs=0;maxp.maxStackElements=8
    maxp.maxSizeOfInstructions=max(len(glyf[n].program.getBytecode()) for n in font.getGlyphOrder())
    font.save(output)
    return dict(records=records,clusters=tables,cvt=cvt,limitations=__doc__)
