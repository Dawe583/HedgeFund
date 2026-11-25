/* The tsx seam for node --test: Node's type stripping covers .ts but refuses
   .tsx, and the render tests mount real components. esbuild transforms each
   .tsx module once at load — JSX becomes createElement, types vanish — and
   Node executes plain ESM. Test-only: production code is bundled by Vite,
   never sees this hook. Also handles the `?url` wasm imports the perspective
   bootstrap uses, which mean nothing outside Vite. */

import { transformSync } from "esbuild";
import { readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

export async function resolve(specifier, context, nextResolve) {
  if (specifier.endsWith("?url")) {
    // A ?url import under Vite yields the asset's served URL. In tests the
    // wasm never actually boots (jsdom lacks the browser APIs perspective's
    // engine needs) — what matters is a URL fetch() can parse and resolve,
    // so the boot promise fails or succeeds on its own merits rather than
    // crashing on a malformed specifier.
    return {
      url: "data:text/javascript,export default " + JSON.stringify("data:application/wasm;base64,"),
      shortCircuit: true,
    };
  }
  try {
    return await nextResolve(specifier, context);
  } catch (e) {
    // TypeScript sources import each other extensionless ("./client.ts" is
    // written as "./client" in some files): try the TS suffixes before
    // giving up — the same lenience tsconfig's moduleResolution gives them.
    if (e && e.code === "ERR_MODULE_NOT_FOUND" && specifier.startsWith(".")) {
      for (const ext of [".ts", ".tsx", "/index.ts", "/index.tsx"]) {
        try {
          return await nextResolve(specifier + ext, context);
        } catch {
          /* try the next extension */
        }
      }
    }
    throw e;
  }
}

export async function load(url, context, nextLoad) {
  if (url.endsWith(".css")) {
    // Styles mean nothing in jsdom — the viewer's theme import resolves to an
    // empty module rather than crashing the loader.
    return { format: "module", source: "export default {};", shortCircuit: true };
  }
  if (url.startsWith("data:")) {
    return nextLoad(url, { ...context, format: "module" });
  }
  if (url.endsWith(".tsx") && url.startsWith("file:")) {
    const source = await readFile(fileURLToPath(url), "utf8");
    const { code } = transformSync(source, {
      loader: "tsx",
      jsx: "automatic",
      format: "esm",
      target: "es2022",
      sourcemap: "inline",
      sourcefile: url,
    });
    return { format: "module", source: code, shortCircuit: true };
  }
  return nextLoad(url, context);
}
