import { CheckCircle, Clock } from "lucide-react";

interface ProcessingBadgeProps {
  isProcessed: boolean;
  chunksCount: number;
}

export function ProcessingBadge({ isProcessed, chunksCount }: ProcessingBadgeProps) {
  if (isProcessed) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-medium text-green-700">
        <CheckCircle className="h-3.5 w-3.5" />
        Processed · {chunksCount} {chunksCount === 1 ? "chunk" : "chunks"}
      </span>
    );
  }

  return (
    <span className="inline-flex animate-pulse items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
      <Clock className="h-3.5 w-3.5" />
      Processing...
    </span>
  );
}
