-- Synthetic HR and RAG tables. Not executed in Step 1.
-- Embedding width matches Titan Text Embeddings V2 at 1024 dimensions.

CREATE TABLE IF NOT EXISTS locations (
  location_id text PRIMARY KEY,
  name text NOT NULL,
  region text NOT NULL,
  remote_eligible boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
  employee_id text PRIMARY KEY,
  display_name text NOT NULL,
  email text NOT NULL,
  location_id text NOT NULL REFERENCES locations (location_id),
  manager_id text,
  employment_type text NOT NULL
);

CREATE TABLE IF NOT EXISTS managers (
  employee_id text PRIMARY KEY REFERENCES employees (employee_id),
  manager_id text REFERENCES employees (employee_id)
);

CREATE TABLE IF NOT EXISTS pto_balances (
  employee_id text PRIMARY KEY REFERENCES employees (employee_id),
  annual_hours numeric NOT NULL,
  used_hours numeric NOT NULL,
  pending_hours numeric NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
  ticket_id text PRIMARY KEY,
  employee_id text NOT NULL REFERENCES employees (employee_id),
  subject text NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_documents (
  document_id text PRIMARY KEY,
  title text NOT NULL,
  source_uri text NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_chunks (
  chunk_id text PRIMARY KEY,
  document_id text NOT NULL REFERENCES policy_documents (document_id),
  section_id text NOT NULL,
  heading text,
  content text NOT NULL,
  embedding vector(1024)
);

CREATE INDEX IF NOT EXISTS policy_chunks_document_id_idx
  ON policy_chunks (document_id);
