"""Feature representatives and the combined Shamir 2003 constraint model.

Numeric tolerances, metric rounding and interpolation-reference selection are
explicit project policies. Input extraction coverage is reported separately.
"""
from array import array
from itertools import combinations
import numpy as np
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables.ttProgram import Program
from shamir_geometry import from_font,unit
from shamir_features import recognize,Interior,side_is_cardinal
from shamir_segment_fit import prepared_glyph,clusters
from shamir_constraints import relation,resolve,compile_graph


def feature_model(model,baseline=False):
    glyph,mapping,members=prepared_glyph(model);points=np.asarray(glyph.coordinates,float).reshape(-1,2)
    parallel_dot=1-1e-12 if baseline else .999
    found=recognize(model);groups=[];features=[];eps=model['tolerances']['distance']
    def group(ids,normal,side_id=None):
        normal=unit(np.asarray(normal,float))
        if normal[np.argmax(abs(normal))]<0:normal=-normal
        ids=set(ids)
        matching=[i for i,g in enumerate(groups) if
                  (side_id is not None and side_id in g.get('source_sides',[])) or
                  (abs(float(normal@np.asarray(g['normal'])))>parallel_dot and ids&g['members'])]
        if matching:
            i=matching[0];groups[i]['members'].update(ids)
            if side_id is not None:groups[i]['source_sides']=sorted(set(groups[i].get('source_sides',[]))|{side_id})
            return i
        groups.append(dict(normal=normal.tolist(),members=ids))
        if side_id is not None:groups[-1]['source_sides']=[side_id]
        return len(groups)-1
    for f in found['features']:
        if f['kind']=='slant':
            d=np.asarray(found['sides'][f['sides'][0]]['direction']);n=unit(np.array([-d[1],d[0]]))
        else:n=np.eye(2)[f.get('axis',0 if f['kind']=='stem' else 1)]
        ids=[]
        for pid in f.get('points',[]):
            rep=mapping[pid];support={rep}
            for seg in model['segments']:
                if pid in (seg['start'],seg['end']):support.update(i for i in members[seg['id']] if abs(float((points[i]-points[rep])@n))<=1)
            ids.append(group(support,n))
        for sid in f.get('sides',[]):
            side=found['sides'][sid];side_normal=n
            if baseline:
                # A segment has one representative and its own alignment
                # direction (§3.5–3.6), even when several features share it.
                # Feature width keeps the feature's separate projection below.
                d=np.asarray(side['direction']);side_normal=np.array([-d[1],d[0]])
            ids.append(group([i for s in side['segments'] for i in members[s]],
                             side_normal,sid if baseline else None))
        if len(ids)==2 and ids[0]!=ids[1]:
            support={key:f[key] for key in ('support_direction','support_intervals','length') if key in f}
            features.append(dict(kind=f['kind'],groups=ids,normal=n.tolist(),width=f['width'],**support))
    # Global heights come from horizontal segment support and recognized curved
    # features (§3.4). An isolated corner extremum still gets a local phantom
    # anchor (§3.5), but does not vote as a flat horizontal segment.
    horizontal_support=set()
    for side in found['sides']:
        if (side_is_cardinal(model,side,1) if baseline else abs(side['direction'][1])<=np.sin(model['tolerances']['angle_radians'])):
            horizontal_support.update(i for sid in side['segments'] for i in members[sid])
    curved_heights={pid for f in found['features'] if f['kind'] in ('arc','curve_bar')
                    for pid in f.get('points',[])}
    for p in model['points']:
        for axis in map(int,p['extrema']):
            rep=mapping[p['id']];n=np.eye(2)[axis];support={rep}
            for seg in model['segments']:
                if p['id'] in (seg['start'],seg['end']):support.update(i for i in members[seg['id']] if abs(points[i,axis]-points[rep,axis])<=1)
            i=group(support,n)
            if baseline and axis==1:groups[i]['height_lookup']='-'+p['extrema']['1']
            if axis==1 and (rep in horizontal_support or p['id'] in curved_heights):
                shape='flat' if rep in horizontal_support else 'round'
                groups[i]['height_kind']='height-'+shape+'-'+p['extrema']['1']
    # Merge transitively overlapping representations of the same physical side.
    changed=True
    while changed:
        changed=False
        for i,g in enumerate(groups):
            for j in range(i):
                h=groups[j]
                if g['members'] and h['members'] and g['members']&h['members'] and abs(np.dot(g['normal'],h['normal']))>parallel_dot:
                    h['members'].update(g['members']);g['members']=set()
                    if baseline and ('source_sides' in g or 'source_sides' in h):
                        h['source_sides']=sorted(set(h.get('source_sides',[]))|set(g.get('source_sides',[])))
                        g.pop('source_sides',None)
                    if 'height_kind' in g:h['height_kind']=g['height_kind']
                    if 'height_lookup' in g:h['height_lookup']=g['height_lookup']
                    for f in features:f['groups']=[j if k==i else k for k in f['groups']]
                    changed=True;break
    extrema={}
    if len(points):
        oncurve=list(mapping.values())
        for axis in (0,1):
            extrema[axis]=[min(oncurve,key=lambda p:points[p,axis]),max(oncurve,key=lambda p:points[p,axis])]
    metric_ids={p for pair in extrema.values() for p in pair}
    for g in groups:
        if g['members']:
            # Representatives are outline points. Bézier controls can follow a
            # side or tangent, but cannot become its geometric anchor (§3.3).
            eligible=g['members'].intersection(mapping.values())
            if not eligible:raise ValueError('feature group has no on-curve representative')
            g['rep']=min(eligible) if baseline else min(eligible,key=lambda p:(p not in metric_ids,p))
    features=[f for f in features if f['groups'][0]!=f['groups'][1]]
    # White distances use facing cardinal sides with a common support interval.
    interior=Interior(model)
    for axis in (0,1):
        aligned=[i for i,g in enumerate(groups) if g['members'] and abs(g['normal'][axis])>.999]
        aligned.sort(key=lambda i:points[groups[i]['rep'],axis])
        for a,b in combinations(aligned,2):
            ga,gb=groups[a],groups[b];pa=points[list(ga['members'])];pb=points[list(gb['members'])];other=1-axis
            lo=max(pa[:,other].min(),pb[:,other].min());hi=min(pa[:,other].max(),pb[:,other].max())
            width=float(points[gb['rep'],axis]-points[ga['rep'],axis])
            if hi-lo<=eps or width<=eps:continue
            white=True
            if baseline:
                vertices=[]
                for u,t in ((0,0),(1,0),(1,1),(0,1)):
                    point=np.zeros(2);point[axis]=points[ga['rep'],axis]+u*width;point[other]=lo+t*(hi-lo)
                    vertices.append(point)
                white=interior.region_inside(vertices,filled=False)
            else:
                for t in (.2,.5,.8):
                    for u in (.2,.5,.8):
                        p=np.zeros(2);p[axis]=points[ga['rep'],axis]+u*width;p[other]=lo+t*(hi-lo)
                        if interior.contains(p):white=False
            if white:features.append(dict(kind='counter-x' if axis==0 else 'counter-y',groups=[a,b],normal=np.eye(2)[axis].tolist(),width=width))
    for axis,kind in ((0,'stem'),(1,'bar')):
        strokes=[]
        for f in features:
            if f['kind']!=kind:continue
            a,b=sorted(f['groups'],key=lambda i:points[groups[i]['rep'],axis])
            # Measure the paired visible stroke, including only intervals where
            # both boundary sides exist. Group extents can include other features
            # or unsupported gaps after shared-side membership is merged.
            length=f['length']
            if baseline or length>=2*f['width']:strokes.append((a,b,f['width'],length))
        strokes.sort(key=lambda s:points[groups[s[0]]['rep'],axis])
        for i in range(len(strokes)-2):
            triple=strokes[i:i+3];widths=[s[2] for s in triple];lengths=[s[3] for s in triple]
            gaps=[points[groups[b[0]]['rep'],axis]-points[groups[a[1]]['rep'],axis] for a,b in zip(triple,triple[1:])]
            if min(gaps)<=eps or np.ptp(widths)>eps or np.ptp(lengths)>(eps if baseline else max(eps,.1*max(lengths))) or np.ptp(gaps)>eps:continue
            if not all(any(f['kind'].startswith('counter') and set(f['groups'])=={a[1],b[0]} for f in features) for a,b in zip(triple,triple[1:])):continue
            for a,b in zip(triple,triple[1:]):
                features.append(dict(kind='ladder-x' if axis==0 else 'ladder-y',groups=[a[0],b[0]],normal=np.eye(2)[axis].tolist(),width=float(points[groups[b[0]]['rep'],axis]-points[groups[a[0]]['rep'],axis])))
    if baseline:
        seen_ladder_pairs=set();unique=[]
        for feature in features:
            if feature['kind'].startswith('ladder-'):
                key=(feature['kind'],tuple(feature['groups']))
                if key in seen_ladder_pairs:continue
                seen_ladder_pairs.add(key)
            unique.append(feature)
        features=unique
    return dict(glyph=glyph,points=points,groups=groups,features=features,extrema=extrema,extraction=[('analytic connecting segments and full support/counter strips; explicit epsilon settings' if baseline else 'analytic curve interiors with sampled cross-stroke checks and project tolerances'), 'serif coverage is limited to configured reusable templates'])


