// Run after build.sh nodejs preview. Differential checks of the live native and
// WASM method seam, including integer selection/pow, not historical snapshots.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync, mkdirSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {basename, relative, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
const root = fileURLToPath(new URL('../../../', import.meta.url));
const require = createRequire(import.meta.url);
const wasmPackage=resolve(root,process.env.KERNING_WASM_PACKAGE ?? 'crates/wasm/pkg-nodejs-preview');
let bindings;
if (existsSync(resolve(wasmPackage,'package.json')) && JSON.parse(readFileSync(resolve(wasmPackage,'package.json'),'utf8')).type==='commonjs') {
  bindings=require(resolve(wasmPackage,'font_wasm.js'));
} else {
  bindings=await import(pathToFileURL(resolve(wasmPackage,'font_wasm.js')).href);
  await bindings.default({module_or_path:readFileSync(resolve(wasmPackage,'font_wasm_bg.wasm'))});
}
const {Font}=bindings;
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const cases = [];
for (const name of ['Literata','Roboto','RobotoFlex','SourceSans3']) {
  for (const size_px of [12,16,20]) for (const settings of [
    {normal_distance_em:.1,intrusion_tolerance_em:.1},
    {normal_distance_em:.0925,intrusion_tolerance_em:.03125},
  ]) for (const letter_spacing_px of [0,1]) {
    cases.push({id:`${name}-${size_px}-${cases.length}`,font_file:resolve(root,`fonts/${name}.ttf`),spec:{
      text:'lynx tuft frogs gs hi ca nx en os se ri ig\nabc ABC 0123', width:180,height:100,
      size_px,axes:{wght:400,...(name==='Literata'?{opsz:size_px}:{})},output_bits:1,
      kerning:true,letter_spacing_px,hinting:'auto_fallback',
      pipeline:{fitting:'font_hints_auto',rasterization:'free_type_mono_terminals',diagonal_fitting:true},
      kerning_method:{method:'typefacet',...settings},
    }});
  }
}
// The source oracle exposed a rounding-sensitive tie at this normal distance.
// Exercise the same decimal/FMA calculation in the actual WASM binary.
cases.push({id:'literata-decimal-tie',font_file:resolve(root,'fonts/Literata.ttf'),spec:{
  ...cases[0].spec,text:'aa',size_px:16,axes:{wght:400,opsz:16},
  kerning_method:{method:'typefacet',normal_distance_em:.0625,intrusion_tolerance_em:0},
}});
// Gray uses fitted curves: exercise every supported coverage depth, real
// collapsed quadratics, mixed case and accented scalars without binary masks.
for (const name of ['Literata','Roboto','RobotoFlex','SourceSans3']) {
  for (const output_bits of [2,3,4]) for (const parameters of [
    {normal_distance_em:.1,intrusion_tolerance_em:.1},
    {normal_distance_em:.0925,intrusion_tolerance_em:.03125},
  ]) {
    cases.push({id:`gray-${name}-${output_bits}-${cases.length}`,font_file:resolve(root,`fonts/${name}.ttf`),spec:{
      text:'AV To Éé Åñ café minimum gs hi nx ca os pe 0123',width:180,height:100,
      size_px:16,axes:{wght:400,...(name==='Literata'?{opsz:16}:{})},output_bits,
      kerning:true,letter_spacing_px:1,hinting:'auto',gray_gamma:1.7,mono_threshold:96,
      pipeline:{fitting:'upstream_mono',rasterization:'coverage'},
      kerning_method:{method:'typefacet',...parameters},
    }});
  }
  // Keep source shaping in one script per strike: some fonts' mixed-script
  // pairs require glyph substitutions outside the scalar renderer contract.
  for (const text of ['αβΩ','Жя']) {
    cases.push({id:`script-${name}-${cases.length}`,font_file:resolve(root,`fonts/${name}.ttf`),spec:{
      text,width:180,height:100,size_px:16,axes:{wght:400,...(name==='Literata'?{opsz:16}:{})},
      output_bits:3,kerning:true,hinting:'auto',
      pipeline:{fitting:'upstream_mono',rasterization:'coverage'},
      kerning_method:{method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1},
    }});
  }
}
// Exercise analytic methods through the same prepared renderer in both binary
// and Gray. Calibration glyphs are intentionally absent from most output text.
// Additional original TypeFacet controls must cross both JS validation and the
// shared solver; old two-field requests retain the zero/.1 defaults.
for (const name of ['Literata','Roboto']) for (const output_bits of [1,3]) {
  for (const controls of [
    {minimum_distance_em:.06,max_x_extrema_overlap_em:.25},
    {minimum_distance_em:0,max_x_extrema_overlap_em:0},
  ]) {
    const spec={text:'AV Ta nn ac ck',width:180,height:100,size_px:16,
      axes:{wght:400,...(name==='Literata'?{opsz:16}:{})},output_bits,
      kerning:true,letter_spacing_px:0,hinting:output_bits===1?'auto_fallback':'auto',
      pipeline:output_bits===1
        ?{fitting:'font_hints_auto',rasterization:'free_type_mono_terminals',diagonal_fitting:true}
        :{fitting:'upstream_mono',rasterization:'coverage'},
      kerning_method:{method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,...controls},
    };
    const {text,width,height,pipeline,kerning_method,letter_spacing_px,...config}=spec;
    cases.push({id:`typefacet-extra-controls-${name}-${output_bits}-${cases.length}`,
      font_file:resolve(root,`fonts/${name}.ttf`),spec,
      ...(output_bits===1?{export_request:{config:{...config,characters:text},pipeline,kerning_method,letter_spacing_px}}:{}),
    });
  }
}
for (const name of ['Literata','Roboto','RobotoFlex','SourceSans3']) {
  for (const output_bits of [1,3]) for (const kerning_method of [
    {method:'hu_hersch'}, {method:'fontforge'},
  ]) {
    const spec = {
      text:'lynx tuft frogs ca nx en os se ri ig AV 0123',width:180,height:100,
      size_px:16,axes:{wght:400,...(name==='Literata'?{opsz:16}:{})},output_bits,
      kerning:true,letter_spacing_px:1,hinting:'auto',
      pipeline:output_bits===1
        ? {fitting:'font_hints_auto',rasterization:'free_type_mono_terminals',diagonal_fitting:true}
        : {fitting:'upstream_mono',rasterization:'coverage'},
      kerning_method,
    };
    cases.push({id:`${kerning_method.method}-${name}-${output_bits}`,font_file:resolve(root,`fonts/${name}.ttf`),spec});
  }
}
for (const output_bits of [2,4]) for (const kerning_method of [
  {method:'hu_hersch'}, {method:'fontforge'},
]) {
  cases.push({id:`analytic-gray-depth-${output_bits}-${kerning_method.method}`,font_file:resolve(root,'fonts/Literata.ttf'),spec:{
    text:'ca en os se nx Éé',width:180,height:100,size_px:16,axes:{wght:400,opsz:16},output_bits,
    kerning:true,hinting:'auto',pipeline:{fitting:'upstream_mono',rasterization:'coverage'},kerning_method,
  }});
}
// Keep source and full-method endpoints, output-independent auxiliary capture,
// and tracked export on the public seam rather than inferring them from profiles.
for (const kerning_method of [{method:'source'},{method:'fontforge'},{method:'hu_hersch'}]) {
  for (const letter_spacing_px of [0,1]) {
    const spec={
      text:'ca en os se nx',width:180,height:100,size_px:16,axes:{wght:400,opsz:16},output_bits:1,
      kerning:true,letter_spacing_px,hinting:'auto',
      pipeline:{fitting:'font_hints_auto',rasterization:'free_type_mono_terminals',diagonal_fitting:true},kerning_method,
    };
    const {text,width,height,pipeline,...config}=spec;
    delete config.letter_spacing_px;
    delete config.kerning_method;
    cases.push({id:`endpoint-export-${kerning_method.method}-${letter_spacing_px}`,
      font_file:resolve(root,'fonts/Literata.ttf'),spec,
      export_request:{config:{...config,characters:text},pipeline,letter_spacing_px,kerning_method},
    });
  }
}
cases.push({id:'hu-unsupported-script-retains-source',font_file:resolve(root,'fonts/SourceSans3.ttf'),spec:{
  text:'αβΩ',width:180,height:100,size_px:16,axes:{wght:400},output_bits:3,
  kerning:true,hinting:'auto',pipeline:{fitting:'upstream_mono',rasterization:'coverage'},
  kerning_method:{method:'hu_hersch'},
},expect_source_identity:true});
// Hu/Hersch depth controls own the full endpoint. Include export through the
// same method seam for both default and explicit depths.
for (const name of ['Literata','Roboto']) for (const output_bits of [1,3]) for (const kerning_method of [
  {method:'hu_hersch'}, {method:'hu_hersch',aperture_depth_factor:.35,global_depth_factor:.4},
]) {
  const spec={
    text:'AV To ca en os se nx',width:240,height:100,size_px:16,
    axes:{wght:400,...(name==='Literata'?{opsz:16}:{})},output_bits,
    kerning:true,letter_spacing_px:1,hinting:'auto',
    pipeline:output_bits===1
      ? {fitting:'font_hints_auto',rasterization:'free_type_mono_terminals',diagonal_fitting:true}
      : {fitting:'upstream_mono',rasterization:'coverage'},
    kerning_method,
  };
  const tag=kerning_method.aperture_depth_factor===undefined?'default':'depths';
  const item={id:`hu-${tag}-${name}-${output_bits}`,font_file:resolve(root,`fonts/${name}.ttf`),spec};
  if(output_bits===1){
    const {text,width,height,pipeline,letter_spacing_px,kerning_method:method,...config}=spec;
    item.export_request={config:{...config,characters:text},pipeline,letter_spacing_px,kerning_method:method};
  }
  cases.push(item);
}
const nativeStarted=performance.now();
const native = spawnSync('cargo',['run','--release','--locked','--quiet','--manifest-path','crates/wasm/Cargo.toml',
  '--features','preview','--example','parity_reference'],{cwd:root,input:JSON.stringify(cases),encoding:'utf8',maxBuffer:16*1024*1024});
