import type { Components } from "react-markdown";

// How a model's Markdown is drawn — Tailwind classes per element, no typography
// plugin. It lived in Advisor.tsx, which was a page; it is here now because it
// was never that page's, and the two things that render prose in this app are
// the chat panel and the analysis reader.
export const mdComponents: Components = {
  h1: ({ node: _n, ...p }) => <h1 className="mb-3 mt-2 text-xl font-semibold text-ink" {...p} />,
  h2: ({ node: _n, ...p }) => <h2 className="mb-2 mt-6 border-b border-hair pb-1 text-lg font-semibold text-ink" {...p} />,
  h3: ({ node: _n, ...p }) => <h3 className="mb-1.5 mt-4 text-base font-semibold text-ink" {...p} />,
  p: ({ node: _n, ...p }) => <p className="my-2" {...p} />,
  ul: ({ node: _n, ...p }) => <ul className="my-2 list-disc space-y-1 pl-5" {...p} />,
  ol: ({ node: _n, ...p }) => <ol className="my-2 list-decimal space-y-1 pl-5" {...p} />,
  strong: ({ node: _n, ...p }) => <strong className="font-semibold text-ink" {...p} />,
  a: ({ node: _n, ...p }) => <a className="text-olive underline" target="_blank" rel="noreferrer" {...p} />,
  blockquote: ({ node: _n, ...p }) => (
    <blockquote className="my-3 rounded-r-lg border-l-4 border-warn bg-warn-tint px-3 py-2 text-ink" {...p} />
  ),
  code: ({ node: _n, ...p }) => <code className="rounded bg-tint px-1 py-0.5 font-mono text-[13px]" {...p} />,
  pre: ({ node: _n, ...p }) => (
    <pre className="my-3 overflow-x-auto rounded-sm border border-hair bg-tint p-3 font-mono text-xs text-ink [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-ink" {...p} />
  ),
  hr: ({ node: _n, ...p }) => <hr className="my-4 border-rule" {...p} />,
  table: ({ node: _n, ...p }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs" {...p} />
    </div>
  ),
  th: ({ node: _n, ...p }) => <th className="border-b border-rule py-1.5 pr-4 font-semibold text-ink" {...p} />,
  td: ({ node: _n, ...p }) => <td className="border-b border-hair py-1.5 pr-4 align-top" {...p} />,
};
