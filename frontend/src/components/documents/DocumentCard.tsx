"use client";

import { FileText, Trash2 } from "lucide-react";
import { ProcessingBadge } from "./ProcessingBadge";
import { getDomain, timeAgo } from "@/lib/queryHelpers";
import type { Document } from "@/types";

interface DocumentCardProps {
  document: Document;
  onDelete: (id: string) => void;
  isAdmin: boolean;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export function DocumentCard({ document, onDelete, isAdmin }: DocumentCardProps) {
  const domain = getDomain(document.source_url);
  const uploaded = timeAgo(document.created_at);

  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 transition-shadow hover:shadow-sm">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <FileText className="mt-0.5 h-5 w-5 shrink-0 text-slate-400" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-800">{document.title}</p>
          <p className="mt-0.5 text-xs text-slate-500">
            {domain && <span>{domain} · </span>}
            <span>Uploaded {uploaded || "just now"}</span>
            {document.author && <span> · {document.author}</span>}
          </p>
          {typeof document.file_size_bytes === "number" && (
            <p className="mt-0.5 text-xs text-slate-400">
              {formatFileSize(document.file_size_bytes)}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <ProcessingBadge
          isProcessed={document.is_processed}
          chunksCount={document.chunks_count}
        />
        {isAdmin && (
          <button
            type="button"
            onClick={() => onDelete(document.id)}
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
            aria-label={`Delete ${document.title}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
