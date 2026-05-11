"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { Document } from "@/types";

export interface UploadMetadata {
  title: string;
  source_url?: string;
  author?: string;
}

export interface UploadState {
  isUploading: boolean;
  progress: number;
  error: string | null;
  success: boolean;
}

interface DocumentsListResponse {
  items: Document[];
  page: number;
  page_size: number;
}

export interface UseDocumentsReturn {
  documents: Document[];
  isLoading: boolean;
  error: string | null;
  uploadState: UploadState;
  uploadDocument: (file: File, metadata: UploadMetadata) => Promise<void>;
  deleteDocument: (id: string) => Promise<void>;
  refetch: () => void;
  resetUploadSuccess: () => void;
}

const INITIAL_UPLOAD_STATE: UploadState = {
  isUploading: false,
  progress: 0,
  error: null,
  success: false,
};

function mapUploadError(status: number | undefined, detail?: string): string {
  if (status === 413) return "File is too large. Maximum size is 50MB.";
  if (status === 415) return "File type not supported. Upload PDF or text files.";
  if (status === 422) return detail || "Upload failed: invalid file or missing fields.";
  return "Upload failed. Please try again.";
}

function mapDeleteError(status: number | undefined): string {
  if (status === 403) return "You don't have permission to delete this document.";
  if (status === 404) return "Document not found. It may already be deleted.";
  return "Failed to delete document. Please try again.";
}

function getErrorInfo(err: unknown): { status?: number; detail?: string } {
  if (
    err &&
    typeof err === "object" &&
    "response" in err &&
    err.response &&
    typeof err.response === "object" &&
    "status" in err.response
  ) {
    const res = err.response as { status: number; data?: { detail?: string } };
    return { status: res.status, detail: res.data?.detail };
  }
  return {};
}

export function useDocuments(): UseDocumentsReturn {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>(INITIAL_UPLOAD_STATE);

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { data } = await api.get<DocumentsListResponse>(
        "/documents?page=1&page_size=50",
      );
      setDocuments(data.items ?? []);
    } catch {
      setError("Failed to load documents. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  async function uploadDocument(file: File, metadata: UploadMetadata): Promise<void> {
    setUploadState({ isUploading: true, progress: 0, error: null, success: false });

    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", metadata.title);
    if (metadata.source_url) formData.append("source_url", metadata.source_url);
    if (metadata.author) formData.append("author", metadata.author);

    try {
      await api.post("/documents", formData, {
        onUploadProgress: (e) => {
          const total = e.total ?? 1;
          const pct = Math.round((e.loaded * 100) / total);
          setUploadState((s) => ({ ...s, progress: pct }));
        },
      });
      setUploadState({ isUploading: false, progress: 100, error: null, success: true });
      await fetchDocuments();
    } catch (err: unknown) {
      const { status, detail } = getErrorInfo(err);
      setUploadState({
        isUploading: false,
        progress: 0,
        error: mapUploadError(status, detail),
        success: false,
      });
    }
  }

  async function deleteDocument(id: string): Promise<void> {
    const previous = documents;
    setDocuments((docs) => docs.filter((d) => d.id !== id));
    try {
      await api.delete(`/documents/${id}`);
    } catch (err: unknown) {
      setDocuments(previous);
      setError(mapDeleteError(getErrorInfo(err).status));
      await fetchDocuments();
    }
  }

  function resetUploadSuccess() {
    setUploadState((s) => ({ ...s, success: false, error: null, progress: 0 }));
  }

  return {
    documents,
    isLoading,
    error,
    uploadState,
    uploadDocument,
    deleteDocument,
    refetch: fetchDocuments,
    resetUploadSuccess,
  };
}
