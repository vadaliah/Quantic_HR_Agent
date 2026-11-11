# Deployed

**Not live yet** (2026-11-12 ~00:10 CET). There is no public URL.

Planned: one Render free web service (`render.yaml`) that serves the UI and API and reads the
existing `QuanticHrAgentStack` Aurora database (`quantic_hr_agent`, us-east-2) through the RDS
Data API. Bedrock provides chat (Nova Pro) and embeddings (Titan v2). Steps and current checklist:
[docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md).

Done: IAM user `quantic-hr-render` with the least-privilege inline policy; one access key
(kept outside the repo); smoke tests passed (Nova Pro Converse, Titan v2, Data API reads).
Pending: AWS Budget alert, Render Blueprint, live URL, `/health` URL, measured cold start.

In AWS today: `QuanticHrAgentStack` (Aurora Serverless v2 with live data, deletion protection
on) created 2026-11-03. Do not run `cdk deploy` from this branch.

Local BFF: `http://127.0.0.1:8000` (`/`, `/health`, `/chat`, `/ping`).
