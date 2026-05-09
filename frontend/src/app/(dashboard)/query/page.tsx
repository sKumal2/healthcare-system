"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { QuestionInput } from "@/components/query/QuestionInput";
import { AnswerCard } from "@/components/query/AnswerCard";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useQuery } from "@/hooks/useQuery";
import { useQueryDetail } from "@/hooks/useQueryHistory";

function QueryPageContent() {
  const searchParams = useSearchParams();
  const queryId = searchParams.get("id");

  const { isLoading, result, error, submitQuestion, clearResult, clearError, resetSession } =
    useQuery();

  const { data: detailResult } = useQueryDetail(queryId);

  const displayResult = queryId && detailResult ? detailResult : result;

  function handleNewSession() {
    resetSession();
    clearResult();
  }

  return (
    <PageWrapper
      title="Ask a Question"
      subtitle="Verified by official sources"
      action={
        displayResult ? (
          <button
            type="button"
            onClick={handleNewSession}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            New Session
          </button>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-6">
        {error && (
          <ErrorBanner message={error} onDismiss={clearError} />
        )}

        <QuestionInput onSubmit={submitQuestion} isLoading={isLoading} />

        {(displayResult || isLoading) && (
          <AnswerCard
            result={
              displayResult ?? {
                question: "",
                answer: "",
                sources: [],
                confidence_score: 0,
                query_id: "",
                processing_time_ms: 0,
                disclaimer: "",
                generated_at: "",
              }
            }
            isLoading={isLoading && !displayResult}
          />
        )}
      </div>
    </PageWrapper>
  );
}

export default function QueryPage() {
  return <QueryPageContent />;
}
