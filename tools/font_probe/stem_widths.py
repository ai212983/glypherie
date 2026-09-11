"""Source-geometric stem-to-adjoining-section width inheritance experiment."""
import math
import numpy as np


def inherit_widths(strokes, features, links):
    members={}
    for feature in features:
        for group,point in zip(feature['groups'],feature['points']):
            members.setdefault(group,set()).add(point)
    for c in links:
        name=c.get('feature','')
        if name.startswith('align-'):
            group=int(name[6:]);members.setdefault(group,set()).update([c['point'],*c['sources']])
    audit=[]
    for stroke in strokes:
        section=features[stroke['feature']];candidates=[]
        for index,stem in enumerate(features):
            if stem['kind']!='stem' or stem['width']<=0:continue
            common=set(section['groups']) & set(stem['groups'])
            if len(common)!=1:continue
            outer=next(iter(common))
            sg=next(g for g in section['groups'] if g!=outer)
            tg=next(g for g in stem['groups'] if g!=outer)
            junction=members[sg] & members[tg]
            if not junction:continue
            n=np.array(section['normal'],float);m=np.array(stem['normal'],float)
            cosine=abs(float(n@m))/(np.linalg.norm(n)*np.linalg.norm(m))
            # Explicit experimental limits: nearly parallel, modest source taper.
            if cosine<math.cos(math.radians(5)):continue
            ratio=section['width']/stem['width']
            if not .8<=ratio<=1.2:continue
            candidates.append(dict(feature=index,width=int(math.floor(stem['width']+.5)),
                                   shared_group=outer,junction_points=sorted(junction)))
        if not candidates:continue
        row=dict(section=stroke['feature'],before=stroke['cvts'].copy(),candidates=candidates)
        widths={c['width'] for c in candidates}
        if len(widths)!=1:
            row['status']='ambiguous-width';audit.append(row);continue
        width=next(iter(widths))
        if width<=0:continue
        stroke['cvts']=[width,width];stroke['shared_cvt']=True
        row.update(status='inherited',after=width);audit.append(row)
    return audit
