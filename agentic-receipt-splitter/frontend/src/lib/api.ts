/* ------------------------------------------------------------------ */
/*  API client — talks to the FastAPI backend                         */
/* ------------------------------------------------------------------ */

import type { InterviewResponse, UploadResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForBackendReady({
  timeoutMs = 90_000,
  intervalMs = 2_500,
}: {
  timeoutMs?: number;
  intervalMs?: number;
} = {}): Promise<void> {
  const started = Date.now();

  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(`${API_BASE}/`, {
        method: "GET",
        cache: "no-store",
      });
      if (res.ok) return;
    } catch {
      // Backend likely still cold-starting.
    }

    await sleep(intervalMs);
  }

  throw new Error("Backend is still waking up. Please try again in a few seconds.");
}

/* ---- Upload a receipt image ---- */
export async function uploadReceipt(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    if (res.status === 429) {
      throw new Error(
        "You\u2019ve reached the upload limit (3 per hour). Please wait a while and try again."
      );
    }
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
    if (res.status === 429) {
      throw new Error(
        "You\u2019ve sent too many requests. Please wait a moment and try again."
      );
    }
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail ?? `Interview submission failed (${res.status})`
    );
  }

  return res.json();
}
