"use client";

import { useQuery as useRQQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { QueryResponse } from "@/types";

export interface QueryHistoryItem {
  query_id: string;
  question: string;
  answer: string;
  confidence_score: number;
  created_at: string;
}

interface QueryHistoryResponse {
  items: QueryHistoryItem[];
  page: number;
  page_size: number;
}

export function useQueryHistory(page = 1) {
  return useRQQuery<QueryHistoryResponse>({
    queryKey: ["queries", page],
    queryFn: async () => {
      const { data } = await api.get<QueryHistoryResponse>(
        `/queries?page=${page}&page_size=20`
      );
      return data;
    },
  });
}

export function useQueryDetail(queryId: string | null) {
  return useRQQuery<QueryResponse>({
    queryKey: ["query", queryId],
    queryFn: async () => {
      const { data } = await api.get<QueryResponse>(`/queries/${queryId}`);
      return data;
    },
    enabled: !!queryId,
  });
}

export function useSubmitFeedback() {
  return useMutation({
    mutationFn: async ({
      queryId,
      feedbackType,
      rating,
    }: {
      queryId: string;
      feedbackType: string;
      rating?: number;
    }) => {
      await api.post(`/queries/${queryId}/feedback`, {
        feedback_type: feedbackType,
        rating,
      });
    },
  });
}
