/* ------------------------------------------------------------------ */
/*  TypeScript types matching the FastAPI backend state models         */
/* ------------------------------------------------------------------ */

export interface ItemConfidence {
  name?: number;
  quantity?: number;
  unit_price?: number;
}

export interface Item {
  name: string;
  price: string; // Decimal comes as string from JSON
  quantity: string;
  confidence?: ItemConfidence | null;
}

export interface Totals {
  subtotal: string;
  tax_total: string;
  tip_total: string;
  fees_total: string;
  grand_total: string;
}

export interface AssignmentShare {
  participant: string;
  fraction: string;
}

export interface ItemAssignment {
  item_index: number;
  shares: AssignmentShare[];
}

export interface AuditEvent {
  timestamp: string;
  node: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface ParticipantCost {
  participant: string;
  item_costs: {
    item_index: number;
    item_name: string;
    item_price: number;
    quantity: number;
    share_percentage: number; // 0-100
    cost: number;
  }[];
  subtotal: string;
  tax_share: string;
  tip_share: string;
  fees_share: string;
  total_owed: string;
}

export interface ReceiptState {
  thread_id: string;
  image_path?: string | null;
  items: Item[];
  participants: string[];
  assignments: ItemAssignment[];
  totals?: Totals | null;
  confidence?: Record<string, number> | null;
  audit_log: AuditEvent[];
  current_node?: string | null;
  pending_questions: string[];
  final_costs?: ParticipantCost[] | null;
}

export interface UploadResponse {
  thread_id: string;
  state: ReceiptState;
}

export interface InterviewResponse {
  thread_id: string;
  state: ReceiptState;
}

/** Which step of the UI flow the user is on */
export type AppStep = "upload" | "review" | "results";
