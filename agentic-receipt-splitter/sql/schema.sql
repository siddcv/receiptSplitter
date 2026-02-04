-- Agentic Receipt Splitter: Normalized Schema
-- Run this file to reset and create the core domain tables.

-- Optional: enable UUID generation with pgcrypto
-- If not available, use uuid-ossp or generate UUIDs in the app.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Drop in dependency order (children -> parents)
DROP TABLE IF EXISTS assignments CASCADE;
DROP TABLE IF EXISTS receipt_items CASCADE;
DROP TABLE IF EXISTS participants CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS receipts CASCADE;

-- Receipts are keyed by your thread_id
CREATE TABLE receipts (
    id TEXT PRIMARY KEY, -- use thread_id
    subtotal    NUMERIC(12,2) NOT NULL CHECK (subtotal >= 0),
    tax_total   NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    tip_total   NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tip_total >= 0),
    fees_total  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (fees_total >= 0),
    grand_total NUMERIC(12,2) NOT NULL CHECK (grand_total >= 0),
    -- Ensure grand_total matches the sum of components
    CONSTRAINT receipts_total_consistency
        CHECK (grand_total = subtotal + tax_total + tip_total + fees_total),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique participants per receipt
CREATE TABLE participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id TEXT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT participants_unique_per_receipt UNIQUE (receipt_id, name)
);
CREATE INDEX idx_participants_receipt ON participants(receipt_id);

-- Items extracted from the receipt image
CREATE TABLE receipt_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id TEXT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity   NUMERIC(10,3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(12,2) NOT NULL CHECK (line_total >= 0),
    -- Store per-field confidences like {"item_name":0.92,"quantity":0.85,"unit_price":0.90}
    confidence JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_items_receipt ON receipt_items(receipt_id);

-- Assignment of items to participants with explicit fractions
CREATE TABLE assignments (
    item_id UUID NOT NULL REFERENCES receipt_items(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    fraction NUMERIC(6,5) NOT NULL CHECK (fraction >= 0 AND fraction <= 1),
    PRIMARY KEY (item_id, participant_id)
);
CREATE INDEX idx_assignments_item ON assignments(item_id);
CREATE INDEX idx_assignments_participant ON assignments(participant_id);

-- Optional: audit log to mirror the in-app audit trail (useful for reporting)
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    receipt_id TEXT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    node TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB
);
CREATE INDEX idx_audit_receipt_ts ON audit_logs(receipt_id, ts);
