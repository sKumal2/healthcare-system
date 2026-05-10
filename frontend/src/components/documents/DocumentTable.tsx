"use client";

import { FolderOpen, RefreshCw } from "lucide-react";
import { DocumentCard } from "./DocumentCard";
import type { Document } from "@/types";

interface DocumentTableProps {
  documents: Document[];
  isLoading: boolean;
  onDelete: (id: string) => void;
  onRefresh: () => void;
  isAdmin: boolean;
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start gap-3">
        <div className="h-5 w-5 rounded bg-slate-200" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-2/3 rounded bg-slate-200" />
          <div className="h-3 w-1/3 rounded bg-slate-200" />
        </div>
        <div className="h-6 w-24 rounded-full bg-slate-200" />
      </div>
    </div>
  );
}

export function DocumentTable({
  documents,
  isLoading,
  onDelete,
  onRefresh,
  isAdmin,
}: DocumentTableProps) {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-base font-semibold text-slate-800">
          Documents
          {!isLoading && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {documents.length}
            </span>
          )}
        </h3>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : documents.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-slate-200 bg-white py-16 text-slate-500">
          <FolderOpen className="h-12 w-12 text-slate-300" />
          <p className="text-sm font-medium">No documents yet</p>
          <p className="text-xs text-slate-400">
            {isAdmin
              ? "Upload your first healthcare document to get started"
              : "Contact your administrator to add documents"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              document={doc}
              onDelete={onDelete}
              isAdmin={isAdmin}
            />
          ))}
        </div>
      )}
    </div>
  );
}
