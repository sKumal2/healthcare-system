"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

const EXAMPLE_QUESTIONS = [
  "What are symptoms of Type 2 diabetes?",
  "How does ibuprofen interact with blood thinners?",
  "What is the recommended vaccine schedule for adults?",
];

interface QuestionInputProps {
  onSubmit: (question: string) => void;
  isLoading: boolean;
  disabled?: boolean;
}

export function QuestionInput({ onSubmit, isLoading, disabled }: QuestionInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (trimmed.length >= 10 && !isLoading && !disabled) {
      onSubmit(trimmed);
    }
  }, [value, isLoading, disabled, onSubmit]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  }

  const charCount = value.length;
  const counterColor = charCount > 1800 ? "text-red-500" : "text-slate-400";
  const canSubmit = !isLoading && !disabled && value.trim().length >= 10;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
      <label className="block text-lg font-semibold text-slate-800 mb-3">
        Ask a healthcare question
      </label>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value.slice(0, 2000))}
        onKeyDown={handleKeyDown}
        placeholder="e.g. What are the symptoms of Type 2 diabetes?"
        disabled={isLoading || disabled}
        className="w-full min-h-[120px] max-h-[240px] rounded-xl border border-slate-200 p-4 text-sm text-slate-800 placeholder-slate-400 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-60 disabled:cursor-not-allowed"
      />

      <div className="mt-2 flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setValue(q)}
              className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-full px-3 py-1 cursor-pointer transition-colors"
            >
              {q}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className={`text-xs tabular-nums ${counterColor}`}>
            {charCount}/2000
          </span>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl px-6 h-11 text-sm font-medium transition-colors"
          >
            {isLoading ? (
              <>
                <LoadingSpinner size="sm" />
                Getting answer...
              </>
            ) : (
              "Ask Question →"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
