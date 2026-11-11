# Device-canvas rulers

Figma-like top/left pixel rulers around the centered native-resolution device
canvas in the Screen workspace central panel, with synchronized pan/zoom and
scrollbars. No draggable guides were requested.

## Choice

[`@scena/ruler`](https://www.npmjs.com/package/@scena/ruler) `0.20.0`
([daybrush/ruler](https://github.com/daybrush/ruler), MIT), the
framework-agnostic vanilla ruler, with our own small React 19 host
(`apps/web/src/app/features/screen/PixelRuler.tsx`). The older React wrapper
is not a direct dependency; it remains only transitively (see below).

- Construction is `new Ruler(hostElement, options)`; the library appends and
  owns its canvas child, React owns the host div.
- Hot updates paint synchronously through `draw({ scrollPos, zoom, unit })`;
  `scroll(scrollPos)` takes a single argument, so zoom travels through `draw`
  or the documented mutable `zoom` property instead.
- Origin and scale match the viewport exactly: `scrollPos` is in ruler units
  (native device px), `zoom` is the workspace `cssScale`, `negativeRuler`
  draws outside-canvas values, `textFormat` renders integer px labels, and
  explicit `width`/`height` props track the measured scrollport.
- No library observers: `useResizeObserver: false` is passed explicitly and
  the viewport owns resize; structural size/theme/type changes recreate the
  instance while scroll/zoom/unit repaint the current one.
- Runtime dependencies are
  [`croact`](https://www.npmjs.com/package/croact) and
  [`croact-ruler`](https://www.npmjs.com/package/croact-ruler), and
  `croact-ruler` itself wraps the `@scena/react-ruler` painter, so that
  package is still present transitively. No new general ruler layer was
  added; the viewport owner above is the only integration point.

## React 19 proof

A real headless-Chrome harness (React 19.3.1, `StrictMode`) mounted the
actual host, saved as `core-wrapper-smoke.log` in the run evidence
directory: both rulers mount exactly one canvas each, the backing store is
sharpened for the live density, zoom and scroll prop changes repaint, a theme
change recreates the instance with the new background, remount keeps one
canvas per host, and unmount leaves zero canvases with no page errors.

## Pinned destroy defect

The 0.20.0 `destroy()` deterministically throws
`TypeError: Cannot set properties of null (setting '__CROACT__')` and leaves
its canvas behind. Cause, read in the published `dist/ruler.esm.js`: the
constructor keeps the element in a local instead of `this.selfElement` (and
discards the renderer handle), so destroy unmounts `null` and removes
nothing; an enabled resize observer would leak with it
(`core-destroy-probe.log`). The host therefore attempts `destroy()`, contains
only that known `TypeError`, rethrows any other failure after clearing, and
always clears stray host children
(`apps/web/src/app/features/screen/ruler-cleanup.ts`, covered by
`apps/web/tests/unit/ruler-cleanup.test.ts`, including the injected-error
case). No private fields are touched and no new dependency was added.

## Rendering lifecycle

- The painter caches its backing-store scale on first paint; `resize()` does
  not recompute it. Only the ruler instances remount on a density change (via
  the existing live-ratio owner as their React key); the stage never does.
- Ruler colors come from the existing theme owner (`light`/`dark` studio
  tokens); no per-frame style reads. The corner cell names the `px` unit and
  tooltips use the shared hint component; rulers are supplemental visuals,
  not editing surfaces.

## Alternatives (rejected)

- **`@scena/react-guides`**: wraps the ruler and adds draggable guidelines
  via several more runtime dependencies. Correct library, wrong scope:
  guidelines were not requested.
- **Direct `@scena/react-ruler` use**: superseded by the user decision above;
  the vanilla core plus our host owns lifecycle explicitly instead.

## Limitations

- The daybrush ruler repositories are stale (mid-2023) with no upstream
  React 19 statement; the surface used here is small and replaceable, and
  the React 19 behavior above is proven by the saved harness rather than
  inferred from the registry page.
- Ruler tick stepping is fixed `unit`/`segment`; the 1/2/5-adaptive density
  across the device zoom band is computed by the viewport owner.
- Shell-bezel geometry stays single-sourced through `deviceShownLayout`,
  shared by the shell and the viewport, so the ruler origin cannot drift
  from the canvas when the body is shown, hidden, or rotated.

## Sources

- [daybrush/ruler](https://github.com/daybrush/ruler), MIT; vanilla core
  [`packages/ruler/src/Ruler.tsx`](https://github.com/daybrush/ruler/blob/master/packages/ruler/src/Ruler.tsx);
  painter
  [`packages/react-ruler/src/react-ruler/Ruler.tsx`](https://github.com/daybrush/ruler/blob/master/packages/react-ruler/src/react-ruler/Ruler.tsx)
  and
  [`types.ts`](https://github.com/daybrush/ruler/blob/master/packages/react-ruler/src/react-ruler/types.ts).
- [daybrush/guides](https://github.com/daybrush/guides) repository.
- npm registry metadata for `@scena/ruler`, `croact`, and `croact-ruler`.
- Repo integration: `apps/web/src/app/features/screen/CanvasViewport.tsx`,
  `canvas-viewport-geometry.ts`, `SceneWorkspace.tsx` (viewport wiring),
  `apps/web/tests/browser/screen-canvas-rulers.test.ts` (centered-aperture,
  origin, and scrollbar acceptance).
