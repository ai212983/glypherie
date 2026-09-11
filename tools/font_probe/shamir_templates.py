"""Reusable sequence automata and constraint templates (1996 §4.4; 2003 §3.5).

Sequences use point categories, not glyph identities. Published example
sequences are available for recognition; constraint recipes are explicit inputs
because the papers do not publish a complete serif hint library.
"""
import numpy as np
from shamir_constraints import relation
from shamir_features import Interior

PUBLISHED_SEQUENCES={
    'MinchoBarCap':[['HR','CH','T','V','T']],
    'RomanSerif':[['T','T','LR','LR','LR','LR','T','T']],
}


def tapered_contour(model,contour,ids):
    """Recognize a complete elongated taper, in a geometry-derived local frame."""
    if len(ids)!=4 or any(model['segments'][s]['kind']!='line' for s in contour):return None
    p=np.array([model['points'][i]['position'] for i in ids])
    if not Interior(model).contains(p.mean(axis=0)):return None
    edges=np.roll(p,-1,axis=0)-p
    turns=edges[:,0]*np.roll(edges,-1,axis=0)[:,1]-edges[:,1]*np.roll(edges,-1,axis=0)[:,0]
    if not (np.all(turns>0) or np.all(turns<0)):return None
    lengths=np.linalg.norm(edges,axis=1);eps=model['tolerances']['distance']
    for k in (0,1):
        a,b=k,k+2
        if min(lengths[a],lengths[b])<=eps:continue
        if abs(float(edges[a]@edges[b]/(lengths[a]*lengths[b])))<np.cos(model['tolerances']['angle_radians']):continue
        wide,narrow=(a,b) if lengths[a]>lengths[b] else (b,a)
        if lengths[wide]-lengths[narrow]<=eps:continue
        n=edges[wide]/lengths[wide]
        if n[np.argmax(abs(n))]<0:n=-n
        w=sorted((wide,(wide+1)%4),key=lambda i:p[i]@n)
        q=sorted((narrow,(narrow+1)%4),key=lambda i:p[i]@n)
        longitudinal=np.array([-n[1],n[0]])
        if ((p[q].mean(axis=0)-p[w].mean(axis=0))@longitudinal)<0:longitudinal=-longitudinal
        length=float((p[q].mean(axis=0)-p[w].mean(axis=0))@longitudinal)
        if length<3*lengths[wide]:continue
        if min(p[q]@n)<min(p[w]@n)-eps or max(p[q]@n)>max(p[w]@n)+eps:continue
        cardinal=bool(np.max(np.abs(n))>1-1e-10)
        return dict(points=[ids[i] for i in w+q],frame=[n.tolist(),longitudinal.tolist()],
                    supported=cardinal,unsupported_reason=None if cardinal else 'noncardinal taper recipe conflicts with character-axis metric ownership',
                    wide_cap_units=float(lengths[wide]),narrow_cap_units=float(lengths[narrow]),
                    half_pixel_ppem=float(.5*model['em']/lengths[wide]),
                    width_policy='nearest-pixel wide cap; subpixel caps may collapse')
    return None


