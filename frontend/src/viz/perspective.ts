import SERVER_WASM from "@perspective-dev/server/dist/wasm/perspective-server.wasm?url";
import SERVER64_WASM from "@perspective-dev/server/dist/wasm/perspective-server.memory64.wasm?url";
import CLIENT_WASM from "@perspective-dev/viewer/dist/wasm/perspective-viewer.wasm?url";
import type * as psp from "@perspective-dev/client";

/* Perspective's bootstrap, as the viz spike verified it (.spikes/viz/
   SPIKE-REPORT.md, 2026-11-25). Three rules from the spike are load-bearing:

   1. The wasm binaries MUST be imported with `?url` — a bare `.wasm` import
      under Vite is the instantiated module, not a URL, and fetch()ing it
      fails at runtime.
   2. server32/server64 are registered as THUNKS, so only the binary the
      browser actually supports is ever downloaded; a single `server`
      registration silently caps the engine heap at 4 GB.
   3. The datagrid/charts plugins are separate packages, registered by
      side-effect import.

   This module is never imported statically: the components that need it
   `await import("./perspective.ts")` it, so the ~1 MB of Perspective JS glue
   and the wasm assets stay out of the app's main chunk. The wasm files are
   fetched only when the browser actually boots the engine.

   The whole bootstrap sits behind ONE module-level promise, which is what
   makes it idempotent: React StrictMode double-mounts effects, and two
   blotters on one page must share the engine, not race to init() it twice
   (init() throws on a second call). */
let boot: Promise<psp.Client> | null = null;

async function bootstrap(): Promise<psp.Client> {
  // `await import()` on literal paths on purpose, and WHY it is the exception:
  // static imports here would be hoisted into whichever chunk first touches
  // this module, dragging the full Perspective JS glue into that chunk at
  // evaluation time. The dynamic import IS the code-splitting boundary — Vite
  // emits these as separate lazy chunks fetched only when the first blotter
  // actually mounts. The specifiers are static literals, so types and
  // tree-shaking still apply.
  const [{ default: perspective }, { default: perspective_viewer }] = await Promise.all([
    import("@perspective-dev/client"),
    import("@perspective-dev/viewer"),
    // Side-effect imports: registering the render plugins with the viewer.
    import("@perspective-dev/viewer-datagrid"),
    import("@perspective-dev/viewer-charts"),
    // Theme tokens. The themes use light-dark(), so the viewer follows the OS
    // scheme on its own — the spike verified white-in-light is correct.
    import("@perspective-dev/viewer/dist/css/themes.css"),
  ]);
  await perspective_viewer.init({
    server32: () => fetch(SERVER_WASM),
    server64: () => fetch(SERVER64_WASM),
    viewer: fetch(CLIENT_WASM),
  });
  return perspective.worker();
}

/** The one engine worker for the page, booted on first use. */
export function getPerspectiveClient(): Promise<psp.Client> {
  if (!boot) boot = bootstrap();
  return boot;
}
