/* The terminal's keyboard layer, argued with directly (hotkeys.ts).

   What these tests pin is the GUARD more than the keys: a hotkey that fires
   while someone types is worse than no hotkey, so the typing rule gets the
   most rows. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { KEY_SHEET, SECTION_KEYS, readHotkey } from "../src/components/hotkeys.ts";

// A stand-in for an element: readHotkey's guard is structural — it only
// asks tagName, isContentEditable and closest — so a plain object wearing
// them exercises the real logic, and no DOM needs to exist for it.
function el({
  tag = "DIV",
  editable = false,
  inViewer = false,
}: {
  tag?: string;
  editable?: boolean;
  inViewer?: boolean;
} = {}): { tagName: string; isContentEditable: boolean; closest: (sel: string) => unknown } {
  const fake = {
    tagName: tag,
    isContentEditable: editable,
    closest: (sel: string) => (sel === "perspective-viewer" && inViewer ? fake : null),
  };
  return fake;
}

test("the digit keys reach the sections in the strip's order", () => {
  for (const [i, section] of SECTION_KEYS.entries()) {
    const hot = readHotkey(String(i + 1), el(), false, false, false);
    assert.deepEqual(hot, { kind: "section", index: i + 1 }, `${i + 1} should reach ${section}`);
  }
  assert.equal(SECTION_KEYS[0], "dashboard");
  assert.equal(SECTION_KEYS[2], "trading");
});

test("digits beyond the sections are not ours", () => {
  assert.equal(readHotkey(String(SECTION_KEYS.length + 1), el(), false, false, false), null);
  assert.equal(readHotkey("0", el(), false, false, false), null);
});

test("the question mark toggles the sheet, escape closes it", () => {
  assert.deepEqual(readHotkey("?", el(), false, false, false), { kind: "sheet" });
  assert.deepEqual(readHotkey("Escape", el(), false, false, false), { kind: "escape" });
});

test("escape still reads inside an input — closing is never trapped", () => {
  assert.deepEqual(readHotkey("Escape", el({ tag: "INPUT" }), false, false, false), { kind: "escape" });
});

test("every other key is dead while typing — input, textarea, select, contenteditable", () => {
  for (const target of [
    el({ tag: "INPUT" }),
    el({ tag: "TEXTAREA" }),
    el({ tag: "SELECT" }),
    el({ editable: true }),
  ]) {
    assert.equal(readHotkey("3", target, false, false, false), null, `digit inside ${target.tagName}`);
    assert.equal(readHotkey("?", target, false, false, false), null, `question inside ${target.tagName}`);
  }
});

test("the blotter grid owns its own arrows and keys", () => {
  assert.equal(readHotkey("3", el({ inViewer: true }), false, false, false), null);
});

test("modifier chords are never ours — the browser's and the OS's keys stay theirs", () => {
  for (const [ctrl, meta, alt] of [
    [true, false, false],
    [false, true, false],
    [false, false, true],
  ]) {
    assert.equal(readHotkey("3", el(), ctrl, meta, alt), null);
    assert.equal(readHotkey("?", el(), ctrl, meta, alt), null);
  }
});

test("a non-element target (the document itself) does not crash the guard", () => {
  assert.deepEqual(readHotkey("1", null, false, false, false), { kind: "section", index: 1 });
});

test("the key sheet documents the sections the wiring binds, and the research table's rows", () => {
  const sheet = KEY_SHEET.map((r) => r.keys + " " + r.does).join("\n");
  for (const section of SECTION_KEYS) {
    assert.ok(
      sheet.toLowerCase().includes(section),
      `the sheet never mentions ${section} — documentation drifted from the wiring`,
    );
  }
  assert.ok(sheet.includes("Enter"), "the sheet never documents the detail key");
});