assert.equal(native.status,0,native.stderr);
const nativeReferenceMs=performance.now()-nativeStarted;
const expected = JSON.parse(native.stdout), fonts = new Map();
let rendered=0, exported=0;
const started=performance.now();
try {
  for (let i=0;i<cases.length;i++) {
    const c=cases[i], reference=expected[i];
    if (!fonts.has(c.font_file)) fonts.set(c.font_file,new Font(readFileSync(c.font_file)));
    const font=fonts.get(c.font_file);
    assert.equal(reference.error,undefined,`${c.id}: ${reference.error}`);
    const output=font.render(c.spec);
    try {
      assert.equal(hash(output.pixels()),reference.pixel_sha256,c.id);
      assert.deepEqual(output.layout(),reference.layout,c.id);
      if (c.expect_source_identity) {
        const source=font.render({...c.spec,kerning_method:{method:'source'}});
        try {
          assert.equal(hash(output.pixels()),hash(source.pixels()),`${c.id} Source pixels`);
          assert.deepEqual(output.layout(),source.layout(),`${c.id} Source layout`);
        } finally {source.free();}
      }
      if (c.spec.kerning_method.method==='typefacet' && c.spec.kerning_method.minimum_distance_em===undefined) {
        const explicit=font.render({...c.spec,kerning_method:{...c.spec.kerning_method,
          minimum_distance_em:0,max_x_extrema_overlap_em:.1}});
        try {
          assert.equal(hash(output.pixels()),hash(explicit.pixels()),`${c.id} legacy TypeFacet defaults`);
          assert.deepEqual(output.layout(),explicit.layout(),`${c.id} legacy TypeFacet layout`);
        } finally {explicit.free();}
      }
      rendered++;
    } finally {output.free();}
    if (c.export_request) {
      assert.equal(reference.export_error,null,`${c.id}: ${reference.export_error}`);
      assert.equal(hash(font.export_playdate(c.export_request)),reference.export_sha256,`${c.id} export`);
      exported++;
    }
  }
  const font=fonts.values().next().value, spec=cases[0].spec;
  for (const kerning_method of [{method:'unknown'},{method:'source',strength:1},{method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,foreign:1},
    {method:'typefacet',normal_distance_em:NaN,intrusion_tolerance_em:0},{method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:-1},
    {method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,minimum_distance_em:-.01},
    {method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,minimum_distance_em:.101},
    {method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,minimum_distance_em:NaN},
    {method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,max_x_extrema_overlap_em:-.01},
    {method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,max_x_extrema_overlap_em:.501},
    {method:'typefacet',normal_distance_em:.1,intrusion_tolerance_em:.1,max_x_extrema_overlap_em:Infinity},
    {method:'hu_hersch',strength:0},{method:'hu_hersch',strength:.35},{method:'hu_hersch',strength:1},
    {method:'hu_hersch',strength:NaN},{method:'hu_hersch',strength:Infinity},
    {method:'hu_hersch',strength:-.1},{method:'hu_hersch',strength:1.1},
    {method:'hu_hersch',strength:null},{method:'hu_hersch',strength:'0.5'},{method:'hu_hersch',strength:1,foreign:1},
    {method:'fontforge',strength:0},{method:'fontforge',strength:1},{method:'fontforge',strength:null},
    {method:'fontforge',strength:'1'},{method:'fontforge',strength:1,foreign:1},
    {method:'fontforge',strength:NaN},{method:'fontforge',strength:-.1},{method:'fontforge',strength:1.1}]) {
    assert.throws(()=>font.render({...spec,text:'',kerning_method}));
    assert.throws(()=>font.export_playdate({config:{characters:'ca',size_px:16,output_bits:1},pipeline:spec.pipeline,kerning_method}));
  }
  assert.throws(()=>font.render({...spec,text:'',pipeline:undefined,renderer:'candidate'}));
  const report={status:'passed',exactNativeWasmCases:rendered,exactNativeWasmExports:exported,
    methods:['source','typefacet','hu_hersch','fontforge'],fonts:4,sizes:[12,16,20],outputBits:[1,2,3,4],
    typefacetSettings:new Set(cases.filter(c=>c.spec.kerning_method.method==='typefacet').map(c=>JSON.stringify(c.spec.kerning_method))).size,
    typefacetExtraControls:true,legacyTypefacetDefaultsIdentical:true,huDepthEndpoints:['default','explicit'],
    retiredStrengthRejected:true,tracking:[0,1],decimalTieCase:true,
    invalidRequestsRejected:true,nativeReferenceMs,wasmTotalMs:performance.now()-started,
    wasmPackage:relative(root,wasmPackage),
    wasmSha256:hash(readFileSync(resolve(wasmPackage,'font_wasm_bg.wasm'))),
    methodCoverage:Object.fromEntries(['source','typefacet','hu_hersch','fontforge'].map(method=>{
      const selected=cases.filter(c=>c.spec.kerning_method.method===method);
      return [method,{cases:selected.length,
        sizes:[...new Set(selected.map(c=>c.spec.size_px))].sort((a,b)=>a-b),
        outputBits:[...new Set(selected.map(c=>c.spec.output_bits))].sort(),
      }];
    })),
  };
  const output=resolve(root,'out/diagnostics/contextual-spacing/interchangeable-kerning');
  const reportName=basename(wasmPackage)==='pkg-nodejs-preview' ? 'native-wasm-parity.json' : `native-wasm-parity-${basename(wasmPackage)}.json`;
  mkdirSync(output,{recursive:true});writeFileSync(resolve(output,reportName),JSON.stringify(report,null,2)+'\n');
  console.log(report);
} finally {for (const font of fonts.values()) font.free();}
