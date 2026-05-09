import { BookOpen, CircleAlert } from "lucide-react";
import { SourceCard } from "./SourceCard";
import type { SourceMetadata } from "@/types";

interface SourceListProps {
  sources: SourceMetadata[];
  isLoading?: boolean;
}

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 animate-pulse">
      <div className="flex gap-2 mb-2">
        <div className="h-6 w-6 rounded-full bg-slate-200" />
        <div className="h-5 w-24 rounded-full bg-slate-200" />
      </div>
      <div className="h-4 w-full rounded bg-slate-200 mb-2" />
      <div className="h-4 w-3/4 rounded bg-slate-200 mb-2" />
      <div className="h-3 w-20 rounded bg-slate-200" />
    </div>
  );
}

export function SourceList({ sources, isLoading }: SourceListProps) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <BookOpen className="h-4 w-4 text-slate-500" />
        <span className="text-sm font-semibold text-slate-700">Sources</span>
        {!isLoading && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {sources.length}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : sources.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <CircleAlert className="h-4 w-4" />
          No verified sources found
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {sources.map((source, i) => (
            <SourceCard key={source.document_id} source={source} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