def constraints_for(model,tables,em,baseline=False):
    p=model['points'];groups=model['groups'];candidates=[];attachments=[];reps=set()
    def add(kind,point,n,sources=(),value=None,**extra):candidates.append(relation(kind,point,n,sources,value,**extra))
    def shared(kind,value):
        close=[v for v in tables.get(kind,[]) if abs(v-value)<=.01*em]
        return min(close,key=lambda v:abs(v-value)) if close else None
    # Character dimensions are constraints, distinct from unchanged advance width.
    for axis,(a,b) in model['extrema'].items():
        role='glyph-x-bound' if axis==0 else 'glyph-y-bound'
        n=np.eye(2)[axis];add('Abs',a,n,value=float(p[a,axis]),metric=True,metric_role=role)
        if b!=a:add('Dist',b,n,[a],float(p[b,axis]-p[a,axis]),metric=True,metric_role=role)
        reps.update((a,b))
    for i,g in enumerate(groups):
        if not g['members']:continue
        r=g['rep'];n=np.asarray(g['normal']);value=float(p[r]@n);global_value=shared(g.get('height_kind',''),value)
        if baseline and global_value is None and 'height_lookup' in g:
            heights=[shared(kind,value) for kind in tables if kind.startswith('height-') and kind.endswith(g['height_lookup'])]
            heights=[v for v in heights if v is not None]
            if heights:global_value=min(heights,key=lambda v:abs(v-value))
        add('PAbs' if global_value is not None else 'Abs',r,n,value=global_value if global_value is not None else value,feature=f'segment-{i}',**(dict(segment_owner=i) if baseline else {}))
        reps.add(r)
        for member in sorted(g['members']-{r}):
            # A horizontal baseline link carries character-metric semantics even
            # when its endpoint also represents a diagonal (§3.6). Preserve
            # ordinary priority for other local alignments and experimental code.
            baseline_link=baseline and n[0]==0 and p[r,1]==0 and p[member,1]==0
            attachments.append(relation('Dist',member,n,[r],float((p[member]-p[r])@n),round=False,feature=f'align-{i}',
                                        **(dict(metric=True,metric_role='baseline') if baseline_link else {})))
    for i,f in enumerate(model['features']):
        ga,gb=f['groups'];a,b=groups[ga]['rep'],groups[gb]['rep'];n=np.asarray(f['normal'])
        if float((p[b]-p[a])@n)<0:a,b,ga,gb=b,a,gb,ga
        value=float((p[b]-p[a])@n);global_value=shared(f['kind'],value)
        add('PDist' if global_value is not None else 'Dist',b,n,[a],global_value if global_value is not None else value,feature=f'width-{i}',**(dict(segment_owner=gb) if baseline else {}))
    return candidates,attachments,reps


