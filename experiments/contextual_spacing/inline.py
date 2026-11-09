"""Losslessly project the first captured font into an offline inline comparison.

All supplied presets remain available. Exceeding the inline size limit is an
explicit error, never a reason to silently discard text or comparison modes.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import re
import struct
import zopfli
import zopfli.gzip
from browser_reference import compact_browser_reference

MAX_CHARACTERS = 512000
SAMPLE = ('ty type type type\nyp pe\nlynx tuft frogs\nff cc zz nn oo no on\nbd ct ab du\njo yd le pi ip te tp OE OR\noe kh rn xn co\n'
          '01 12 23 0123456789\nlynx tuft frogs, dolphins abduct by proxy\n'
          'minimum awkward rhythm unique possible re t f tiflnm')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def build(document, selected_models, sample_text=None):
    match = re.search(r'<script id="spacing-data" type="application/json">(.*?)</script>', document, re.S)
    page = json.loads(match.group(1))
    page['cases'] = page['cases'][:1]
    font = page['cases'][0]
    full_presets = len(page['presets'])
    font.pop('verification', None)
    font['models'] = {name: font['models'][name] for name in selected_models}
    sample = SAMPLE if sample_text is None else sample_text
    page['defaultText'] = font['defaultText'] = sample
    if page.get('defaultSpacingModel') not in selected_models:
        page['defaultSpacingModel'] = 'hu_source_relative' if 'hu_source_relative' in selected_models else selected_models[0]
    required = {ord(c) for preset in page['presets'] for c in preset['text'] if c != '\n'}
    required |= {ord(c) for c in sample if c != '\n'}
    previous = font['codepoints']
    assert required <= set(previous), sorted(required - set(previous))
    selected = [i for i, cp in enumerate(previous) if cp in required]
    pairs = [i * len(previous) + j for i in selected for j in selected]
    for model in font['models'].values():
        for key, value in list(model.items()):
            if isinstance(value, list) and value and all(isinstance(row, list) and len(row) == len(previous)**2 for row in value):
                model[key] = [[row[i] for i in pairs] for row in value]
            elif isinstance(value, list) and len(value) == len(previous)**2:
                model[key] = [value[i] for i in pairs]
        # These are offline audit fields; no page.js consumer reads them.
        for key in ('counterspace', 'estimator', 'pairReasonCounts', 'preservedPairReasonCounts'):
            model.pop(key, None)
    for key in ('calibration', 'estimator', 'adapterIdentity', 'analysisIdentity'):
        font.pop(key, None)
    font['codepoints'] = [previous[i] for i in selected]
    font['glyphs'] = [g for g in font['glyphs'] if g['codepoint'] in required]
    if 'browserReference' in font:
        font['browserReference'] = compact_browser_reference(font['browserReference'], font['codepoints'])
    original = json.loads(json.dumps(page))
    pool, blocks, palette, numbers, field_map = [], {}, [None], {}, {}
    block_size = len(font['codepoints'])

    def number(value):
        if value is None:
            return 0
        bits = struct.pack('<d', float(value))
        if bits not in numbers:
            numbers[bits] = len(palette)
            palette.append(value)
        return numbers[bits]

    def pack(values):
        refs = []
        for start in range(0, len(values), block_size):
            block = tuple(number(value) for value in values[start:start + block_size])
            if block not in blocks:
                blocks[block] = len(pool)
                pool.append(block)
            refs.append(blocks[block])
        return refs

    def numeric(value):
        return value is None or type(value) in (int, float)

    def encode_column(values):
        if all(map(numeric, values)):
            return {'refs': pack(values)}
        present = [item for item in values if item is not None]
        if present and all(isinstance(item, dict) for item in present):
            keys = set(present[0])
            if all(set(item) == keys for item in present):
                return dict(present=pack([int(item is not None) for item in values]),
                            columns={key: encode_column([item[key] if item is not None else None for item in values])
                                     for key in sorted(keys)})
        indices, dictionary, indexed = {}, [], []
        for item in values:
            identity = canonical(item)
            if identity not in indices:
                indices[identity] = len(dictionary)
                dictionary.append(item)
            indexed.append(indices[identity])
        return {'refs': pack(indexed), 'dictionary': dictionary}

    for name, model in font['models'].items():
        matrix, vector, objects, source_overlays = [], [], [], []
        for key, value in list(model.items()):
            if isinstance(value, list) and value and all(isinstance(row, list) and len(row) == block_size**2 and all(map(numeric, row)) for row in value):
                matrix.append(key)
                model[key] = [pack(row) for row in value]
            elif isinstance(value, list) and len(value) == block_size**2 and all(map(numeric, value)):
                vector.append(key)
                model[key] = pack(value)
        for key, value in list(model.items()):
            if isinstance(value, list) and len(value) == block_size**2 and all(isinstance(v, dict) for v in value):
                columns = {}
                for field in value[0]:
                    values = [record[field] for record in value]
                    columns[field] = encode_column(values)
                model[key] = columns
                objects.append(key)
        for key in ('pairTargetMetadataByKerning', 'preservedPairTargetMetadataByKerning'):
            if key not in model:
                continue
            encoded = []
            for row in model[key]:
                fields = ('source_step_px', 'source_target_px', 'target_area_px2', 'unconstrained_step_px')
                nested = ('source_kerning', 'source_step_px', 'source_target_px')
                assert all(set(record) == set(fields) | {'hu_hersch'} for record in row)
                assert all(record['hu_hersch'] is None or set(record['hu_hersch']) == set(nested) for record in row)
                encoded.append(dict(fields={field: pack([record[field] for record in row]) for field in fields},
                    present=pack([int(record['hu_hersch'] is not None) for record in row]),
                    hu={field: pack([record['hu_hersch'][field] if record['hu_hersch'] is not None else None for record in row]) for field in nested}))
            model[key] = encoded
            source_overlays.append(key)
        field_map[name] = {'matrix': matrix, 'vector': vector, 'objects': objects, 'sourceOverlays': source_overlays}
    restored = json.loads(json.dumps(page))

    def unpack(refs):
        return [palette[index] for ref in refs for index in pool[ref]]

    def decode_column(column):
        if 'columns' in column:
            fields = {key: decode_column(value) for key, value in column['columns'].items()}
            return [{key: values[i] for key, values in fields.items()} if present else None
                    for i, present in enumerate(unpack(column['present']))]
        values = unpack(column['refs'])
        return [column['dictionary'][int(value)] for value in values] if 'dictionary' in column else values

    for name, model in restored['cases'][0]['models'].items():
        for key in field_map[name]['matrix']:
            model[key] = [unpack(row) for row in model[key]]
        for key in field_map[name]['vector']:
            model[key] = unpack(model[key])
        for key in field_map[name]['objects']:
            columns = {field: decode_column(column) for field, column in model[key].items()}
            model[key] = [{field: values[i] for field, values in columns.items()} for i in range(block_size**2)]
        for key in field_map[name]['sourceOverlays']:
            decoded = []
            for row in model[key]:
                fields = {field: unpack(refs) for field, refs in row['fields'].items()}
                nested = {field: unpack(refs) for field, refs in row['hu'].items()}
                present = unpack(row['present'])
                decoded.append([dict({field: values[i] for field, values in fields.items()},
                    hu_hersch={field: values[i] for field, values in nested.items()} if present[i] else None)
                    for i in range(block_size**2)])
            model[key] = decoded
    assert restored == original, 'Projected numeric and nested diagnostic values must restore exactly'
    def typed(value):
        if value is None:
            return ['null']
        if type(value) is bool:
            return ['bool', value]
        if type(value) in (int, float):
            return ['number', struct.pack('<d', float(value)).hex()]
        if isinstance(value, str):
            return ['string', value]
        if isinstance(value, list):
            return ['array', [typed(item) for item in value]]
        return ['object', [[key, typed(value[key])] for key in sorted(value)]]
    projected_typed_sha256 = hashlib.sha256(json.dumps(typed(original), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    width = 2 if len(palette) <= 65536 else 4
    style_match = re.search(r'<style>(.*?)</style>', document, re.S)
    script_match = re.search(r'<script>(.*?)</script>', document, re.S)
    assert style_match and script_match
    guard = 'if (typeof document !== "undefined") {'
    runtime_script = script_match.group(1)
    assert runtime_script.count(guard) == 1
    runtime_script = runtime_script.replace(guard, 'if (typeof document !== "undefined" && document.getElementById("spacing-data").type === "application/json") {')
    # Retain every value while grouping equal low-order float bytes. The remap
    # changes storage indices only; the typed-value hash covers restored data.
    order = [0] + sorted(range(1, len(palette)), key=lambda i: struct.pack('<d', float(palette[i])))
    remap = {old: new for new, old in enumerate(order)}
    palette = [palette[i] for i in order]
    pool = [tuple(remap[i] for i in block) for block in pool]
    shell = document[:match.start()] + '<script id="spacing-data" type="application/octet-stream"></script>' + document[match.end():]
    shell = shell.replace(script_match.group(0), '')
    shell = re.sub(r'<header class="intro">.*?</header>', '', shell, count=1, flags=re.S)
    hint = f'Inline view: {font["label"]} / {len(selected_models)} models. All {full_presets} supplied presets retained. The full offline page contains all four fonts. Optical quality remains pending assessment.'
    shell = shell.replace('<section class="controls"', f'<p class="hint">{hint}</p><section class="controls"', 1)
    runtime_body = re.search(r'<body>(.*?)</body>', shell, re.S).group(1)
    header = json.dumps(dict(page=page, fields=field_map, blockLengths=list(map(len, pool)),
                             paletteCount=len(palette), indexWidth=width,
                             runtimeBody=runtime_body, runtimeStyle=style_match.group(1), runtimeScript=runtime_script), separators=(',', ':'), ensure_ascii=True).encode()
    def shuffle(data, stride):
        # Group equal byte positions before gzip; this is a reversible byte
        # permutation, preserving every IEEE754 value and table index exactly.
        return b''.join(data[offset::stride] for offset in range(stride))

    raw = (struct.pack('<I', len(header)) + header +
           shuffle(struct.pack('<' + 'd' * len(palette), *(float('nan') if v is None else v for v in palette)), 8) +
           shuffle(struct.pack('<' + ('H' if width == 2 else 'I') * sum(map(len, pool)), *(v for block in pool for v in block)), width))
    if zopfli.__version__ != "0.4.0":
        raise RuntimeError("inline packing requires zopfli==0.4.0")
    payload = base64.b64encode(zopfli.gzip.compress(raw, numiterations=5)).decode()
    html = document[:document.index('<body>')] + f'<body><p id="status">Loading comparison…</p><script id="spacing-data" type="application/octet-stream">{payload}</script></body></html>'
    html = html.replace(style_match.group(0), '<style id="inline-style"></style>')
    bootstrap = """<script>(async()=>{try{const el=document.getElementById('spacing-data');const bytes=Uint8Array.from(atob(el.textContent),c=>c.charCodeAt(0));const raw=await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();const view=new DataView(raw);const length=view.getUint32(0,true);const data=JSON.parse(new TextDecoder().decode(new Uint8Array(raw,4,length)));const unshuffle=(bytes,stride)=>{const count=bytes.length/stride;const result=new Uint8Array(bytes.length);for(let byte=0;byte<stride;byte++)for(let i=0;i<count;i++)result[i*stride+byte]=bytes[byte*count+i];return new DataView(result.buffer);};let cursor=4+length;const paletteView=unshuffle(new Uint8Array(raw,cursor,data.paletteCount*8),8);const values=Array.from({length:data.paletteCount},(_,i)=>{const value=paletteView.getFloat64(i*8,true);return Number.isNaN(value)?null:value;});cursor+=data.paletteCount*8;const indexView=unshuffle(new Uint8Array(raw,cursor),data.indexWidth);let indexCursor=0;const blocks=data.blockLengths.map(length=>Array.from({length},()=>{const index=data.indexWidth===2?indexView.getUint16(indexCursor,true):indexView.getUint32(indexCursor,true);indexCursor+=data.indexWidth;return values[index];}));const unpack=refs=>refs.flatMap(ref=>blocks[ref]);const decodeColumn=column=>{if(column.columns){const fields=Object.fromEntries(Object.entries(column.columns).map(([key,value])=>[key,decodeColumn(value)]));return unpack(column.present).map((present,i)=>present?Object.fromEntries(Object.entries(fields).map(([key,values])=>[key,values[i]])):null);}return unpack(column.refs).map(value=>column.dictionary?column.dictionary[value]:value);};for(const font of data.page.cases)for(const[name,model]of Object.entries(font.models)){for(const key of data.fields[name].matrix)model[key]=model[key].map(unpack);for(const key of data.fields[name].vector)model[key]=unpack(model[key]);for(const key of data.fields[name].objects){const columns=Object.fromEntries(Object.entries(model[key]).map(([field,column])=>[field,decodeColumn(column)]));model[key]=Array.from({length:font.codepoints.length**2},(_,i)=>Object.fromEntries(Object.entries(columns).map(([field,values])=>[field,values[i]])));}for(const key of data.fields[name].sourceOverlays||[]){model[key]=model[key].map(row=>{const fields=Object.fromEntries(Object.entries(row.fields).map(([key,refs])=>[key,unpack(refs)]));const nested=Object.fromEntries(Object.entries(row.hu).map(([key,refs])=>[key,unpack(refs)]));const present=unpack(row.present);return present.map((exists,i)=>({...Object.fromEntries(Object.entries(fields).map(([key,values])=>[key,values[i]])),hu_hersch:exists?Object.fromEntries(Object.entries(nested).map(([key,values])=>[key,values[i]])):null}));});}}globalThis.__inlineSpacingData=data.page;document.getElementById('inline-style').textContent=data.runtimeStyle;const script=document.createElement('script');script.textContent=data.runtimeScript;document.body.append(script);ContextualSpacing.mount(data.page);}catch(error){document.getElementById('status').textContent='Comparison could not load: '+error.message;}})();</script>"""
    bootstrap = bootstrap.replace("globalThis.__inlineSpacingData=data.page;", "document.body.innerHTML=data.runtimeBody;globalThis.__inlineSpacingData=data.page;")
    html = html.replace('</body>', bootstrap + '</body>')
    manifest = dict(sourcePageSha256=hashlib.sha256(document.encode()).hexdigest(),
                    inlineSha256=hashlib.sha256(html.encode()).hexdigest(), losslessDataVerification=True,
                    projectedTypedSha256=projected_typed_sha256, models=selected_models, inlineCharacters=len(html), numericBlocks=len(pool),
                    numericValues=len(palette), indexWidth=width, sample=sample,
                    codepoints=font['codepoints'], presets=len(page['presets']), fullPagePresets=full_presets,
                    generatorSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return html, manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_page', type=Path)
    parser.add_argument('output_directory', type=Path)
    parser.add_argument('--models', nargs='+', default=['hu_source_relative', 'hu_hersch', 'source_relative'])
    parser.add_argument('--text-file', type=Path, help='Initial sample text; every character must be captured')
    options = parser.parse_args()
    if options.output_directory.exists():
        parser.error('output directory already exists')
    document = options.input_page.read_text()
    html, manifest = build(document, options.models, options.text_file.read_text() if options.text_file else None)
    if len(html) > MAX_CHARACTERS:
        raise ValueError(f'Inline HTML exceeds tool limit: {len(html)} characters')
    options.output_directory.mkdir(parents=True)
    (options.output_directory / 'index.html').write_text(html)
    (options.output_directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest))