def recognize_templates(model,templates):
    hits=[]
    for contour in model['contours']:
        ids=[model['segments'][s]['start'] for s in contour]
        # Quadratic encoding introduces smooth subdivision joins that carry no
        # typographic event. Retain extrema/inflections, skip only plain CT/line.
        ids=[i for i in ids if model['points'][i]['categories'] not in (['CT'],['line'])]
        for name,template in templates.items():
            if template.get('geometry')=='tapered-stroke':
                hit=tapered_contour(model,contour,ids)
                if hit:hits.append(dict(name=name,**hit))
                continue
            for sequence in template['sequences']:
                if not sequence or len(sequence)>len(ids):continue
                # A finite chain of category transitions; every cyclic start is
                # considered, so contour encoding does not affect recognition.
                for start in range(len(ids)):
                    path=[ids[(start+k)%len(ids)] for k in range(len(sequence))]
                    if all(token in model['points'][pid]['categories'] for token,pid in zip(sequence,path)):
                        if template.get('geometry')=='horizontal-foot':
                            p=np.array([model['points'][i]['position'] for i in path]);eps=.012*model['em']
                            if abs(p[0,1]-p[-1,1])>eps or abs(p[3,1]-p[4,1])>eps:continue
                            if min(p[0,1],p[-1,1])-max(p[3,1],p[4,1])<=eps:continue
                            left,right=sorted((p[3,0],p[4,0]))
                            if not all(left-eps<=x<=right+eps for x in p[:,0]):continue
                            if right-left<=abs(p[0,0]-p[-1,0])+eps:continue
                        if template.get('geometry')=='horizontal-cap':
                            p=np.array([model['points'][i]['position'] for i in path]);before=np.array(model['points'][ids[(start-1)%len(ids)]]['position']);after=np.array(model['points'][ids[(start+2)%len(ids)]]['position'])
                            width=abs(p[1,0]-p[0,0]);eps=.003*model['em']
                            flank0=before-p[0];flank1=after-p[1]
                            if width<=eps or abs(p[1,1]-p[0,1])>eps:continue
                            if flank0[1]*flank1[1]<=0 or min(abs(flank0[1]),abs(flank1[1]))<2*width:continue
                            if any(abs(v[0])>.15*abs(v[1]) for v in (flank0,flank1)):continue
                        if template.get('geometry')=='rounded-terminal':
                            p=np.array([model['points'][i]['position'] for i in path]);eps=.012*model['em']
                            if abs(p[0,1]-p[-1,1])>eps or abs(p[2,1]-p[4,1])>eps:continue
                            if p[3,1]<=max(p[0,1],p[-1,1])+2*abs(p[0,0]-p[-1,0]):continue
                            if not min(p[2,0],p[4,0])<p[3,0]<max(p[2,0],p[4,0]):continue
                        hits.append(dict(name=name,points=path))
    # Prefer the larger declared sequence when one match is a sub-automaton.
    accepted=[]
    for hit in sorted(hits,key=lambda h:(-len(h['points']),h['name'],h['points'])):
        if any(set(hit['points'])<=set(a['points']) for a in accepted):continue
        accepted.append(hit)
    return accepted


def template_members(model,mapping,hit):
    """Native points along the matched contour, including skipped joins/controls."""
    contour=model['contours'][model['points'][hit['points'][0]]['contour']]
    if 'frame' in hit:segments=contour  # A taper matches the entire contour.
    else:
        start=next(i for i,s in enumerate(contour) if model['segments'][s]['start']==hit['points'][0])
        segments=[]
        for offset in range(len(contour)):
            sid=contour[(start+offset)%len(contour)]
            if model['segments'][sid]['start']==hit['points'][-1]:break
            segments.append(sid)
    owned={mapping[p] for p in hit['points']}
    for sid in segments:
        segment=model['segments'][sid];start=mapping[segment['start']]
        owned.update(range(start,start+len(segment['control'])-1))
        owned.add(mapping[segment['end']])
    return owned


def instantiate_templates(model,mapping,points,templates,basic_groups=(),basic_features=()):
    """Bind template ports to existing feature coordinates before adding shape.

    Explicit ports and basic sides extending beyond the matched contour share
    their existing projected coordinates. A side wholly inside the match remains
    available to the authored recipe. Native controls and skipped smooth joins
    belong to the match, so curve subdivision cannot invent a boundary.
    A rounded distance already owned by a basic feature reuses that width;
    authored shape interpolation continues to use its resulting coordinates.
    """
    constraints=[];unconfigured=[];bindings=[];hits=recognize_templates(model,templates)
    for hit in hits:
        ids=[mapping[p] for p in hit['points']]
        hit['native_points']=ids
        owned=template_members(model,mapping,hit)
        if hit.get('supported') is False:
            unconfigured.append(dict(hit,reason=hit['unsupported_reason']));continue
        recipes=templates[hit['name']].get('constraints')
        if not recipes:unconfigured.append(hit);continue
        for recipe in recipes:
            p=ids[recipe['point']];sources=[ids[s] for s in recipe.get('sources',[])];n=recipe['normal'];kind=recipe['kind']
            if 'frame' in hit:n=(np.asarray(n)@np.asarray(hit['frame'])).tolist()
            if recipe.get('bind',True) and kind=='Dist' and recipe.get('round',True):
                normal=np.asarray(n,float);normal/=np.linalg.norm(normal)
                widths=[]
                for i,feature in enumerate(basic_features):
                    if len(feature['groups'])!=2 or abs(float(normal@np.asarray(feature['normal'])))<=.999:continue
                    a,b=[basic_groups[g]['members'] for g in feature['groups']]
                    if (p in a and sources[0] in b) or (p in b and sources[0] in a):widths.append(i)
                if widths:
                    bindings.append(dict(name=hit['name'],point=p,normal=normal.tolist(),
                                         features=widths,reason='existing basic width',recipe=dict(recipe)))
                    continue
            if recipe.get('bind',True):
                port=recipe['point'] in templates[hit['name']].get('ports',())
                normal=np.asarray(n,float);normal/=np.linalg.norm(normal)
                owners=[i for i,g in enumerate(basic_groups) if p in g['members'] and
                        abs(float(normal@np.asarray(g['normal'])))>.999 and
                        (port or not set(g['members'])<=owned)]
                if owners:
                    bindings.append(dict(name=hit['name'],point=p,normal=normal.tolist(),
                                         groups=owners,reason='explicit port' if port else 'side crosses template boundary',recipe=dict(recipe)))
                    continue
            value=recipe.get('value')
            if value is None:
                if kind=='Abs':value=float(points[p]@n)
                elif kind=='Dist':value=float((points[p]-points[sources[0]])@n)
                elif kind=='Ratio':
                    a,b=sources;den=float((points[b]-points[a])@n)
                    if abs(den)<1e-9:raise ValueError('degenerate template Ratio')
                    value=float((points[p]-points[a])@n)/den
                else:raise ValueError('parametric template requires value')
            constraints.append(relation(kind,p,n,sources,value,round=recipe.get('round',True),feature=hit['name']))
    return constraints,dict(matches=hits,unconfigured=unconfigured,bindings=bindings)


