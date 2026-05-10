"use client";

import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { DocumentUploader } from "@/components/documents/DocumentUploader";
import { DocumentTable } from "@/components/documents/DocumentTable";
import { DeleteConfirmModal } from "@/components/documents/DeleteConfirmModal";
import { useDocuments } from "@/hooks/useDocuments";
import { getUserIdentity } from "@/lib/auth";
import type { Document } from "@/types";

export default function DocumentsPage() {
  const {
    documents,
    isLoading,
    error,
    uploadState,
    uploadDocument,
    deleteDocument,
    refetch,
    resetUploadSuccess,
  } = useDocuments();

  const [isAdmin, setIsAdmin] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    setIsAdmin(getUserIdentity()?.role === "admin");
  }, []);

  function handleRequestDelete(id: string) {
    const target = documents.find((d) => d.id === id);
    if (target) setPendingDelete(target);
  }

  async function handleConfirmDelete() {
    if (!pendingDelete) return;
    setIsDeleting(true);
    try {
      await deleteDocument(pendingDelete.id);
    } finally {
      setIsDeleting(false);
      setPendingDelete(null);
    }
  }

  return (
    <PageWrapper
      title="Documents"
      subtitle="Manage your healthcare knowledge base"
    >
      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} />
        </div>
      )}

      {!isAdmin && (
        <div className="mb-4 flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-700">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Contact your administrator to add documents to the knowledge base.</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-5">
        {isAdmin && (
          <div className="md:col-span-2">
            <DocumentUploader
              onUploadSuccess={refetch}
              isUploading={uploadState.isUploading}
              progress={uploadState.progress}
              error={uploadState.error}
              success={uploadState.success}
              onUpload={uploadDocument}
              onResetStatus={resetUploadSuccess}
            />
          </div>
        )}

        <div className={isAdmin ? "md:col-span-3" : "md:col-span-5"}>
          <DocumentTable
            documents={documents}
            isLoading={isLoading}
            onDelete={handleRequestDelete}
            onRefresh={refetch}
            isAdmin={isAdmin}
          />
        </div>
      </div>

      <DeleteConfirmModal
        isOpen={pendingDelete !== null}
        documentTitle={pendingDelete?.title ?? ""}
        chunksCount={pendingDelete?.chunks_count ?? 0}
        isDeleting={isDeleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => {
          if (!isDeleting) setPendingDelete(null);
        }}
      />
    </PageWrapper>
  );
}
