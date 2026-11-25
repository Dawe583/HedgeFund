import { useEffect, useState } from "react";
import { getTradingStatus, type TradingStatus } from "../api/trading";
import { engineReading, engineTone } from "./tradingStatus";

/* The frame's bottom line, the furniture real terminals are read by. Four
   facts, all of them real:

   · WHERE you are — a terminal always knows what it is looking at;
   · the ENGINE, as a lamp and a compact readout, polled from the backend
     every 45 seconds — the one piece of furniture that turns this from a
     website with a dark theme into an operations surface. The states are
     tradingStatus.engineReading's own, with the same honesty rule the
     trading page keeps: unreachable is never read as offline. What the
     strip shows is compact by design; the full sentence is the lamp's
     title and the trading page's strip;
   · the local CLOCK, ticking once a second — the one number on the page
     that must never be stale, because it is what says the page itself is
     alive;
   · the key-sheet hint — a terminal documents itself, and a hotkey layer
     nobody can discover is no hotkey layer.

   Nothing coloured except the lamp: colour is information, and the lamp is
   the only information here. */

const POLL_MS = 45_000;

/** The engine state, polled. null means the backend has not answered yet —
    either because the first poll is in flight or because it failed, and the
    lamp reads engineReading(null) as unreachable, which is exactly the
    distinction the type exists to keep. */
function useEngineStatus(): TradingStatus | null {
  const [status, setStatus] = useState<TradingStatus | null>(null);
  useEffect(() => {
    let alive = true;
    const poll = () => {
      getTradingStatus()
        .then((s) => {
          if (alive) setStatus(s);
        })
        .catch(() => {
          if (alive) setStatus(null);
        });
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return status;
}

export function StatusLine({
  section,
  onOpenSheet,
}: {
  section: string;
  onOpenSheet: () => void;
}) {
  const engine = useEngineStatus();
  const reading = engineReading(engine);
  const tone = engineTone(reading);
  const lamp = tone === "up" ? "bg-up" : tone === "warn" ? "bg-warn" : "bg-ink-faint";

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const clock = now.toLocaleTimeString(undefined, { hour12: false });
  const day = now.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <footer className="sticky bottom-0 z-10 mt-auto border-t border-rule bg-surface">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-0.5 px-4 py-1.5 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-ink-soft">
        <span className="text-ink">{section}</span>
        <span className="flex items-center gap-1.5" title={reading.line}>
          <span className={"inline-block h-2 w-2 " + lamp} aria-hidden="true" />
          <span>ENG</span>
          <span className={tone === "warn" ? "text-warn" : tone === "up" ? "text-up" : "text-ink-soft"}>
            {reading.state}
          </span>
        </span>
        <button
          onClick={onOpenSheet}
          className="ml-auto flex items-center gap-1.5 tracking-[0.14em] text-ink-soft transition hover:text-ink"
          aria-label="Show the keyboard sheet"
        >
          <kbd className="border border-rule px-1 text-ink">?</kbd>
          <span className="hidden sm:inline">keys</span>
        </button>
        <span className="tabular-nums">{day}</span>
        <span className="tabular-nums text-ink">{clock}</span>
      </div>
    </footer>
  );
}
