/* ------------------------------------------------------------------ */
/*  Step 1 — Upload a receipt image (drag-and-drop or file picker)    */
/* ------------------------------------------------------------------ */
"use client";

import { useCallback, useState, type DragEvent, type ChangeEvent } from "react";

interface UploadStepProps {
  /** true while the backend is processing */
  readonly loading: boolean;
  /** called with the chosen file */
  readonly onUpload: (file: File) => void;
  /** error message to display (e.g. low-confidence rejection) */
  readonly error?: string | null;
}

const ACCEPTED = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"];

export default function UploadStep({ loading, onUpload, error }: UploadStepProps) {
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  /* ---------- drag handlers ---------- */
  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file && ACCEPTED.includes(file.type)) {
        setFileName(file.name);
        onUpload(file);
      }
    },
    [onUpload]
  );

  /* ---------- file picker handler ---------- */
  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setFileName(file.name);
        onUpload(file);
      }
    },
    [onUpload]
  );

  return (
    <section className="mx-auto w-full max-w-xl space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-gray-900">Upload Your Receipt</h2>
        <p className="text-sm text-gray-500">
          Take a photo or upload an image of your receipt to get started.
        </p>
      </div>

      {/* Drop zone */}
      <label
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-12 transition-colors ${
          dragOver
            ? "border-indigo-500 bg-indigo-50"
            : "border-gray-300 bg-gray-50 hover:border-gray-400"
        } ${loading ? "pointer-events-none opacity-60" : ""}`}
      >
        {/* Upload icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-10 w-10 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>

        <span className="text-sm font-medium text-gray-600">
          {fileName ?? "Drag & drop your receipt here, or click to browse"}
        </span>

        <span className="text-xs text-gray-400">JPG, PNG, WebP up to 10 MB</span>

        <input
          type="file"
          accept={ACCEPTED.join(",")}
          onChange={handleFileChange}
          className="hidden"
          disabled={loading}
        />
      </label>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <p className="font-medium">⚠️ {error}</p>
          <p className="mt-1 text-red-500">Please provide more information and try again.</p>
        </div>
      )}
    </section>
  );
}
