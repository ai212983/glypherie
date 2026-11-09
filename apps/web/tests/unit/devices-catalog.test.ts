// cspell:words TEMPERA RLCD Xteink paperwhite Picco BOOX boox
// Device catalog tests: shipped profiles, physical density, shell bounds and
// aspect, strict validation, graceful unknown lookup, and shell/layout math.
import assert from "node:assert/strict";
import test from "node:test";
import {
  DEVICE_CATALOG,
  deviceById,
  deviceLayout,
  loadDeviceCatalog,
  shellUrl,
} from "../../src/app/devices/catalog.ts";

test("shipped catalog carries the four required profiles plus Playdate and Picco", () => {
  assert.equal(DEVICE_CATALOG.version, 1);
  const ids = DEVICE_CATALOG.devices.map((device) => device.id);
  assert.deepEqual(ids, [
    "xteink-x4",
    "xteink-x3",
    "inkplate-4-tempera",
    "waveshare-esp32-s3-rlcd-4-2",
    "playdate",
    "boox-picco",
  ]);
  const byId = new Map(DEVICE_CATALOG.devices.map((device) => [device.id, device]));
  assert.deepEqual(
    [byId.get("xteink-x4")?.widthPx, byId.get("xteink-x4")?.heightPx, byId.get("xteink-x4")?.ppi],
    [480, 800, 220],
  );
  assert.deepEqual(
    [byId.get("xteink-x3")?.widthPx, byId.get("xteink-x3")?.heightPx, byId.get("xteink-x3")?.ppi],
    [528, 792, 259],
  );
  assert.deepEqual([byId.get("inkplate-4-tempera")?.widthPx, byId.get("inkplate-4-tempera")?.heightPx], [600, 600]);
  assert.ok((byId.get("inkplate-4-tempera")?.ppi ?? 0) > 223 && (byId.get("inkplate-4-tempera")?.ppi ?? 0) < 224);
  assert.deepEqual(
    [byId.get("waveshare-esp32-s3-rlcd-4-2")?.widthPx, byId.get("waveshare-esp32-s3-rlcd-4-2")?.heightPx],
    [400, 300],
  );
  assert.ok(
    (byId.get("waveshare-esp32-s3-rlcd-4-2")?.ppi ?? 0) > 119 &&
      (byId.get("waveshare-esp32-s3-rlcd-4-2")?.ppi ?? 0) < 121,
  );
  assert.deepEqual(
    [byId.get("playdate")?.widthPx, byId.get("playdate")?.heightPx, byId.get("playdate")?.ppi],
    [400, 240, 173],
  );
  assert.deepEqual(
    [byId.get("boox-picco")?.widthPx, byId.get("boox-picco")?.heightPx, byId.get("boox-picco")?.ppi],
    [480, 800, 235],
  );
  for (const device of DEVICE_CATALOG.devices) {
    assert.match(device.label, /^\S/);
    assert.ok(device.ppiBasis === "advertised" || device.ppiBasis === "derived");
  }
  assert.equal(byId.get("xteink-x4")?.ppiBasis, "advertised");
  assert.equal(byId.get("xteink-x3")?.ppiBasis, "advertised");
  assert.equal(byId.get("inkplate-4-tempera")?.ppiBasis, "derived");
  assert.equal(byId.get("waveshare-esp32-s3-rlcd-4-2")?.ppiBasis, "derived");
  assert.equal(byId.get("playdate")?.ppiBasis, "advertised");
  assert.equal(byId.get("boox-picco")?.ppiBasis, "advertised");
});

test("every shell aperture matches the native aspect inside its viewBox", () => {
  for (const device of DEVICE_CATALOG.devices) {
    const [vx, vy, vw, vh] = device.shell.viewBox;
    const [sx, sy, sw, sh] = device.shell.screenRect;
    assert.ok(sx >= vx && sy >= vy && sx + sw <= vx + vw && sy + sh <= vy + vh);
    const expected = device.widthPx / device.heightPx;
    assert.ok(Math.abs(sw / sh / expected - 1) < 1e-9, `${device.id} aperture aspect`);
    assert.equal(shellUrl(device), `/devices/${device.shell.src}`, `${device.id} shell resolves beneath the prefix`);
  }
});

