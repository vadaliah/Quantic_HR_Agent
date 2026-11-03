-- 005: Least privilege for the agent runtime role (brief section 4: no irreversible actions).
-- Replaces the broad SELECT/INSERT/UPDATE grant from 003.
-- The runtime may READ reference data and may only INSERT mock tickets and trace rows.
-- Corpus ingestion and seeding run as quantic_hr_admin, never as the runtime.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM quantic_hr_agent;

GRANT SELECT ON
  locations, employees, managers, pto_accruals, pto_blackouts, benefits,
  tickets, policy_documents, policy_chunks
TO quantic_hr_agent;

GRANT INSERT ON tickets, agent_runs TO quantic_hr_agent;
GRANT EXECUTE ON FUNCTION pto_balance_as_of(date) TO quantic_hr_agent;
