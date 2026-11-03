-- 004: Align the schema with corpus POL-001..POL-012 and mock_data/.
-- Additive and idempotent: safe to re-run, does not alter 001-003.
-- Apply as the admin user (quantic_hr_admin), not the runtime role.

-- Locations ---------------------------------------------------------------
ALTER TABLE locations ADD COLUMN IF NOT EXISTS country text;

-- Employees: fields needed for probation, FMLA, sabbatical, PT proration ----
ALTER TABLE employees ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS scheduled_hours_per_week integer;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS hire_date date;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS home_country text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS home_location text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS work_model text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS remote_eligible boolean;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS designated_onsite_role boolean NOT NULL DEFAULT false;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS cost_center text;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'employees_employment_type_chk') THEN
    ALTER TABLE employees ADD CONSTRAINT employees_employment_type_chk
      CHECK (employment_type IN ('FT', 'PT', 'CONTRACTOR'));
  END IF;
END $$;

-- PTO: accrual STATE in days. pto_balances (hours, from 002) is deprecated.
CREATE TABLE IF NOT EXISTS pto_accruals (
  employee_id            text PRIMARY KEY REFERENCES employees (employee_id),
  plan                   text NOT NULL CHECK (plan IN ('FULL_TIME_STANDARD','PART_TIME_PRORATED','NOT_ELIGIBLE')),
  accrual_days_per_month numeric(6,4) NOT NULL,          -- 1.25 FT (POL-001 2.1), prorated PT (2.2)
  carryover_days         numeric(5,2) NOT NULL CHECK (carryover_days BETWEEN 0 AND 5),  -- POL-001 4.1
  taken_days_this_year   numeric(5,2) NOT NULL DEFAULT 0,
  pending_days           numeric(5,2) NOT NULL DEFAULT 0,
  balance_year           integer NOT NULL
);
COMMENT ON TABLE pto_balances IS 'DEPRECATED by 004: use pto_accruals + pto_balance_as_of().';

CREATE TABLE IF NOT EXISTS pto_blackouts (           -- POL-001 3.3, month/day so they apply every year
  label       text PRIMARY KEY,
  start_month int NOT NULL, start_day int NOT NULL,
  end_month   int NOT NULL, end_day   int NOT NULL
);

-- Live balance. The app passes CURRENT_DATE; evaluation pins a fixed date.
CREATE OR REPLACE FUNCTION pto_balance_as_of(as_of date DEFAULT CURRENT_DATE)
RETURNS TABLE (employee_id text, plan text, accrued_days numeric, available_days numeric)
LANGUAGE sql STABLE AS $$
  SELECT a.employee_id, a.plan,
         round(a.accrual_days_per_month
               * GREATEST(0, as_of - GREATEST(make_date(extract(year FROM as_of)::int, 1, 1), e.hire_date))
               / 30.4375, 2) AS accrued_days,
         round(a.carryover_days
               + a.accrual_days_per_month
                 * GREATEST(0, as_of - GREATEST(make_date(extract(year FROM as_of)::int, 1, 1), e.hire_date))
                 / 30.4375
               - a.taken_days_this_year - a.pending_days, 2) AS available_days
  FROM pto_accruals a JOIN employees e USING (employee_id);
$$;

-- Benefits (POL-007) -------------------------------------------------------
CREATE TABLE IF NOT EXISTS benefits (
  employee_id              text PRIMARY KEY REFERENCES employees (employee_id),
  benefits_class           text NOT NULL CHECK (benefits_class IN ('FULL','RETIREMENT_ONLY','NOT_ELIGIBLE','NON_US_LOCAL')),
  reason                   text,
  coverage_start           date,
  enrollment_deadline      date,
  medical_plan             text,
  dental                   boolean,
  vision                   boolean,
  company_premium_share_pct numeric,
  retirement_match_pct     numeric,
  retirement_enrolled      boolean,
  disability               boolean,
  life_insurance_multiple  numeric,
  wellness_remaining       numeric,
  learning_remaining       numeric
);

-- Tickets: mock actions only ---------------------------------------------
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS summary text;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS is_mock boolean NOT NULL DEFAULT true;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS confirmed_by_user boolean NOT NULL DEFAULT false;

-- Policy metadata for citations -------------------------------------------
ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS format text;
ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS chunk_index integer;
ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS token_count integer;
ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS content_sha text;
CREATE INDEX IF NOT EXISTS policy_chunks_embedding_hnsw
  ON policy_chunks USING hnsw (embedding vector_cosine_ops);

-- Agent trace log (brief section 4 trace + section 9 latency metrics) ------
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id       uuid PRIMARY KEY,
  thread_id    text,
  user_message text NOT NULL,
  answer       text,
  trace        jsonb NOT NULL DEFAULT '[]'::jsonb,
  citations    jsonb NOT NULL DEFAULT '[]'::jsonb,
  escalation   boolean NOT NULL DEFAULT false,
  latency_ms   integer,
  cold_start   boolean,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_runs_created_at_idx ON agent_runs (created_at);