test("tempera shell follows the published 83x90 face with a square aperture", () => {
  const tempera = deviceById(DEVICE_CATALOG, "inkplate-4-tempera");
  assert.ok(tempera);
  // Manufacturer nominal "90 x 83 x 24 mm" (both versions) lists dimensions
  // without axis labels; the official front photos show a taller-than-wide
  // face, so 83 mm maps to width and 90 mm to height. viewBox units are
  // 0.1 mm, and the framebuffer/PPI identity stays untouched.
  assert.deepEqual(tempera.shell.viewBox, [0, 0, 830, 900]);
  assert.deepEqual([tempera.widthPx, tempera.heightPx, tempera.ppi], [600, 600, 223.3]);
  const [, , vw, vh] = tempera.shell.viewBox;
  assert.ok(vw < vh, "tempera face is taller than wide");
  assert.ok(Math.abs(vw / vh / (83 / 90) - 1) < 1e-9, "tempera outline matches the 83:90 face");
  const [sx, sy, sw, sh] = tempera.shell.screenRect;
  assert.equal(sw, sh, "tempera aperture stays square");
  assert.equal(sw, 682, "tempera active side stays 68.2 mm nominal (600 px at 223.3 PPI)");
  assert.ok(
    Math.abs(sw / 10 - (600 / tempera.ppi) * 25.4) < 0.1,
    "aperture size stays consistent with the nominal PPI",
  );
  assert.ok(Math.abs(sx - (vw - sw) / 2) < 1e-9, "tempera aperture stays centered horizontally");
  const top = sy - tempera.shell.viewBox[1];
  const chin = tempera.shell.viewBox[1] + vh - (sy + sh);
  assert.ok(top < chin, "tempera aperture sits high with a wider lower chin");
});

test("xteink profiles match the published nominal bodies and advertised densities", () => {
  // External invariants (not catalog copies): instruction-manual/product-page
  // nominal dimensions, diagonal sizes, and advertised PPI.
  const x4 = deviceById(DEVICE_CATALOG, "xteink-x4");
  const x3 = deviceById(DEVICE_CATALOG, "xteink-x3");
  assert.ok(x4 && x3);
  assert.deepEqual([x4.widthPx, x4.heightPx], [480, 800]);
  assert.deepEqual([x3.widthPx, x3.heightPx], [528, 792]);
  // Advertised PPI agrees with the diagonal size within nominal rounding.
  assert.ok(Math.abs(Math.hypot(480, 800) / 4.3 / 220 - 1) < 0.02, "x4 4.3-inch 220 PPI");
  assert.ok(Math.abs(Math.hypot(528, 792) / 3.7 / 259 - 1) < 0.02, "x3 3.7-inch 259 PPI");
  // Nominal body bounds (0.1 mm units) sit inside the full art bounds; the
  // excess is protruding keys/margins, never a resized body.
  assert.equal(x4.shell.viewBox[3], 1140, "x4 art height is the nominal 114 mm body");
  assert.ok(x4.shell.viewBox[2] - 690 <= 10 && x4.shell.viewBox[2] >= 690, "x4 art width is body plus keys");
  assert.ok(x3.shell.viewBox[2] >= 637 && x3.shell.viewBox[3] >= 976, "x3 art contains the 63.7x97.6 mm body");
  assert.ok(x3.shell.viewBox[2] - 637 <= 20 && x3.shell.viewBox[3] - 976 <= 20, "x3 art excess is keys/margins");
});

test("waveshare profile matches the dimension-diagram face and active area", () => {
  // docs.waveshare.com dimension diagram: 92.50 x 69.10 face, 84.80 x 63.60
  // active; vendor listing SKU 33298: 300 x 400 panel presented landscape.
  const ws = deviceById(DEVICE_CATALOG, "waveshare-esp32-s3-rlcd-4-2");
  assert.ok(ws);
  assert.deepEqual([ws.widthPx, ws.heightPx], [400, 300]);
  assert.deepEqual(ws.shell.viewBox, [0, 0, 925, 691]);
  assert.deepEqual([ws.shell.screenRect[2], ws.shell.screenRect[3]], [848, 636]);
  const derived = 400 / (84.8 / 25.4);
  assert.ok(Math.abs(ws.ppi - derived) < 0.05, `waveshare PPI derives from the active area (${derived})`);
});

