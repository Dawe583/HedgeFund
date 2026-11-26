/* The terminal's keyboard layer, as pure decisions — App.tsx wires them to
   the DOM, node --test argues with all of it without one.

   THE KEYS. A terminal is operated, not browsed: the sections are numbered
   in the order the tab strip shows them, and pressing the number goes there
   — one keystroke, no modifier, because this app IS the foreground for its
   reader the way a terminal is for a desk. `?` opens the key sheet, because
   a terminal documents itself; Escape closes it.

   Why digits and not letters: letters type. The sections' initials collide
   with the chat and every form, and a two-key leader sequence (g then t) is
   a habit borrowed from editors, not desks. Digits in plain text are rarer
   than letters in the contexts where the keys are silent anyway — which is
   the guard below, and the guard is the feature: a hotkey that fires while
   someone types is worse than no hotkey.

   THE GUARD. The keys are dead whenever the focus is anywhere text can be
   entered — an input, a textarea, a select, anything contenteditable — and
   inside the blotter grids, whose own keyboard model (arrows between cells)
   belongs to Perspective. What counts is decided here, once, so the app
   shell and the tests share one definition. */

/** True when a keydown happening on `target` must not trigger app hotkeys:
    the focus is somewhere text is entered or a widget owns the arrows.
    Structural, not instanceof — the decision is about what a target IS, and
    asking its shape keeps the logic testable in bare Node, where the DOM's
    classes do not exist. */
export function typingTarget(target: unknown): boolean {
  if (typeof target !== "object" || target === null) return false;
  const el = target as {
    isContentEditable?: boolean;
    tagName?: string;
    closest?: (sel: string) => unknown;
  };
  if (el.isContentEditable === true) return true;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  // The Perspective blotter owns arrows and Enter inside itself; reaching
  // the grid is a deliberate act and its keys stay its own.
  if (typeof el.closest === "function" && el.closest("perspective-viewer")) return true;
  return false;
}

/** The sections the digit keys reach, in the tab strip's own order: the key
    is the position, and the position is printed in the key sheet — the strip
    itself is the documentation. Indexed from 1, as rows of keys are. */
export const SECTION_KEYS = ["dashboard", "portfolio", "trading", "intel", "records", "profile"] as const;
export type SectionKey = (typeof SECTION_KEYS)[number];

/** What a keydown means for the shell. `section` carries the 1-based digit;
    "sheet" toggles the key sheet; "escape" closes it. null: not ours — the
    key is typing, a modifier chord, or nothing the shell binds. */
export type Hotkey =
  | { kind: "section"; index: number }
  | { kind: "sheet" }
  | { kind: "escape" };

export function readHotkey(key: string, target: unknown, ctrl: boolean, meta: boolean, alt: boolean): Hotkey | null {
  if (ctrl || meta || alt) return null;
  if (key === "Escape") return { kind: "escape" };
  if (typingTarget(target)) return null;
  if (key === "?") return { kind: "sheet" };
  if (/^[1-9]$/.test(key)) {
    const index = Number(key);
    if (index <= SECTION_KEYS.length) return { kind: "section", index };
  }
  return null;
}

/* The key sheet's rows, as data: the furniture documents itself from the
   same table the tests read, so the sheet can never drift from the wiring. */
export const KEY_SHEET: { keys: string; does: string }[] = [
  { keys: "1 – 6", does: "Go to a section, in the strip's order: Dashboard, Portfolio, Trading, Intel, Records, Profile" },
  { keys: "?", does: "Open or close this sheet" },
  { keys: "Esc", does: "Close this sheet" },
  { keys: "↑ ↓", does: "Move between runs in the research record, scan the intelligence stream" },
  { keys: "Enter", does: "Open or close a run's detail" },
];
