import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { PerspectiveViewer } from "@perspective-dev/react";
import type * as psp from "@perspective-dev/client";
import type * as pspViewer from "@perspective-dev/viewer";

/* A blotter: the Perspective datagrid behind one React component, generic
   over the row shape. Used wherever a table is scanned rather than read —
   positions, fills, raw research rows — where grouping and re-sorting live in
   the grid itself instead of being re-implemented per page.

   Perspective is heavy (the spike measured ~1 MB of JS glue plus the wasm
   engine), so NOTHING here loads it eagerly: the client arrives lazily
   through ./perspective.ts's dynamic imports, which are this app's
   code-splitting boundary. The wrapper only deals in the client it is handed.
   And an EMPTY blotter boots nothing at all — the engine is megabytes of
   memory for exactly zero rows, so the empty state is a sentence, rendered
   before any import happens.

   StrictMode discipline: effects run mount → cleanup → mount, and both runs
   resolve the SAME singleton client promise. Table names are unique per
   component instance (the counter), so the first mount's async work finishing
   after its cleanup cannot collide with the second mount's table; each run
   deletes the table it created. Engine memory is real memory — a table left
   undeleted leaks wasm heap. */

// Row type: what perspective tables accept — plain JSON-shaped records.
export type BlotterRow = Record<string, string | number | boolean | null>;

let nextTableId = 0;

export function Blotter({
  rows,
  columns,
  groupBy = [],
  height = 360,
  empty,
}: {
  rows: BlotterRow[];
  /** Which columns the grid shows, in order. */
  columns: string[];
  groupBy?: string[];
  height?: number;
  /** What an empty blotter says — worded by the caller, because "no trades"
      and "no validation runs yet" are different sentences, and the honest
      sentence is the whole point. */
  empty: ReactNode;
}) {
  const [client, setClient] = useState<psp.Client | null>(null);
  const [ready, setReady] = useState(false);
  const [bootFailed, setBootFailed] = useState(false);
  const tableRef = useRef<psp.Table | null>(null);
  // One table name per component instance. useState's initializer rather than
  // a ref: reading a ref during render is a lint error under the React
  // compiler rules, and useState is exactly "compute once per instance".
  const [name] = useState(() => `blotter-${nextTableId++}`);
  // The host div, so the viewer element's `theme` attribute can follow the
  // app's own theme. The React wrapper forwards no attribute for it, and
  // leaving the grid on Perspective's light-dark() default would follow the
  // OS — wrong for an app whose dark face is a product decision, not the
  // system's.
  const hostRef = useRef<HTMLDivElement | null>(null);

  const rowsEmpty = rows.length === 0;

  // "Pro Dark"/"Pro Light" are Perspective's own dense professional themes —
  // the terminal genre the rest of the page wears, in the grid's own dialect.
  useEffect(() => {
    const paint = () => {
      const viewer = hostRef.current?.querySelector("perspective-viewer");
      if (!viewer) return;
      const dark = document.documentElement.getAttribute("data-theme") !== "light";
      viewer.setAttribute("theme", dark ? "Pro Dark" : "Pro Light");
    };
    paint();
    const observer = new MutationObserver(paint);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [ready]);

  // The engine worker, booted once per page through the lazy module — and
  // only when there is anything to show.
  useEffect(() => {
    if (rowsEmpty) return;
    let alive = true;
    void import("./perspective").then(({ getPerspectiveClient }) =>
      getPerspectiveClient().then(
        (c) => {
          if (alive) setClient(c);
        },
        () => {
          // A failed boot (the wasm unfetchable offline, an engine error) is
          // a fact, not a crash: without this rejection handler the failure
          // is an unhandled promise rejection that poisons the page — and in
          // test environments, the whole run. The blotter says its engine
          // failed instead of spinning "loading" forever.
          if (alive) setBootFailed(true);
        },
      ),
    );
    return () => {
      alive = false;
    };
  }, [rowsEmpty]);

  // The table: created once the client exists and there is something to show,
  // deleted on cleanup — whatever state the async work is in by then.
  useEffect(() => {
    if (!client || rowsEmpty) return;
    let alive = true;
    void client.table(rows, { name }).then((t) => {
      if (!alive) {
        // The cleanup ran first (StrictMode's first mount): the table exists
        // but nobody owns it — delete it here or the heap keeps it forever.
        void t.delete();
        return;
      }
      tableRef.current = t;
      setReady(true);
    });
    return () => {
      alive = false;
      setReady(false);
      const t = tableRef.current;
      tableRef.current = null;
      if (t) void t.delete();
    };
    // rows deliberately absent: the first non-empty load creates the table,
    // later refresh flows through replace() below — tearing the table down
    // per refresh would reset the reader's grouping and scroll every time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, name, rowsEmpty]);

  // Refreshed rows for a live table: replace is the whole-table update,
  // correct at blotter scale (the spike verified live updates through the
  // same machinery).
  useEffect(() => {
    const t = tableRef.current;
    if (!t || rowsEmpty) return;
    void t.replace(rows);
  }, [rows, rowsEmpty]);

  const groupKey = groupBy.join(",");
  const columnKey = columns.join(",");

  // The viewer config is memoized on content: a fresh object identity per
  // render would hand the viewer a "new" config on every parent re-render,
  // resetting the reader's own grouping and scroll — the grid belongs to the
  // reader once drawn.
  const config = useMemo<pspViewer.ViewerConfigUpdate>(
    () => ({
      table: name,
      group_by: groupBy,
      columns,
      plugin: "Datagrid",
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on joined content: groupBy/columns are fresh literals per render at call sites
    [name, groupKey, columnKey],
  );

  if (rowsEmpty) {
    return (
      <div className="flex items-center justify-center text-sm text-ink-soft" style={{ height }}>
        {empty}
      </div>
    );
  }
  if (bootFailed) {
    return (
      <div className="flex items-center justify-center text-sm text-ink-soft" style={{ height }}>
        The grid engine could not start — the rows exist, the viewer does not.
      </div>
    );
  }
  if (!ready || !client) {
    return (
      <div className="flex items-center justify-center text-sm text-ink-soft" style={{ height }}>
        Loading the grid…
      </div>
    );
  }
  return (
    /* `[&_perspective-viewer]:h-full` is load-bearing, not styling: the viewer
       element has no intrinsic height, so without it the grid renders 0px
       tall — present in the DOM, invisible on the page. The spike's CSS did
       the same thing one level up. */
    <div
      ref={hostRef}
      style={{ height }}
      className="overflow-hidden rounded-sm border border-rule bg-surface [&_perspective-viewer]:h-full"
    >
      <PerspectiveViewer client={client} config={config} />
    </div>
  );
}
