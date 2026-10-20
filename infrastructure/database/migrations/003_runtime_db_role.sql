-- IAM database user for the AgentCore runtime. Not executed in Step 1.
-- The runtime role may call rds-db:connect only as this user.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'quantic_hr_agent') THEN
    CREATE ROLE quantic_hr_agent LOGIN;
  END IF;
END
$$;

GRANT rds_iam TO quantic_hr_agent;
GRANT CONNECT ON DATABASE quantic_hr TO quantic_hr_agent;
GRANT USAGE ON SCHEMA public TO quantic_hr_agent;
GRANT SELECT, INSERT, UPDATE ON
  locations,
  employees,
  managers,
  pto_balances,
  tickets,
  policy_documents,
  policy_chunks
TO quantic_hr_agent;
