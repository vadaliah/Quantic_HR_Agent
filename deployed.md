# Deployed

No public URL yet. Planned: one Render free web service (`render.yaml`) serving the UI and API,
reading the existing `QuanticHrAgentStack` Aurora database (`quantic_hr_agent`, us-east-2)
through the RDS Data API, with Bedrock for chat and embeddings. Steps:
[docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md).

What exists in AWS today: `QuanticHrAgentStack` (Aurora Serverless v2 with live data,
deletion protection on) created 2026-11-03. Do not run `cdk deploy` from this branch.

Local BFF: `http://127.0.0.1:8000` (`/`, `/health`, `/chat`, `/ping`).
