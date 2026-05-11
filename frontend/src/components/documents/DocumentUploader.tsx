"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle, FileText, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import type { UploadMetadata } from "@/hooks/useDocuments";

interface DocumentUploaderProps {
  onUploadSuccess: () => void;
  isUploading: boolean;
  progress: number;
  error: string | null;
  success: boolean;
  onUpload: (file: File, metadata: UploadMetadata) => Promise<void>;
  onResetStatus: () => void;
}

const MAX_BYTES = 52_428_800; // 50MB
const ALLOWED_TYPES = ["application/pdf", "text/plain"];

const SUGGESTED_SOURCES: Array<{ label: string; url: string }> = [
  { label: "CDC Guidelines", url: "https://www.cdc.gov" },
  { label: "WHO Fact Sheets", url: "https://www.who.int" },
  { label: "NIH MedlinePlus", url: "https://medlineplus.gov" },
  { label: "FDA Drug Info", url: "https://www.fda.gov" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

function isValidUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export function DocumentUploader({
  onUploadSuccess,
  isUploading,
  progress,
  error,
  success,
  onUpload,
  onResetStatus,
}: DocumentUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [author, setAuthor] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!success) return;
    setFile(null);
    setTitle("");
    setSourceUrl("");
    setAuthor("");
    setFileError(null);
    setUrlError(null);
    if (inputRef.current) inputRef.current.value = "";
    setShowSuccess(true);
    const timer = setTimeout(() => {
      setShowSuccess(false);
      onResetStatus();
      onUploadSuccess();
    }, 3000);
    return () => clearTimeout(timer);
  }, [success, onUploadSuccess, onResetStatus]);

  function validateFile(candidate: File): string | null {
    if (!ALLOWED_TYPES.includes(candidate.type)) {
      return "File type not supported. Upload PDF or TXT files.";
    }
    if (candidate.size > MAX_BYTES) {
      return "File is too large. Maximum size is 50MB.";
    }
    return null;
  }

  function handleFileSelected(candidate: File | null) {
    if (!candidate) {
      setFile(null);
      setFileError(null);
      return;
    }
    const validation = validateFile(candidate);
    if (validation) {
      setFileError(validation);
      setFile(null);
      return;
    }
    setFileError(null);
    setFile(candidate);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) handleFileSelected(dropped);
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleZoneClick() {
    inputRef.current?.click();
  }

  function handleZoneKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleZoneClick();
    }
  }

  function handleClearFile(e: React.MouseEvent) {
    e.stopPropagation();
    setFile(null);
    setFileError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim() || isUploading) return;

    if (sourceUrl.trim() && !isValidUrl(sourceUrl.trim())) {
      setUrlError("Enter a valid URL starting with http:// or https://");
      return;
    }
    setUrlError(null);

    await onUpload(file, {
      title: title.trim(),
      source_url: sourceUrl.trim() || undefined,
      author: author.trim() || undefined,
    });
  }

  const submitDisabled = !file || !title.trim() || isUploading;

  const zoneClasses = [
    "relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors",
    file
      ? "border-green-400 bg-green-50"
      : isDragging
        ? "border-blue-400 bg-blue-50"
        : "border-slate-200 bg-white hover:border-slate-300",
  ].join(" ");

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-base font-semibold text-slate-800">Upload Healthcare Document</h3>
      <p className="mt-1 text-xs text-slate-500">
        Add an official source (CDC, WHO, NIH, FDA) to the knowledge base.
      </p>

      <form onSubmit={handleSubmit} noValidate className="mt-4 space-y-4">
        <div>
          <div
            role="button"
            tabIndex={0}
            aria-label="Upload file"
            className={zoneClasses}
            onClick={handleZoneClick}
            onKeyDown={handleZoneKey}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {file ? (
              <>
                <CheckCircle className="h-12 w-12 text-green-500" />
                <p className="text-sm font-medium text-slate-800">{file.name}</p>
                <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
                <button
                  type="button"
                  onClick={handleClearFile}
                  className="absolute right-2 top-2 rounded-full p-1 text-slate-400 hover:bg-white hover:text-slate-600"
                  aria-label="Remove selected file"
                >
                  <X className="h-4 w-4" />
                </button>
              </>
            ) : (
              <>
                <FileText className="h-12 w-12 text-slate-300" />
                <p className="text-sm font-medium text-slate-700">
                  Drag &amp; drop your file here
                </p>
                <p className="text-xs text-slate-500">or click to browse</p>
                <p className="mt-1 text-xs text-slate-400">PDF or TXT · Max 50MB</p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              className="hidden"
              onChange={(e) => handleFileSelected(e.target.files?.[0] ?? null)}
            />
          </div>
          {fileError && <p className="mt-1 text-xs text-red-600">{fileError}</p>}
        </div>

        <div>
          <label htmlFor="doc-title" className="mb-1.5 block text-sm font-medium text-slate-700">
            Document Title <span className="text-red-500">*</span>
          </label>
          <Input
            id="doc-title"
            type="text"
            placeholder="CDC Type 2 Diabetes Guidelines"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={isUploading}
            className="w-full rounded-lg"
            required
          />
        </div>

        <div>
          <label htmlFor="doc-url" className="mb-1.5 block text-sm font-medium text-slate-700">
            Source URL <span className="text-slate-400">(optional)</span>
          </label>
          <Input
            id="doc-url"
            type="url"
            placeholder="https://www.cdc.gov/diabetes"
            value={sourceUrl}
            onChange={(e) => {
              setSourceUrl(e.target.value);
              if (urlError) setUrlError(null);
            }}
            disabled={isUploading}
            className="w-full rounded-lg"
            aria-invalid={!!urlError}
          />
          {urlError && <p className="mt-1 text-xs text-red-600">{urlError}</p>}
        </div>

        <div>
          <label htmlFor="doc-author" className="mb-1.5 block text-sm font-medium text-slate-700">
            Author <span className="text-slate-400">(optional)</span>
          </label>
          <Input
            id="doc-author"
            type="text"
            placeholder="Centers for Disease Control"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            disabled={isUploading}
            className="w-full rounded-lg"
          />
        </div>

        {isUploading && (
          <div className="flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-blue-600 transition-all duration-200 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-slate-500">{progress}%</span>
          </div>
        )}

        {error && <ErrorBanner message={error} onDismiss={onResetStatus} />}

        {showSuccess && (
          <ErrorBanner
            variant="info"
            message="Document uploaded and processed successfully!"
          />
        )}

        <button
          type="submit"
          disabled={submitDisabled}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-blue-600 font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isUploading ? (
            <>
              <LoadingSpinner size="sm" />
              <span>Uploading...</span>
            </>
          ) : (
            "Upload Document"
          )}
        </button>
      </form>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-500">Recommended official sources</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {SUGGESTED_SOURCES.map((src) => (
            <button
              key={src.url}
              type="button"
              onClick={() => {
                setSourceUrl(src.url);
                setUrlError(null);
              }}
              className="cursor-pointer rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs text-slate-600 transition-colors hover:bg-blue-50 hover:text-blue-600"
            >
              {src.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
