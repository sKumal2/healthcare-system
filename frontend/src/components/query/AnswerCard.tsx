import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import { DisclaimerBanner } from "./DisclaimerBanner";
import { SourceList } from "./SourceList";
import { FeedbackBar } from "./FeedbackBar";
import { formatProcessingTime, renderSimpleMarkdown } from "@/lib/queryHelpers";
import type { QueryResponse } from "@/types";

interface AnswerCardProps {
  result: QueryResponse;
  isLoading?: boolean;
}

function AnswerSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 w-full rounded bg-slate-200" />
      <div className="h-4 w-5/6 rounded bg-slate-200" />
      <div className="h-4 w-4/5 rounded bg-slate-200" />
      <div className="h-4 w-3/4 rounded bg-slate-200" />
    </div>
  );
}

export function AnswerCard({ result, isLoading }: AnswerCardProps) {
  const processingTime =
    result.processing_time_ms && !isNaN(result.processing_time_ms)
      ? formatProcessingTime(result.processing_time_ms)
      : null;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-lg font-semibold text-slate-800">Answer</span>
        <ConfidenceBadge score={result.confidence_score} showLabel />
        {processingTime && (
          <span className="ml-auto text-xs text-slate-400">{processingTime}</span>
        )}
      </div>

      <div className="border-t border-slate-100 my-4" />

      {isLoading ? (
        <AnswerSkeleton />
      ) : (
        <p
          className="text-sm leading-relaxed text-slate-700 whitespace-pre-wrap"
          dangerouslySetInnerHTML={{ __html: renderSimpleMarkdown(result.answer) }}
        />
      )}

      <div className="mt-4">
        <DisclaimerBanner text={result.disclaimer || undefined} />
      </div>

      <div className="mt-6">
        <SourceList sources={result.sources} isLoading={isLoading} />
      </div>

      <FeedbackBar queryId={result.query_id} />
    </div>
  );
}
