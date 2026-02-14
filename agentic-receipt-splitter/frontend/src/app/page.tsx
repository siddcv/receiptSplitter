/* ------------------------------------------------------------------ */
/*  Main page — single-page receipt splitter flow                     */
/*  Step 1: Upload  →  Step 2: Review + Interview  →  Step 3: Results */
/* ------------------------------------------------------------------ */
"use client";

import { useCallback, useState } from "react";

import UploadStep from "@/components/UploadStep";
import ReviewStep from "@/components/ReviewStep";
import ResultsStep from "@/components/ResultsStep";
import Spinner from "@/components/Spinner";
import { uploadReceipt, submitInterview } from "@/lib/api";
import type { AppStep, ReceiptState } from "@/lib/types";

/**
 * If ≥ 50 % of extracted item fields were flagged as low-confidence, the
 * receipt image is considered too unclear and the user is asked to re-upload.
 */
function isReceiptTooPoor(state: ReceiptState): boolean {
  // Case 1: vision model outright failed — backend already set a message
  if (
    state.pending_questions.length === 1 &&
    state.pending_questions[0].toLowerCase().includes("vision model failed")
  ) {
    return true;
  }

  // Case 2: too many low-confidence field flags
  if (state.items.length === 0) return true;

  const totalFields = state.items.length * 3; // name, qty, price per item
  const flagCount = state.pending_questions.filter((q) =>
    q.toLowerCase().includes("confidence")
  ).length;

  return totalFields > 0 && flagCount / totalFields >= 0.5;
}

const MAX_INTERVIEW_ATTEMPTS = 3;

export default function Home() {
  const [step, setStep] = useState<AppStep>("upload");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<ReceiptState | null>(null);
  const [clarification, setClarification] = useState<string | null>(null);
  const [attempts, setAttempts] = useState(0);

  /* ---- Step 1 → 2: upload image ---- */
  const handleUpload = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);
    try {
      const res = await uploadReceipt(file);
      const s = res.state;

      if (isReceiptTooPoor(s)) {
        setError(
          "The receipt image wasn\u2019t clear enough to extract items reliably. " +
            "Please upload a higher-quality photo."
        );
        setLoading(false);
        return; // stay on step 1
      }

      setState(s);
      setStep("review");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Handle a failed interview attempt: increment attempts and either show
   * a clarification message or bail back to upload after MAX_INTERVIEW_ATTEMPTS.
   */
  const handleFailedAttempt = useCallback(
    (message: string) => {
      const nextAttempt = attempts + 1;
      setAttempts(nextAttempt);

      if (nextAttempt >= MAX_INTERVIEW_ATTEMPTS) {
        setStep("upload");
        setError(
          "Not enough information was provided to split the bill accurately. Please try again."
        );
        setState(null);
        setClarification(null);
        setAttempts(0);
      } else {
        setClarification(
          `${message}\n\n(Attempt ${nextAttempt} of ${MAX_INTERVIEW_ATTEMPTS})`
        );
      }
    },
    [attempts]
  );

  /* ---- Step 2 → 3 (or back to 2 with clarification): submit assignment ---- */
  const handleInterview = useCallback(
    async (text: string) => {
      if (!state) return;
      setLoading(true);
      setClarification(null);
      try {
        const res = await submitInterview(state.thread_id, text);
        const s = res.state;
        setState(s);

        if (s.pending_questions.length > 0) {
          handleFailedAttempt(s.pending_questions.join("\n\n"));
        } else if (s.final_costs && s.final_costs.length > 0) {
          setStep("results");
        } else {
          handleFailedAttempt(
            "Something went wrong computing the split. Please try describing the assignments again."
          );
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Submission failed";
        handleFailedAttempt(`Error: ${msg}. Please try again.`);
      } finally {
        setLoading(false);
      }
    },
    [state, handleFailedAttempt]
  );

  /* ---- Reset everything ---- */
  const handleStartOver = useCallback(() => {
    setStep("upload");
    setLoading(false);
    setError(null);
    setState(null);
    setClarification(null);
    setAttempts(0);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ---- Header ---- */}
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <h1 className="text-lg font-bold text-gray-900 tracking-tight">
            🧾 Receipt Splitter
          </h1>

          {/* Step indicator */}
          <div className="flex items-center gap-2 text-xs font-medium text-gray-400">
            <span className={step === "upload" ? "text-indigo-600" : ""}>Upload</span>
            <span>→</span>
            <span className={step === "review" ? "text-indigo-600" : ""}>Assign</span>
            <span>→</span>
            <span className={step === "results" ? "text-indigo-600" : ""}>Results</span>
          </div>
        </div>
      </header>

      {/* ---- Main content ---- */}
      <main className="mx-auto max-w-5xl px-6 py-10">
        {loading && step === "upload" && <Spinner message="Extracting receipt data…" />}

        {step === "upload" && !loading && (
          <UploadStep loading={loading} onUpload={handleUpload} error={error} />
        )}

        {step === "review" && state && (
          <ReviewStep
            items={state.items}
            totals={state.totals}
            clarification={clarification}
            loading={loading}
            onSubmit={handleInterview}
            onCancel={handleStartOver}
          />
        )}

        {step === "results" && state?.final_costs && (
          <ResultsStep
            costs={state.final_costs}
            totals={state.totals}
            onStartOver={handleStartOver}
          />
        )}
      </main>

      {/* ---- Footer ---- */}
      <footer className="border-t border-gray-200 bg-white py-4 text-center text-xs text-gray-400">
        Agentic Receipt Splitter · Powered by Gemini + LangGraph
      </footer>
    </div>
  );
}
