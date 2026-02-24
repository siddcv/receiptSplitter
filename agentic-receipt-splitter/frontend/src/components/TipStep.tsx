/* ------------------------------------------------------------------ */
/*  Intermediate step — optional additional tip (percentage-based)    */
/* ------------------------------------------------------------------ */
"use client";

import { useState } from "react";
import type { Totals } from "@/lib/types";

interface TipStepProps {
  readonly totals: Totals | null | undefined;
  readonly onSubmit: (tipPercent: number) => void;
}

export default function TipStep({ totals, onSubmit }: TipStepProps) {
  const [value, setValue] = useState("");

  const subtotal = totals ? Number.parseFloat(totals.subtotal) : 0;
  const tipPercent = Number.parseFloat(value) || 0;
  const tipAmount = (subtotal * tipPercent) / 100;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    // Allow empty, digits, and one decimal point
    if (raw === "" || /^\d*\.?\d{0,2}$/.test(raw)) {
      setValue(raw);
    }
  };

  return (
    <section className="mx-auto w-full max-w-md space-y-6 text-center">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-gray-900">💵 Add a Tip?</h2>
        <p className="text-sm text-gray-500">
          If you&apos;d like to add an extra tip that isn&apos;t on the receipt,
          enter the percentage below. It will be split proportionally.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white px-6 py-5 shadow-sm space-y-4">
        <label
          htmlFor="tip-percent"
          className="block text-sm font-medium text-gray-700"
        >
          Additional tip (%)
        </label>

        <div className="relative mx-auto w-40">
          <input
            id="tip-percent"
            type="text"
            inputMode="decimal"
            value={value}
            onChange={handleChange}
            placeholder="0"
            className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 pr-8 text-center text-lg font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 font-medium">
            %
          </span>
        </div>

        {tipPercent > 0 && (
          <p className="text-sm text-gray-500">
            +${tipAmount.toFixed(2)} on a ${subtotal.toFixed(2)} subtotal
          </p>
        )}
      </div>

      <div className="flex items-center justify-center gap-3">
        <button
          onClick={() => onSubmit(tipPercent)}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          {tipPercent > 0 ? `Add ${tipPercent}% Tip →` : "Continue without Tip →"}
        </button>

        {value !== "" && tipPercent !== 0 && (
          <button
            onClick={() => onSubmit(0)}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          >
            Skip
          </button>
        )}
      </div>
    </section>
  );
}
