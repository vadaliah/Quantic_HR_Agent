-- 012: Prompt-level tracking for agent runs.
-- Keyed by prompt_id, which is also returned to the client, so one transaction
-- can be reconstructed: trace, tool calls, citations, latency.
-- No BEGIN/COMMIT: the Data API runner owns the transaction.

ALTER TABLE agent_runs RENAME COLUMN run_id TO prompt_id;
ALTER TABLE agent_runs ALTER COLUMN prompt_id TYPE text USING prompt_id::text;

ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS route text;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tool_names text;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS step_count integer;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS model text;

CREATE INDEX IF NOT EXISTS agent_runs_prompt_idx ON agent_runs (prompt_id);
CREATE INDEX IF NOT EXISTS agent_runs_route_idx ON agent_runs (route);
CREATE INDEX IF NOT EXISTS agent_runs_created_idx ON agent_runs (created_at DESC);
