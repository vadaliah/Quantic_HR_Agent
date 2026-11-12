# Deployed

Live: https://quantic-hr-agent-dcw4.onrender.com/ (Render free web service, 2026-11-12 ~00:58 CET, Europe/Berlin).

The service serves the UI and API and reads the existing `QuanticHrAgentStack` Aurora
database (`quantic_hr_agent`, us-east-2) through the RDS Data API. Bedrock provides chat
(Nova Pro) and embeddings (Titan v2). Steps and current checklist:
[docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md).

Done: IAM user `quantic-hr-render` with the least-privilege inline policy; one access key
(kept outside the repo); smoke tests passed (Nova Pro Converse, Titan v2, Data API reads);
Render Blueprint deployed at the URL above.

Smoke evidence (verified 2026-11-12 ~00:58 CET, Europe/Berlin):

- `/ping` 200 `{"status":"Healthy"}`.
- `/health` 200, `runtime=render`, `database.ok` true, `mode=data_api`,
  `chat_model=us.amazon.nova-pro-v1:0`, `embedding_model=amazon.titan-embed-text-v2:0`.
- `POST /chat` for E1007 "How many PTO days do I have left?" returned
  "10.9 PTO days left as of 2026-11-11 [POL-001 2.1]" via `check_pto_balance` in about 11 s.
- The remote-work question answered `mode=bedrock` with POL-003 citations in about 14 s.

Pending: AWS Budget alert.

In AWS today: `QuanticHrAgentStack` (Aurora Serverless v2 with live data, deletion protection
on) created 2026-11-03. Do not run `cdk deploy` from this branch.

Local BFF: `http://127.0.0.1:8000` (`/`, `/health`, `/chat`, `/ping`).
