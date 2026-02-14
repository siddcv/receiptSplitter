/* ------------------------------------------------------------------ */
/*  Step 3 — Per-person itemised results                              */
/* ------------------------------------------------------------------ */
"use client";

import type { ParticipantCost, Totals } from "@/lib/types";

interface ResultsStepProps {
  readonly costs: ParticipantCost[];
  readonly totals: Totals | null | undefined;
  readonly onStartOver: () => void;
}

function $(v: string | number) {
  return `$${Number.parseFloat(String(v)).toFixed(2)}`;
}

export default function ResultsStep({ costs, totals, onStartOver }: ResultsStepProps) {
  const grandTotal = costs.reduce((sum, c) => sum + Number.parseFloat(c.total_owed), 0);

  return (
    <section className="mx-auto w-full max-w-4xl space-y-8">
      <div className="text-center space-y-1">
        <h2 className="text-2xl font-bold text-gray-900">🎉 Bill Split Results</h2>
        <p className="text-sm text-gray-500">Here&apos;s what each person owes.</p>
      </div>

      {/* ---- Per-person cards ---- */}
      <div className="grid gap-6 lg:grid-cols-2">
        {costs.map((person) => (
          <div
            key={person.participant}
            className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between bg-gray-50 px-5 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">{person.participant}</h3>
              <span className="text-lg font-bold text-indigo-600">{$(person.total_owed)}</span>
            </div>

            {/* Item breakdown */}
            <div className="px-5 py-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs uppercase text-gray-400">
                    <th className="pb-1 text-left font-medium">Item</th>
                    <th className="pb-1 text-right font-medium">Share</th>
                    <th className="pb-1 text-right font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {person.item_costs.map((it) => {
                    const pct = it.share_percentage;
                    const shareLabel =
                      pct === 100 ? "full" : `${Math.round(pct)}%`;
                    return (
                      <tr key={it.item_index}>
                        <td className="py-1.5 text-gray-700">{it.item_name}</td>
                        <td className="py-1.5 text-right text-gray-500">{shareLabel}</td>
                        <td className="py-1.5 text-right font-medium text-gray-800">
                          {$(it.cost)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Cost summary */}
            <div className="border-t border-gray-100 bg-gray-50/50 px-5 py-3 text-sm">
              <div className="flex justify-between text-gray-500">
                <span>Subtotal</span>
                <span>{$(person.subtotal)}</span>
              </div>
              <div className="flex justify-between text-gray-500">
                <span>Tax share</span>
                <span>{$(person.tax_share)}</span>
              </div>
              {Number.parseFloat(person.tip_share) > 0 && (
                <div className="flex justify-between text-gray-500">
                  <span>Tip share</span>
                  <span>{$(person.tip_share)}</span>
                </div>
              )}
              {Number.parseFloat(person.fees_share) > 0 && (
                <div className="flex justify-between text-gray-500">
                  <span>Fees share</span>
                  <span>{$(person.fees_share)}</span>
                </div>
              )}
              <div className="mt-1 flex justify-between border-t border-gray-200 pt-1 font-semibold text-gray-900">
                <span>Total</span>
                <span>{$(person.total_owed)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ---- Validation row ---- */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 px-6 py-4 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-gray-600">Sum of all shares</span>
          <span className="font-bold text-gray-900">{$(grandTotal)}</span>
        </div>
        {totals && (
          <div className="flex items-center justify-between mt-1">
            <span className="text-gray-600">Receipt total</span>
            <span className="font-bold text-gray-900">{$(totals.grand_total)}</span>
          </div>
        )}
        {totals && (
          <div className="mt-2 text-center">
            {Math.abs(grandTotal - Number.parseFloat(totals.grand_total)) < 0.06 ? (
              <span className="inline-flex items-center gap-1 text-green-600 font-medium">
                ✅ Totals match
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-red-600 font-medium">
                ⚠️ Totals differ by{" "}
                {$(Math.abs(grandTotal - Number.parseFloat(totals.grand_total)))}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ---- Start Over ---- */}
      <div className="text-center">
        <button
          onClick={onStartOver}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-200"
        >
          ↩ Start Over
        </button>
      </div>
    </section>
  );
}
