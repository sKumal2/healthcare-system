"use client";

import Link from "next/link";
import { Search } from "lucide-react";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { timeAgo } from "@/lib/queryHelpers";
import type { QueryHistoryItem } from "@/hooks/useQueryHistory";

interface QueryHistoryListProps {
  queries: QueryHistoryItem[];
  isLoading: boolean;
  onSelect: (queryId: string) => void;
}

function SkeletonItem() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-200 bg-white p-4">
      <div className="h-4 w-3/4 rounded bg-slate-200 mb-2" />
      <div className="h-3 w-full rounded bg-slate-200 mb-1" />
      <div className="h-3 w-2/3 rounded bg-slate-200 mb-3" />
      <div className="flex gap-2">
        <div className="h-5 w-16 rounded-full bg-slate-200" />
        <div className="h-5 w-20 rounded bg-slate-200" />
      </div>
    </div>
  );
}

export function QueryHistoryList({ queries, isLoading, onSelect }: QueryHistoryListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonItem key={i} />
        ))}
      </div>
    );
  }

  if (queries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-slate-400">
        <Search className="h-10 w-10" />
        <p className="text-sm font-medium">No questions asked yet</p>
        <Link href="/query" className="text-sm text-blue-600 hover:underline">
          Ask your first question →
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {queries.map((item) => (
        <button
          key={item.query_id}
          type="button"
          onClick={() => onSelect(item.query_id)}
          className="w-full text-left bg-white rounded-xl border border-slate-200 p-4 hover:shadow-sm cursor-pointer transition-shadow"
        >
          <p className="text-sm font-medium text-slate-800 line-clamp-2">{item.question}</p>
          <p className="mt-1 text-xs text-slate-500 line-clamp-2">{item.answer}</p>
          <div className="mt-3 flex items-center gap-2">
            <ConfidenceBadge score={item.confidence_score} />
            <span className="text-xs text-slate-400">{timeAgo(item.created_at)}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
