/* ------------------------------------------------------------------ */
/*  Step 2 — Review extracted items + free-form assignment text box   */
/* ------------------------------------------------------------------ */
"use client";

import { useState } from "react";
import type { Item, Totals } from "@/lib/types";

interface ReviewStepProps {
  readonly items: Item[];
  readonly totals: Totals | null | undefined;
  /** Backend clarification question, if any */
  readonly clarification?: string | null;
  /** true while backend is processing the assignment */
  readonly loading: boolean;
  /** Called when the user submits their free-form assignment text */
  readonly onSubmit: (text: string) => void;
  /** Called when the user wants to go back and upload a different receipt */
  readonly onCancel: () => void;
}

export default function ReviewStep({
  items,
  totals,
  clarification,
  loading,
  onSubmit,
  onCancel,
}: ReviewStepProps) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  return (
    <section className="mx-auto w-full max-w-3xl space-y-8">
      {/* ---- Extracted items table ---- */}
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-1">Extracted Items</h2>
        <p className="text-sm text-gray-500 mb-4">
          These items were read from your receipt. Review them before assigning.
        </p>

        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3 w-10">#</th>
                <th className="px-4 py-3">Item</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Line Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((item, i) => {
                const qty = Number.parseFloat(item.quantity);
                const price = Number.parseFloat(item.price);
                const lineTotal = (qty * price).toFixed(2);
                return (
                  <tr key={`item-${item.name}-${i}`} className="hover:bg-gray-50/60">
                    <td className="px-4 py-2.5 text-gray-400 font-mono">{i}</td>
                    <td className="px-4 py-2.5 font-medium text-gray-800">{item.name}</td>
                    <td className="px-4 py-2.5 text-right text-gray-600">{qty}</td>
                    <td className="px-4 py-2.5 text-right text-gray-600">${price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-medium text-gray-800">
                      ${lineTotal}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ---- Totals summary ---- */}
      {totals && (
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 rounded-lg border border-gray-200 bg-gray-50 px-6 py-4 text-sm max-w-sm">
          <span className="text-gray-500">Subtotal</span>
          <span className="text-right font-medium">${Number.parseFloat(totals.subtotal).toFixed(2)}</span>

          <span className="text-gray-500">Tax</span>
          <span className="text-right font-medium">${Number.parseFloat(totals.tax_total).toFixed(2)}</span>

          {Number.parseFloat(totals.tip_total) > 0 && (
            <>
              <span className="text-gray-500">Tip</span>
              <span className="text-right font-medium">
                ${Number.parseFloat(totals.tip_total).toFixed(2)}
              </span>
            </>
          )}

          {Number.parseFloat(totals.fees_total) > 0 && (
            <>
              <span className="text-gray-500">Fees</span>
              <span className="text-right font-medium">
                ${Number.parseFloat(totals.fees_total).toFixed(2)}
              </span>
            </>
          )}

          <span className="border-t border-gray-300 pt-2 font-semibold text-gray-900">Total</span>
          <span className="border-t border-gray-300 pt-2 text-right font-bold text-gray-900">
            ${Number.parseFloat(totals.grand_total).toFixed(2)}
          </span>
        </div>
      )}

      {/* ---- Interview: clarification or prompt ---- */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-gray-900">
          Who had what?
        </h3>

        {clarification && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <p className="font-medium mb-1">🔄 Clarification needed</p>
            <p className="whitespace-pre-wrap">{clarification}</p>
          </div>
        )}

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={loading}
          rows={5}
          placeholder={
            'Tell us who was there and what each person had.\n\n' +
            'Example: "Alice had the burger and fries. Bob and Charlie split the pizza. Everyone shared the appetizer."'
          }
          className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm text-gray-800 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:opacity-50"
        />

        <div className="flex items-center gap-3">
          <button
            onClick={handleSubmit}
            disabled={loading || !text.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                {" Processing…"}
              </>
            ) : (
              "Split the Bill →"
            )}
          </button>

          <button
            onClick={onCancel}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ↩ Upload Different Receipt
          </button>
        </div>
      </div>
    </section>
  );
}
