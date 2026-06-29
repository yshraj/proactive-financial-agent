import { useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import { linkifyCitations, scrollToSource } from "@/lib/ai";
import { isSafeHref } from "@/lib/sanitize";
import { MARKDOWN_PROSE_CLASS, MARKDOWN_PROSE_COMPACT_CLASS } from "@/lib/markdown";

const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });

type AiMarkdownProps = {
  children: string;
  compact?: boolean;
  linkCitations?: boolean;
  className?: string;
};

/** Markdown renderer with optional inline citation anchor links. */
export function AiMarkdown({
  children,
  compact = false,
  linkCitations = true,
  className = "",
}: AiMarkdownProps) {
  const content = useMemo(
    () => (linkCitations ? linkifyCitations(children) : children),
    [children, linkCitations]
  );

  const handleCitationClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.tagName !== "A") return;
    const href = target.getAttribute("href");
    const match = href?.match(/^#source-(\d+)$/);
    if (match) {
      e.preventDefault();
      scrollToSource(Number(match[1]));
    }
  }, []);

  const proseClass = compact ? MARKDOWN_PROSE_COMPACT_CLASS : MARKDOWN_PROSE_CLASS;

  return (
    <div className={`${proseClass} ${className}`} onClick={handleCitationClick}>
      <ReactMarkdown
        components={{
          a: ({ href, children: linkChildren, ...props }) => {
            const isCitation = href?.startsWith("#source-");
            if (isCitation) {
              return (
                <a
                  href={href}
                  {...props}
                  className="mx-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded bg-brand-100 px-1 text-[10px] font-semibold text-brand-800 no-underline hover:bg-brand-200"
                >
                  {linkChildren}
                </a>
              );
            }
            if (!isSafeHref(href)) {
              return <span className="text-brand-700">{linkChildren}</span>;
            }
            return (
              <a
                href={href}
                {...props}
                rel="noopener noreferrer"
                target="_blank"
                className="text-brand-600 underline hover:text-brand-700"
              >
                {linkChildren}
              </a>
            );
          },
          img: () => null,
          strong: ({ children: strongChildren }) => (
            <strong className="font-semibold text-slate-950">{strongChildren}</strong>
          ),
          table: ({ children: tableChildren }) => (
            <div className="my-3 overflow-x-auto rounded-xl border border-slate-200">
              <table className="min-w-full text-left text-sm">{tableChildren}</table>
            </div>
          ),
          th: ({ children: thChildren }) => (
            <th className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700">
              {thChildren}
            </th>
          ),
          td: ({ children: tdChildren }) => (
            <td className="border-b border-slate-100 px-3 py-2 text-slate-700">{tdChildren}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