test("playdate profile matches Panic's screen, bezel, and offset documentation", () => {
  // help.play.date/developer/designing-for-playdate: 400 x 240 at 173 PPI,
  // 3 mm bezel, device center falls at screen x 228, i.e. the screen sits
  // 28 px left of center. Face is 76 x 74 mm.
  const pd = deviceById(DEVICE_CATALOG, "playdate");
  assert.ok(pd);
  assert.deepEqual([pd.widthPx, pd.heightPx, pd.ppi], [400, 240, 173]);
  const [vx, vy, vw, vh] = pd.shell.viewBox;
  assert.ok(vw >= 760 && vh >= 740, "playdate art contains the 76x74 mm face");
  assert.ok(vw - 760 <= 20 && vh - 740 <= 20, "playdate art excess is crank/tab/margins");
  // Artwork body origin is offset (6,10) inside the viewBox (lock tab/crank
  // margins); the 28 px left offset is measured from the body, not the art.
  const bodyLeft = vx + 6;
  const bodyTop = vy + 10;
  const [sx, sy, sw] = pd.shell.screenRect;
  const offsetPx = ((sx + sw / 2 - (bodyLeft + 760 / 2)) / sw) * pd.widthPx;
  assert.ok(Math.abs(offsetPx + 28) < 1, `playdate screen sits 28 px left of center (saw ${offsetPx})`);
  assert.ok(sx - bodyLeft >= 30 && sy - bodyTop >= 30, "playdate bezel keeps Panic's 3 mm minimum");
  assert.ok(Math.abs(sw / 10 / ((400 / pd.ppi) * 25.4) - 1) < 0.01, "playdate aperture matches the 173 PPI size");
});

test("picco profile matches the nominal body and advertised density", () => {
  // Official store lists a 3.97-inch 480 x 800 panel at 235 PPI in a
  // 105.5 x 62 x 5.5 mm body. viewBox units are 0.1 mm; the full art holds
  // the nominal body plus protruding side keys.
  const picco = deviceById(DEVICE_CATALOG, "boox-picco");
  assert.ok(picco);
  assert.deepEqual([picco.widthPx, picco.heightPx], [480, 800]);
  assert.ok(Math.abs(Math.hypot(480, 800) / 3.97 / 235 - 1) < 0.02, "picco 3.97-inch 235 PPI");
  const [vx, vy, vw, vh] = picco.shell.viewBox;
  assert.ok(vw >= 620 && vh >= 1055, "picco art contains the 62x105.5 mm body");
  assert.ok(vw - 620 <= 60 && vh - 1055 <= 60, "picco art excess is keys/margins");
  // Body origin sits inside the art (left/top margins for the side keys);
  // the nominal body bounds stay distinct from the full art bounds.
  const bodyLeft = vx + 20;
  const bodyTop = vy + 10;
  const [sx, sy, sw, sh] = picco.shell.screenRect;
  assert.ok(sx - bodyLeft >= 40 && bodyLeft + 620 - (sx + sw) >= 40, "picco side bezels stay symmetric");
  assert.ok(Math.abs(sw / 10 - (480 / picco.ppi) * 25.4) < 0.1, "picco aperture width matches the 235 PPI size");
  assert.ok(Math.abs(sh / 10 - (800 / picco.ppi) * 25.4) < 0.1, "picco aperture height matches the 235 PPI size");
  const chin = bodyTop + 1055 - (sy + sh);
  assert.ok(sy - bodyTop < chin, "picco aperture sits high with a wider lower chin");
});

test("unknown and malformed ids recover to null without throwing", () => {
  assert.equal(deviceById(DEVICE_CATALOG, "paperwhite"), null);
  assert.equal(deviceById(DEVICE_CATALOG, "toString"), null);
  assert.equal(deviceById(DEVICE_CATALOG, 42), null);
  assert.equal(deviceById(DEVICE_CATALOG, null), null);
  assert.equal(deviceById(DEVICE_CATALOG, undefined), null);
});

