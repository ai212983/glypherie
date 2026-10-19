import * as React from "react";
import {
  filterKerningPairs,
  formatKerningAdjustment,
  kerningQueryKey,
  pairCodepoints,
  type KerningPairView,
} from "./kerning";
import { useRenderer } from "../../renderer/renderer-context.js";

interface KerningPanelProps {
  ready: boolean;
  fontId: string;
  fontName: string;
  sizePx: number;
  axes: Record<string, number>;
  open: boolean;
  filter: string;
  onToggle: (open: boolean) => void;
  onFilter: (value: string) => void;
}

interface CachedTable {
  pairs: KerningPairView[];
  skipped: number;
}

export function KerningPanel(props: KerningPanelProps): React.JSX.Element {
  const { ready, fontId, fontName, sizePx, axes, open, filter, onToggle, onFilter } = props;
  const { service, session, available } = useRenderer();
  const runnable = ready && service !== null && available === true;
  const cacheRef = React.useRef(new Map<string, CachedTable>());
  const [pairs, setPairs] = React.useState<KerningPairView[] | null>(null);
  const [skipped, setSkipped] = React.useState(0);
  const [status, setStatus] = React.useState("");
  const [shownFont, setShownFont] = React.useState(fontId);
  if (shownFont !== fontId) {
    setShownFont(fontId);
    setPairs(null);
    setSkipped(0);
    setStatus(open ? "Loading kerning pairs…" : "");
  }

  React.useEffect(() => {
    if (!open) return;
    // The renderer session joins the key so a recreated worker never serves
    // pairs cached for a different worker.
    const key = `${session} ${kerningQueryKey(fontId, sizePx, axes)}`;
    const cached = cacheRef.current.get(key);
    if (cached) {
      setPairs(cached.pairs);
      setSkipped(cached.skipped);
      setStatus(cached.pairs.length === 0
        ? `No nonzero pairs in this ASCII subset at this size and axes.${cached.skipped ? "" : ""}`.trim()
        : "");
      return;
    }
    setPairs(null);
    setSkipped(0);
    setStatus("Loading kerning pairs…");
    let cancelled = false;
    const renderer = runnable ? service : null;
    const timer = window.setTimeout(() => {
      if (!renderer) {
        if (!cancelled) setStatus("Source kerning data is unavailable for this font.");
        return;
      }
      renderer.kerning(fontId, sizePx, axes).then((data) => {
        if (cancelled) return;
        const table = Array.isArray(data)
          ? { pairs: data as KerningPairView[], skipped_pairs: 0 }
          : data as { pairs: KerningPairView[]; skipped_pairs: number };
        if (!table || !Array.isArray(table.pairs)) throw new Error("Invalid kerning data.");
        const entry = { pairs: table.pairs, skipped: Number(table.skipped_pairs) || 0 };
        if (cacheRef.current.size >= 16) {
          const oldest = cacheRef.current.keys().next().value;
          if (oldest !== undefined) cacheRef.current.delete(oldest);
        }
        cacheRef.current.set(key, entry);
        setPairs(entry.pairs);
        setSkipped(entry.skipped);
        setStatus("");
      }).catch((error: unknown) => {
        if (cancelled) return;
        setPairs(null);
        setSkipped(0);
        const message = error instanceof Error ? error.message : String(error ?? "");
        setStatus(/reload the page/i.test(message)
          ? message
          : /unavailable/i.test(message)
            ? "Source kerning data is unavailable for this font."
            : `Kerning data error: ${message}`);
      });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, runnable, service, session, fontId, sizePx, axes]);

  const visible = pairs ? filterKerningPairs(pairs, filter) : [];
  const omissions = skipped === 1
    ? "1 pair needs text-run positioning and is not listed."
    : skipped > 1 ? `${skipped} pairs need text-run positioning and are not listed.` : "";
  const count = pairs ? (pairs.length === 1 ? "(1 pair)" : `(${pairs.length} pairs)`) : "";

  let listStatus = status;
  if (!status && pairs) {
    if (pairs.length === 0) listStatus = `No nonzero pairs in this ASCII subset at this size and axes. ${omissions}`.trim();
    else if (visible.length === 0) listStatus = `No pairs match the current filter. ${omissions}`.trim();
    else listStatus = omissions;
  }

  return (
    <details
      className="font-kerning m-0 mb-6 text-[.8rem] leading-normal"
      open={open}
      onToggle={(event) => onToggle((event.target as HTMLDetailsElement).open)}
    >
      <summary>Kerning pairs <span data-kerning-count>{count}</span></summary>
      <p className="font-kerning-scope m-0 mt-2 text-soft">
        Printable ASCII pairs at the selected size and axes. Values show the font’s adjustment in pixels.
      </p>
      <label className="font-kerning-filter mt-[.6rem] flex max-w-64 flex-col gap-[.35rem]">
        Filter pairs
        <input
          type="search"
          data-kerning-filter
          maxLength={8}
          autoComplete="off"
          spellCheck={false}
          placeholder="e.g. AV"
          aria-label={`Filter kerning pairs for ${fontName}`}
          value={filter}
          onChange={(event) => onFilter(event.target.value)}
        />
      </label>
      <p className="font-kerning-status m-0 mt-2 text-soft empty:hidden" data-kerning-status role="status">
        {listStatus}
      </p>
      <ul
        className="font-kerning-list m-0 mt-[.6rem] grid max-h-64 list-none grid-cols-[repeat(auto-fill,minmax(min(100%,11rem),1fr))] gap-x-6 gap-y-[.35rem] overflow-auto pt-0 pr-2 pb-0 pl-0 tabular-nums"
        data-kerning-list
        aria-label={`${fontName} kerning pairs`}
        tabIndex={0}
      >
        {visible.map((pair) => (
          <li key={`${pair.left}-${pair.right}`} className="flex justify-between wrap-anywhere gap-3">
            <span className="pair font-semibold" title={pairCodepoints(pair.left, pair.right)}>
              {String.fromCodePoint(pair.left, pair.right).replaceAll(" ", "␠")}
            </span>
            {formatKerningAdjustment(pair.adjustment_26_6)}
          </li>
        ))}
      </ul>
    </details>
  );
}
