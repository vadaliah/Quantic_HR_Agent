-- 005: Least privilege for the agent runtime role (brief section 4: no irreversible actions).
-- Replaces the broad SELECT/INSERT/UPDATE grant from 003.
-- The runtime may READ reference data and may only INSERT mock tickets and trace rows.
-- Corpus ingestion and seeding run as the admin secret, never as the runtime.
--
-- Idempotent and re-runnable: apply with the Data API runner, which owns the
-- transaction, so this file contains no BEGIN/COMMIT.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM quantic_hr_agent;

GRANT SELECT ON
  locations,
  employees,
  managers,
  pto_accruals,
  pto_blackouts,
  benefits,
  tickets,
  policy_documents,
  policy_chunks,
  agent_runs
TO quantic_hr_agent;

-- pto_balances from migration 002 is deprecated by 004 but still exists and is
-- still empty. The runtime may read it until it is dropped, and never write it.
GRANT SELECT ON pto_balances TO quantic_hr_agent;

-- The runtime may only append: mock HR tickets and the agent trace log.
GRANT INSERT ON tickets, agent_runs TO quantic_hr_agent;

-- Sequence needed for agent_runs inserts if a serial key is added later.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO quantic_hr_agent;

-- Balance lookup is the only function the runtime may execute.
GRANT EXECUTE ON FUNCTION pto_balance_as_of(date) TO quantic_hr_agent;

-- Belt and braces: keep the runtime out of schema changes and corpus ingestion.
REVOKE CREATE ON SCHEMA public FROM quantic_hr_agent;
