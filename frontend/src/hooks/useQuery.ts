"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { generateSessionId } from "@/lib/queryHelpers";
import { getUserIdentity } from "@/lib/auth";
import type { QueryResponse } from "@/types";

interface QueryState {
  isLoading: boolean;
  result: QueryResponse | null;
  error: string | null;
  sessionId: string;
}

interface UseQueryReturn extends QueryState {
  submitQuestion: (question: string, topK?: number) => Promise<void>;
  clearResult: () => void;
  clearError: () => void;
  resetSession: () => void;
}

function mapError(status: number | undefined): string {
  if (status === 422) return "Your question is too long or contains invalid characters.";
  if (status === 429) return "You're asking questions too quickly. Please wait a moment.";
  if (status === 503) return "The AI service is temporarily unavailable. Try again shortly.";
  return "Failed to get an answer. Please try again.";
}

export function useQuery(): UseQueryReturn {
  const [state, setState] = useState<QueryState>({
    isLoading: false,
    result: null,
    error: null,
    sessionId: "",
  });

  useEffect(() => {
    setState((s) => ({ ...s, sessionId: generateSessionId() }));
  }, []);

  async function submitQuestion(question: string, topK?: number): Promise<void> {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    const user = getUserIdentity();
    try {
      const { data } = await api.post<QueryResponse>("/queries", {
        question,
        top_k: topK ?? 5,
        user_id: user?.user_id ?? "",
        session_id: state.sessionId,
      });
      setState((s) => ({ ...s, isLoading: false, result: data }));
    } catch (err: unknown) {
      const status =
        err &&
        typeof err === "object" &&
        "response" in err &&
        err.response &&
        typeof err.response === "object" &&
        "status" in err.response
          ? (err.response as { status: number }).status
          : undefined;
      setState((s) => ({
        ...s,
        isLoading: false,
        error: mapError(status),
      }));
    }
  }

  function clearResult() {
    setState((s) => ({ ...s, result: null }));
  }

  function clearError() {
    setState((s) => ({ ...s, error: null }));
  }

  function resetSession() {
    setState((s) => ({ ...s, result: null, sessionId: generateSessionId() }));
  }

  return { ...state, submitQuestion, clearResult, clearError, resetSession };
}
