import { FileText } from "lucide-react";
import type { ChatSource } from "@/lib/types";
import { relevanceBadgeClass, relevanceLabel } from "@/lib/ai";

type AiSourceListProps = {
  sources: ChatSource[];
  title?: string;
};

/** Numbered, expandable document sources with relevance indicators. */
export function AiSourceList({ sources, title = "Sources" }: AiSourceListProps) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-6 border-t border-slate-100 pt-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="ui-label">{title}</h3>
        <span className="text-[11px] text-slate-400">
          {sources.length} document{sources.length !== 1 ? "s" : ""} referenced
        </span>
      </div>
      <ol className="space-y-2">
        {sources.map((src, i) => {
          const ref = src.ref ?? i + 1;
          const confidence = relevanceLabel(src.relevance);
          return (
            <li key={`${ref}-${src.client_name}-${i}`} id={`source-${ref}`} className="scroll-mt-4">
              <details className="group rounded-xl border border-slate-200 bg-slate-50/60 transition-shadow open:shadow-xs">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs font-medium text-slate-950">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-brand-100 text-[10px] font-bold text-brand-800">
                    {ref}
                  </span>
                  <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
                  <span className="min-w-0 truncate">{src.client_name}</span>
                  {src.doc_type && (
                    <span className="hidden truncate text-slate-500 sm:inline">({src.doc_type})</span>
                  )}
                  {confidence && (
                    <span
                      className={`ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${relevanceBadgeClass(confidence)}`}
                      title={`Document relevance: ${src.relevance?.toFixed(2)}`}
                    >
                      {confidence} match
                    </span>
                  )}
                  {src.date && (
                    <span className="shrink-0 text-slate-400">{src.date}</span>
                  )}
                </summary>
                <p className="border-t border-slate-100 px-3 py-2.5 text-xs leading-relaxed text-slate-600">
                  {src.content}
                </p>
              </details>
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-[11px] text-slate-400">
        Click citation numbers in the answer to jump to the matching source.
      </p>
    </div>
  );
}
