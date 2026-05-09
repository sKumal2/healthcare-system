"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { QueryHistoryList } from "@/components/query/QueryHistoryList";
import { useQueryHistory } from "@/hooks/useQueryHistory";

export default function HistoryPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQueryHistory(page);

  const items = data?.items ?? [];
  const hasMore = items.length === 20;

  function handleSelect(queryId: string) {
    router.push(`/query?id=${queryId}`);
  }

  return (
    <PageWrapper
      title="Question History"
      subtitle="Your past healthcare questions"
    >
      <QueryHistoryList queries={items} isLoading={isLoading} onSelect={handleSelect} />

      {!isLoading && items.length > 0 && (
        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
            Prev
          </button>
          <span className="text-sm text-slate-500">Page {page}</span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasMore}
            className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </PageWrapper>
  );
}
