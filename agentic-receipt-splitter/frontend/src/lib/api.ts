/* ------------------------------------------------------------------ */
/*  API client — talks to the FastAPI backend                         */
/* ------------------------------------------------------------------ */

import type { InterviewResponse, UploadResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ---- Upload a receipt image ---- */
export async function uploadReceipt(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail ?? `Upload failed (${res.status})`
    );
  }

  return res.json();
}

/* ---- Submit free-form assignment text ---- */
export async function submitInterview(
  threadId: string,
  text: string
): Promise<InterviewResponse> {
  const res = await fetch(`${API_BASE}/interview/${threadId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ free_form_assignment: text }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail ?? `Interview submission failed (${res.status})`
    );
  }

  return res.json();
}