test("screen and shell scale together from the aperture", () => {
  const device = deviceById(DEVICE_CATALOG, "xteink-x4");
  assert.ok(device);
  const layout = deviceLayout(device, 0.5);
  assert.equal(layout.screenWidth, 240);
  assert.equal(layout.screenHeight, 400);
  // Aperture 544.8x908 maps 480 device px onto 240 CSS px: one SVG unit is
  // 240/544.8 CSS px, so the 697-unit shell spans 697 * 240/544.8.
  assert.ok(Math.abs(layout.svgWidth - 697 * (240 / 544.8)) < 1e-9);
  assert.ok(Math.abs(layout.svgHeight - 1140 * (240 / 544.8)) < 1e-9);
  assert.ok(Math.abs(layout.screenX - 72.6 * (240 / 544.8)) < 1e-9);
  assert.ok(Math.abs(layout.screenY - 61.9 * (240 / 544.8)) < 1e-9);
  assert.throws(() => deviceLayout(device, 0), /positive/);
  assert.throws(() => deviceLayout(device, Number.NaN), /positive/);
});

test("malformed catalogs fail fast with a reason", () => {
  const base = JSON.parse(JSON.stringify({ version: 1, devices: DEVICE_CATALOG.devices }));
  assert.throws(() => loadDeviceCatalog(null), /catalog object/);
  assert.throws(() => loadDeviceCatalog({ version: 2, devices: [] }), /version 1/);
  assert.throws(() => loadDeviceCatalog({ version: 1, devices: [] }), /non-empty/);
  const dup = structuredClone(base);
  dup.devices.push(structuredClone(dup.devices[0]));
  assert.throws(() => loadDeviceCatalog(dup), /duplicate device/);
  for (const mutate of [
    (entry: Record<string, unknown>) => {
      entry.id = "X4!";
    },
    (entry: Record<string, unknown>) => {
      entry.widthPx = 0;
    },
    (entry: Record<string, unknown>) => {
      entry.heightPx = 5000;
    },
    (entry: Record<string, unknown>) => {
      entry.ppi = 0;
    },
    (entry: Record<string, unknown>) => {
      entry.ppi = Number.NaN;
    },
    (entry: Record<string, unknown>) => {
      entry.ppiBasis = "measured";
    },
    (entry: Record<string, unknown>) => {
      entry.label = "";
    },
  ]) {
    const single = structuredClone(base);
    mutate(single.devices[0]);
    assert.throws(() => loadDeviceCatalog(single), /Invalid device catalog/);
  }
});

test("malformed shells fail fast with a reason", () => {
  const base = { version: 1, devices: [JSON.parse(JSON.stringify(DEVICE_CATALOG.devices[0]))] };
  for (const mutate of [
    (shell: Record<string, unknown>) => {
      shell.src = "/abs/shell.svg";
    },
    (shell: Record<string, unknown>) => {
      shell.src = "../shell.svg";
    },
    (shell: Record<string, unknown>) => {
      shell.src = "shells/shell.png";
    },
    (shell: Record<string, unknown>) => {
      shell.viewBox = [0, 0, 0, 10];
    },
    (shell: Record<string, unknown>) => {
      shell.screenRect = [-5, 0, 10, 10];
    },
    (shell: Record<string, unknown>) => {
      shell.screenRect = [0, 0, 690, 1140];
    },
    (shell: Record<string, unknown>) => {
      shell.screenRect = [60, 100, 570, 570];
    },
  ]) {
    const single = structuredClone(base);
    mutate(single.devices[0].shell);
    assert.throws(() => loadDeviceCatalog(single), /Invalid device catalog/);
  }
});

test("catalog definitions are immutable", () => {
  assert.ok(Object.isFrozen(DEVICE_CATALOG));
  assert.ok(Object.isFrozen(DEVICE_CATALOG.devices));
  for (const device of DEVICE_CATALOG.devices) assert.ok(Object.isFrozen(device));
});
