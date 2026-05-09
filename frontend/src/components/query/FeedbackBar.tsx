"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown, Star } from "lucide-react";
import { useSubmitFeedback } from "@/hooks/useQueryHistory";

interface FeedbackBarProps {
  queryId: string;
}

export function FeedbackBar({ queryId }: FeedbackBarProps) {
  const [selected, setSelected] = useState<"helpful" | "not_helpful" | null>(null);
  const [rating, setRating] = useState<number>(0);
  const [submitted, setSubmitted] = useState(false);
  const { mutate: submitFeedback } = useSubmitFeedback();

  function handleVote(type: "helpful" | "not_helpful") {
    if (submitted) return;
    setSelected(type);
  }

  function handleStar(star: number) {
    if (submitted) return;
    setRating(star);
  }

  function handleSubmit() {
    if (submitted || !selected) return;
    submitFeedback(
      { queryId, feedbackType: selected, rating: rating || undefined },
      {
        onSettled: () => setSubmitted(true),
      }
    );
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="border-t border-slate-100 pt-4 mt-4">
        <span className="text-xs text-slate-500">Thank you for your feedback! ✓</span>
      </div>
    );
  }

  return (
    <div className="border-t border-slate-100 pt-4 mt-4 flex flex-wrap items-center gap-3">
      <span className="text-xs text-slate-500">Was this helpful?</span>

      <button
        type="button"
        onClick={() => handleVote("helpful")}
        className={`flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
          selected === "helpful"
            ? "bg-green-50 text-green-600 border-green-200"
            : "border-slate-200 text-slate-600 hover:bg-green-50 hover:text-green-600 hover:border-green-200"
        }`}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
        Yes
      </button>

      <button
        type="button"
        onClick={() => handleVote("not_helpful")}
        className={`flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
          selected === "not_helpful"
            ? "bg-red-50 text-red-600 border-red-200"
            : "border-slate-200 text-slate-600 hover:bg-red-50 hover:text-red-600 hover:border-red-200"
        }`}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
        No
      </button>

      <div className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => handleStar(star)}
            className="p-0.5 transition-colors"
            aria-label={`Rate ${star} star`}
          >
            <Star
              className={`h-4 w-4 ${
                star <= rating ? "fill-amber-400 text-amber-400" : "text-slate-300"
              }`}
            />
          </button>
        ))}
      </div>

      {(selected || rating > 0) && (
        <button
          type="button"
          onClick={handleSubmit}
          className="ml-auto text-xs text-blue-600 hover:underline"
        >
          Submit
        </button>
      )}
    </div>
  );
}