def calibration_templates():
    """Authored reusable complex-feature recipes; no glyph/size conditions.

    Corner sequence is the epsilon-rule variant of the published Roman serif.
    Preserve foot width/depth and interpolate the bracket between those anchors.
    The taper couples cap widths through Ratio in a geometry-derived frame.
    This is project-authored knowledge, as required by 1996 §4.4, not a recovered
    copy of the authors' unpublished template library.
    """
    recipes=[dict(kind='Abs',point=3,normal=[1,0]),
             dict(kind='Dist',point=4,sources=[3],normal=[1,0]),
             dict(kind='Abs',point=3,normal=[0,1]),
             dict(kind='Dist',point=4,sources=[3],normal=[0,1],round=False),
             dict(kind='Dist',point=0,sources=[3],normal=[0,1]),
             dict(kind='Dist',point=7,sources=[0],normal=[0,1],round=False)]
    for i in (0,1,2,5,6,7):recipes.append(dict(kind='Ratio',point=i,sources=[3,4],normal=[1,0],round=False))
    for i in (1,2,5,6):recipes.append(dict(kind='Ratio',point=i,sources=[3,0],normal=[0,1],round=False))
    rounded=[dict(kind='Abs',point=2,normal=[1,0]),dict(kind='Dist',point=4,sources=[2],normal=[1,0]),dict(kind='Abs',point=3,normal=[0,1])]
    for i in (0,1,3,5,6):rounded.append(dict(kind='Ratio',point=i,sources=[2,4],normal=[1,0],round=False))
    # A taper shares its narrow-cap coordinates with the fitted wide cap via
    # Ratio; its width is therefore fitted once. Caps inherit ordinary segments.
    taper=[dict(kind='Abs',point=0,normal=[1,0],bind=False),
           dict(kind='Dist',point=1,sources=[0],normal=[1,0],bind=False)]
    for i in (2,3):taper.append(dict(kind='Ratio',point=i,sources=[0,1],normal=[1,0],round=False,bind=False))
    taper.extend([dict(kind='Abs',point=0,normal=[0,1]),
                  dict(kind='Dist',point=1,sources=[0],normal=[0,1],round=False),
                  dict(kind='Dist',point=2,sources=[0],normal=[0,1]),
                  dict(kind='Dist',point=3,sources=[2],normal=[0,1],round=False)])
    # Flat stroke ends already have basic segment widths and member alignment.
    # A second rounded terminal width would compete with that same dimension.
    return {'TaperedStroke':dict(sequences=[],geometry='tapered-stroke',ports=[0,1,2,3],constraints=taper),
            'BracketedFoot':dict(sequences=[['T','T','CV','LR','LR','CV','T','T']],geometry='horizontal-foot',ports=[0,7],constraints=recipes),
            'RoundedTerminal':dict(sequences=[['T','I','V','H','V','I','T']],geometry='rounded-terminal',ports=[0,6],constraints=rounded)}
