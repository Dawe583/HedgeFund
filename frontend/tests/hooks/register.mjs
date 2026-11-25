/* Registers the tsx loader before the test files load — the entry point for
   node's --import flag in the test script. */
import { register } from "node:module";
register("./tsx-loader.mjs", import.meta.url);
