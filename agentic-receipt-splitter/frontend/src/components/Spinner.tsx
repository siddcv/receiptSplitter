/* ------------------------------------------------------------------ */
/*  Reusable loading spinner                                          */
/* ------------------------------------------------------------------ */
"use client";

interface SpinnerProps {
  readonly message?: string;
}

export default function Spinner({ message = "Processing…" }: Readonly<SpinnerProps>) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-indigo-600" />
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}
