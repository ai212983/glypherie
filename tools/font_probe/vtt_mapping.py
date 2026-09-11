"""Geometry/constraint-to-VTT mapping experiment, separate from the VTT compiler."""
import numpy as np
from vtt_dependencies import schedule
from vtt_stem_widths import inherit_widths


def commands(points, flags, record, *, shared_dependencies=False, stem_widths=False):
    p=np.asarray(points,float);constraints=record['graph']['constraints']
    links=constraints+[a['constraint'] for a in record['attachment_resolution']]
    strokes=[];cvts=[];warnings=[]
    for index,f in enumerate(record['features']):
        if f['kind']!='slant':continue
        sides=[];members=[]
        for g,rep in zip(f['groups'],f['points']):
            ids={rep}
            for c in links:
                if c.get('feature')==f'align-{g}':ids.update([c['point'],*c['sources']])
            ids=sorted(i for i in ids if flags[i]&1)
            if len(ids)<2:break
            # Choose the farthest on-curve pair, then orient both sides alike.
            a,b=max(((a,b) for a in ids for b in ids if a!=b),key=lambda pair:np.linalg.norm(p[pair[1]]-p[pair[0]]))
            if tuple(p[a][::-1])>tuple(p[b][::-1]):a,b=b,a
            sides.append((a,b));members.append(ids)
        if len(sides)!=2:
            warnings.append(dict(feature=index,reason='missing two on-curve endpoints'));continue
        (a,b),(c,d)=sides
        u=p[b]-p[a];v=p[d]-p[c]
        if min(np.linalg.norm(u),np.linalg.norm(v))==0:
            warnings.append(dict(feature=index,reason='zero-length side'));continue
        u/=np.linalg.norm(u);v/=np.linalg.norm(v)
        if u@v<0:c,d=d,c;v=-v
        direction=u+v;direction/=np.linalg.norm(direction)
        axis=0 if abs(direction[0])<=abs(direction[1]) else 1
        # ResDLink uses perpendicular widths, one for each side (fpgm 118).
        widths=[abs(float(np.linalg.det(np.array([v,p[c]-p[a]])))),
                abs(float(np.linalg.det(np.array([u,p[b]-p[d]]))))]
        values=[int(np.floor(w+.5)) for w in widths]
        if min(values)<=0:warnings.append(dict(feature=index,reason='zero perpendicular width'));continue
        strokes.append(dict(feature=index,endpoints=[a,c,b,d],sides=[[a,b],[c,d]],members=members,cvts=values,axis=axis,length=f['length']))
    # Long supports precede short terminal supports. This is our mapping policy.
    strokes.sort(key=lambda s:(-s['length'],s['feature']))
    width_audit=inherit_widths(strokes,record["features"],links) if stem_widths else []
    dependency_audit = None
    if shared_dependencies:
        operations=[]
        for s in strokes:
            a,c,b,d=s['endpoints']
            reads={(i,axis) for i in (a,b,c,d) for axis in (0,1)}
            writes={(i,s['axis']) for i in (b,c)}
            for (x,y),members in zip(s['sides'],s['members']):
                direction=p[y]-p[x];length=float(np.linalg.norm(direction))
                for i in members:
                    t=float((p[i]-p[x])@direction/(length*length))
                    distance=abs(float(np.linalg.det(np.array([direction,p[i]-p[x]]))))/length
                    if i not in (x,y) and flags[i]&1 and 0<t<1 and distance<1e-7:
                        reads.update((i,axis) for axis in (0,1))
                        writes.update((i,axis) for axis in (0,1))
            operations.append(dict(id=s['feature'],reads=reads,writes=writes))
        order,dependency_audit=schedule(operations)
        if order is None:
            return '',[],dict(strokes=strokes,warnings=warnings,dependencies=dependency_audit,width_inheritance=width_audit,status='held')
        strokes=[strokes[i] for i in order]
    lines=[];anchors=set()
    for c in constraints:
        n=np.array(c['normal']);nz=np.flatnonzero(abs(n)>1e-10)
        if len(nz)!=1 or c['kind'] not in ('Abs','PAbs'):continue
        axis=int(nz[0]);point=c['point'];key=(axis,point)
        if key in anchors:continue
        if c.get('default'):continue
        lines.append(f'{"X" if axis==0 else "Y"}Anchor({point})');anchors.add(key)
    if shared_dependencies:
        # Initialize all parent anchors before any operation consumes their positions.
        for s in strokes:
            a,c,b,d=s['endpoints']
            for parent in (a,d):
                for axis in (0,1):
                    if (axis,parent) not in anchors:
                        lines.append(f'{"X" if axis==0 else "Y"}Anchor({parent})');anchors.add((axis,parent))
    for s in strokes:
        a,c,b,d=s['endpoints'];ci=1000+len(cvts)
        cvts.extend(s['cvts'][:1] if s.get('shared_cvt') else s['cvts'])
        ci_end=ci if s.get('shared_cvt') else ci+1
        # Opposite parents make VTT's crossed projection lines follow both sides.
        # Grid anchoring of these parents is an explicit experiment policy.
        for parent in (a,d):
            for axis in (0,1):
                if (axis,parent) not in anchors:
                    lines.append(f'{"X" if axis==0 else "Y"}Anchor({parent})');anchors.add((axis,parent))
        lines.append(f'Res{"X" if s["axis"]==0 else "Y"}DLink({a},{c},{ci},{d},{b},{ci_end})')
        # Exact interior alignments are emitted after each paired link.
        for (x,y),member_ids in zip(s['sides'],s['members']):
            # Align only genuine source-collinear on-curve interiors on this side.
            direction=p[y]-p[x];length=float(np.linalg.norm(direction))
            children=[]
            for i in member_ids:
                if i in (x,y) or not flags[i]&1:continue
                t=float((p[i]-p[x])@direction/(length*length))
                distance=abs(float(np.linalg.det(np.array([direction,p[i]-p[x]]))))/length
                if 0<t<1 and distance<1e-7:children.append(i)
            if children:lines.append('Align('+','.join(map(str,[x,*children,y]))+')')
    lines.extend(['Smooth()'])
    return '\n'.join(lines)+'\n',cvts,dict(strokes=strokes,warnings=warnings,dependencies=dependency_audit,width_inheritance=width_audit,status='scheduled')
