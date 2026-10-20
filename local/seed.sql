-- Idempotent synthetic data for local Postgres. No AWS.

INSERT INTO locations (location_id, name, region, remote_eligible) VALUES
  ('LOC-NY', 'New York Office', 'US-NY', true),
  ('LOC-OH', 'Columbus Office', 'US-OH', false)
ON CONFLICT (location_id) DO UPDATE SET
  name = EXCLUDED.name,
  region = EXCLUDED.region,
  remote_eligible = EXCLUDED.remote_eligible;

INSERT INTO employees (employee_id, display_name, email, location_id, manager_id, employment_type) VALUES
  ('E001', 'Amina Cole', 'amina.cole@example.com', 'LOC-NY', 'E003', 'full_time'),
  ('E002', 'Ben Ortiz', 'ben.ortiz@example.com', 'LOC-OH', 'E003', 'full_time'),
  ('E003', 'Priya Shah', 'priya.shah@example.com', 'LOC-NY', NULL, 'full_time')
ON CONFLICT (employee_id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  email = EXCLUDED.email,
  location_id = EXCLUDED.location_id,
  manager_id = EXCLUDED.manager_id,
  employment_type = EXCLUDED.employment_type;

INSERT INTO managers (employee_id, manager_id) VALUES
  ('E001', 'E003'),
  ('E002', 'E003')
ON CONFLICT (employee_id) DO UPDATE SET manager_id = EXCLUDED.manager_id;

INSERT INTO pto_balances (employee_id, annual_hours, used_hours, pending_hours) VALUES
  ('E001', 160, 24, 8),
  ('E002', 80, 72, 8),
  ('E003', 160, 8, 0)
ON CONFLICT (employee_id) DO UPDATE SET
  annual_hours = EXCLUDED.annual_hours,
  used_hours = EXCLUDED.used_hours,
  pending_hours = EXCLUDED.pending_hours;

INSERT INTO policy_documents (document_id, title, source_uri) VALUES
  ('remote-work-policy', 'Remote Work Eligibility Policy', 'corpus/remote-work-policy.md'),
  ('pto-policy', 'Paid Time Off Policy', 'corpus/pto-policy.md'),
  ('holiday-calendar', 'Company Holiday Calendar', 'corpus/holiday-calendar.html')
ON CONFLICT (document_id) DO UPDATE SET
  title = EXCLUDED.title,
  source_uri = EXCLUDED.source_uri;

INSERT INTO policy_chunks (chunk_id, document_id, section_id, heading, content) VALUES
  ('remote-eligibility', 'remote-work-policy', 'eligibility', 'Eligibility',
   'Full-time employees assigned to a remote-eligible office may work from another US state in the same region after manager acknowledgment. Columbus is not remote-eligible.'),
  ('remote-security', 'remote-work-policy', 'security', 'Security',
   'Remote workers must use company SSO, full-disk encryption, and must not process HR records on personal email.'),
  ('pto-accrual', 'pto-policy', 'accrual', 'Accrual',
   'Full-time employees accrue paid time off annually. Requests must not exceed remaining hours (annual minus used minus pending).'),
  ('pto-notice', 'pto-policy', 'notice', 'Notice',
   'PTO of eight hours or more should be requested at least five business days in advance except for documented emergencies.'),
  ('holiday-list', 'holiday-calendar', 'us-holidays', 'US Holidays',
   'The company observes New Year''s Day, Memorial Day, Independence Day, Labor Day, Thanksgiving, and Christmas Day. These days do not debit PTO.')
ON CONFLICT (chunk_id) DO UPDATE SET
  document_id = EXCLUDED.document_id,
  section_id = EXCLUDED.section_id,
  heading = EXCLUDED.heading,
  content = EXCLUDED.content;