def complex_feature_ownership(geometry,model,templates):
    """A complete taper owns its transverse shape; ordinary caps remain shared."""
    from shamir_templates import recognize_templates
    _,_,members=prepared_glyph(geometry);evidence=[]
    for hit in recognize_templates(geometry,templates):
        if hit['name']!='TaperedStroke' or not hit.get('supported',False):continue
        contour=geometry['points'][hit['points'][0]]['contour']
        owned={i for segment in geometry['segments'] if segment['contour']==contour for i in members[segment['id']]}
        axis=np.asarray(hit['frame'][1]);suppressed=[]
        for i,g in enumerate(model['groups']):
            if g['members'] and g['members']<=owned and abs(float(np.dot(g['normal'],axis)))<.999:
                suppressed.append(dict(group=i,normal=g['normal'],members=sorted(g['members'])))
                g['members']=set()
        removed={g['group'] for g in suppressed}
        features=[f for f in model['features'] if removed.intersection(f['groups'])]
        model['features']=[f for f in model['features'] if not removed.intersection(f['groups'])]
        evidence.append(dict(name=hit['name'],contour=contour,suppressed_groups=suppressed,
                             suppressed_features=features,retained='cap-axis groups and character metrics'))
    return evidence


def build_font(source,output,chars,templates=None,normalize=True,scheduler="scalar",profile="experimental",ppem=None):
    if profile not in ('experimental','baseline'):raise ValueError(f'unknown profile: {profile}')
    baseline=profile=='baseline'
    if baseline:
        if templates is not None or not normalize or scheduler!='scalar':
            raise ValueError('baseline fixes template, preparation and scheduler policies; use experimental profile for overrides')
        if ppem is None or ppem<=0:raise ValueError('baseline native adapter requires positive ppem')
        from shamir_baseline_solver import resolve_baseline,compile_baseline
        from shamir_baseline_templates import instantiate_baseline_templates
        from shamir_baseline import baseline_decisions
        from shamir_baseline_members import assemble_member_graph,schedule_member_graph
        from shamir_baseline_completion import complete_defaults
    resolver=resolve_baseline if baseline else lambda points,cs,reference_points=(): resolve(points,cs,reference_points,scheduler=scheduler)
    font=TTFont(source,recalcTimestamp=False)
    if 'glyf' not in font or 'fvar' in font:raise ValueError('instantiated static quadratic font required')
    from shamir_boundary import normalize_boundaries
    preparation=normalize_boundaries(font,chars) if normalize else dict(method='raw outline diagnostic',changed=[])
    from shamir_templates import instantiate_templates,calibration_templates
    templates=templates if templates is not None else calibration_templates()
    em=font['head'].unitsPerEm;models={};samples=[]
    for char in dict.fromkeys(chars):
        geometry=from_font(font,char,baseline=True) if baseline else from_font(font,char)
        model=feature_model(geometry,baseline=baseline);models[char]=model
        model['template_ownership']=[] if baseline else complex_feature_ownership(geometry,model,templates)
        _,mapping,_=prepared_glyph(geometry)
        if baseline:
            model['template_constraints'],model['templates']=instantiate_baseline_templates(geometry,mapping,model['points'],basic_groups=model['groups'],basic_features=model['features'])
        else:
            model['template_constraints'],model['templates']=instantiate_templates(geometry,mapping,model['points'],templates,basic_groups=model['groups'],basic_features=model['features'])
        samples.extend((f['kind'],f['width'],char) for f in model['features'])
        for g in model['groups']:
            if g['members'] and 'height_kind' in g:samples.append((g['height_kind'],float(model['points'][g['rep']]@g['normal']),char))
    tables=clusters(samples,em,baseline=True) if baseline else clusters(samples,em);cvt=[];records={};cmap=font.getBestCmap()
    def cvt_id(value):
        value=round(value)
        if value not in cvt:cvt.append(value)
        return cvt.index(value)
    for tag in ('fpgm','prep','cvt ','hdmx','LTSH','VDMX','gasp'):
        if tag in font:del font[tag]
    for name in font.getGlyphOrder():font['glyf'][name].program=Program();font['glyf'][name].program.fromAssembly([])
    for char,m in models.items():
        cs,attachments,reps=constraints_for(m,tables,em,baseline=baseline)
        dominance={}
        if baseline:
            from shamir_segment_dominance import dominant_relations
            cs,dominance=dominant_relations(cs)
        template_core=[c for c in m['template_constraints'] if not (baseline and c.get('template_member'))]
        if baseline:attachments.extend(c for c in m['template_constraints'] if c.get('template_member'))
        cs.extend(template_core)
        reps.update(c['point'] for c in template_core)
        reps.update(s for c in template_core for s in c['sources'])
        # Shared-role links undergo ordinary priorities and cycle resolution.
        # Segment dominance is established before this explicit overlap policy.
        if baseline:
            from shamir_shared_roles import close_shared_roles
            roles=close_shared_roles(cs,attachments,reps)
            cs=roles['reduced_candidates'];late_attachments=roles['late_attachments']
        else:cs.extend(c for c in attachments if c['point'] in reps)
        representative_points=sorted(reps);index={p:i for i,p in enumerate(representative_points)}
        reduced=[dict(c,point=index[c['point']],sources=[index[s] for s in c['sources']]) for c in cs]
        reduced_graph=resolver(m['points'][representative_points],reduced)
        accepted=[dict(c,point=representative_points[c['point']],sources=[representative_points[s] for s in c['sources']]) for c in reduced_graph['constraints']]
        # Selected nondefault representative relations survive late attachments.
        if baseline:
            contours=[];start=0
            for end in m['glyph'].endPtsOfContours:
                contours.append(list(range(start,end+1)));start=end+1
            graph=assemble_member_graph(m['points'],accepted,late_attachments,references=reps,contours=contours,completion=complete_defaults)
            graph=schedule_member_graph(graph,m['points'],reps)
        else:
            graph=resolver(m['points'],accepted+[c for c in attachments if c['point'] not in reps],reference_points=reps)
        if baseline:
            assembly,graph['baseline_execution']=compile_baseline(graph,m['points'],ppem,em,cvt_id)
        else:assembly=compile_graph(graph,cvt_id)
        g=m['glyph'];g.program.fromAssembly(assembly);font['glyf'][cmap[ord(char)]]=g
        # Every proposed alignment has an auditable outcome, including links
        # between representatives and links removed to break dependency cycles.
        discarded={(r['constraint']['point'],r['constraint'].get('feature')):r['reason']
                   for r in graph['rejected']}
        discarded.update({(representative_points[r['constraint']['point']],r['constraint'].get('feature')):r['reason']
                          for r in reduced_graph['rejected']})
        selected={(c['point'],c.get('feature')) for c in graph['constraints'] if not c.get('default')}
        attachment_resolution=[]
        for c in attachments:
            key=(c['point'],c['feature'])
            if key in discarded:status,reason='rejected',discarded[key]
            elif key in selected:status,reason='selected',None
            else:raise AssertionError(f'alignment proposal lost: {key}')
            attachment_resolution.append(dict(constraint=c,status=status,reason=reason))
        records[char]=dict(graph=graph,reduced_graph=reduced_graph,attachment_resolution=attachment_resolution,
                           **(dict(segment_dominance=dominance,representative_points=representative_points,shared_role_assumption=roles['assumption']) if baseline else {}),
                           features=[dict(f,points=[m['groups'][g]['rep'] for g in f['groups']]) for f in m['features']],
                           templates=m['templates'],template_ownership=m['template_ownership'],extraction=m['extraction'])
    font['cvt ']=newTable('cvt ');font['cvt '].values=array('h',cvt)
    maxp=font['maxp'];maxp.maxZones=2;maxp.maxTwilightPoints=0;maxp.maxStorage=0;maxp.maxFunctionDefs=0;maxp.maxInstructionDefs=0;maxp.maxStackElements=8
    maxp.maxSizeOfInstructions=max(len(font['glyf'][n].program.getBytecode()) for n in font.getGlyphOrder())
    font.save(output)
    return dict(records=records,clusters=tables,cvt=cvt,preparation=preparation,
                **(dict(baseline_decisions=baseline_decisions(),baseline_ppem=ppem,measurement_samples=samples) if baseline else {}))
