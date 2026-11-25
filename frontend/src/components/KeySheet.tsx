import { useEffect, useRef } from "react";
import { KEY_SHEET } from "./hotkeys";

/* The key sheet — how the terminal documents itself. One floating panel,
   summoned by `?` or the status line's kbd, dismissed by Escape, `?` again,
   or a press outside. The rows come from hotkeys.ts's KEY_SHEET, the same
   table the wiring and the tests read: the documentation cannot drift from
   the behaviour because there is only one list.

   Rendered as a fixed overlay rather than a popover: it is not attached to
   the control that opened it (three different things open it), it is attached
   to the frame. Focus goes to the panel when it opens and back to the body
   when it closes, so Escape always lands somewhere sane. */
export function KeySheet({ onClose }: { onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
    function onPointer(e: PointerEvent) {
      if (panelRef.current && e.target instanceof Node && !panelRef.current.contains(e.target)) {
        onClose();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [onClose]);

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label="Keyboard sheet"
      tabIndex={-1}
      className="fixed bottom-10 right-4 z-30 w-[26rem] max-w-[calc(100vw-2rem)] border border-rule bg-surface shadow-lg outline-none"
    >
      <div className="border-b border-hair px-3 py-1.5 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-ink-faint">
        Keys — dead while typing
      </div>
      <table className="w-full border-collapse text-xs">
        <tbody>
          {KEY_SHEET.map((row) => (
            <tr key={row.keys} className="border-b border-hair last:border-b-0">
              <td className="w-20 whitespace-nowrap px-3 py-1.5 align-top">
                <kbd className="border border-rule px-1 text-ink">{row.keys}</kbd>
              </td>
              <td className="px-3 py-1.5 text-ink-soft">{row.does}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
