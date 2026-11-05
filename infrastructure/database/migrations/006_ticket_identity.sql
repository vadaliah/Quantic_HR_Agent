-- 006: Make tickets.ticket_id an identity column.
--
-- Why: 002 defined ticket_id as text with no default, so nothing could insert a
-- row without the application inventing an ID. create_mock_hr_ticket now lets
-- the database assign it.
--
-- Safe to apply while tickets is empty, which it is: nothing has inserted into
-- it yet. If rows existed, the cast below would fail loudly rather than
-- silently corrupt anything.
--
-- No BEGIN/COMMIT: the Data API runner owns the transaction.
-- Apply after 004, 005 and the seed.

ALTER TABLE tickets ALTER COLUMN ticket_id TYPE bigint USING ticket_id::bigint;
ALTER TABLE tickets ALTER COLUMN ticket_id ADD GENERATED ALWAYS AS IDENTITY;

-- 005 granted USAGE on the sequences that existed at the time. The identity
-- sequence is created here, so the runtime role needs it too.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO quantic_hr_agent;

-- The mock ticket flow never deletes or rewrites a row, so no other grant changes.
COMMENT ON COLUMN tickets.ticket_id IS 'Database-assigned identity. Mock records only.';
COMMENT ON COLUMN tickets.is_mock IS 'Always TRUE: no real HR system is touched.';
COMMENT ON COLUMN tickets.confirmed_by_user IS 'TRUE only when the user approved the action.';
