"use client";

import { useEffect } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { AlertTriangle } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

interface DeleteConfirmModalProps {
  isOpen: boolean;
  documentTitle: string;
  chunksCount: number;
  isDeleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirmModal({
  isOpen,
  documentTitle,
  chunksCount,
  isDeleting,
  onConfirm,
  onCancel,
}: DeleteConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isDeleting) onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, isDeleting, onCancel]);

  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isDeleting) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-200 bg-white p-6 shadow-xl outline-none">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <Dialog.Title className="text-base font-semibold text-slate-800">
                Delete Document?
              </Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-slate-600">
                Are you sure you want to delete{" "}
                <span className="font-medium text-slate-800">
                  &quot;{documentTitle}&quot;
                </span>
                ? This will remove all {chunksCount}{" "}
                {chunksCount === 1 ? "chunk" : "chunks"} from the knowledge base
                and cannot be undone.
              </Dialog.Description>
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={isDeleting}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={isDeleting}
              className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isDeleting ? (
                <>
                  <LoadingSpinner size="sm" />
                  <span>Deleting...</span>
                </>
              ) : (
                "Delete"
              )}
            </button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
