# Quantic development baseline — actual code and verification

This documents the consolidated baseline: local FastAPI/Vite/MCP spine plus the reusable CDK (create-new Aurora or Café Fausse reuse). Avoid treating this as deployed AWS.

## Project structure

```text
Quantic_HR_Agent/
├── .github/workflows/
│   ├── app.yml                 # CI Python+Postgres and React build
│   └── infrastructure.yml      # CI CDK build/test/synth
├── docs/                       # architecture, scope and findings
├── corpus/                     # currently synthetic policy examples
├── frontend/
│   ├── src/App.jsx             # React/Vite starter UI
│   ├── package.json            # npm dev/build/preview scripts
│   └── vite.config.js
├── src/quantic_hr/
│   ├── bff.py                  # FastAPI /health and /chat
│   ├── agent.py                # current local LangGraph scaffold (not Bedrock)
│   ├── mcp_server.py           # stdio MCP prototype
│   ├── db.py                   # configurable Postgres connection
│   └── tools.py                # synthetic prototype tools, NOT approved business stories
├── runtime/hello_world/        # AgentCore Hello World packaging and tests
├── infrastructure/
│   ├── bin/                    # CDK entrypoint
│   ├── lib/constructs/         # VPC, Aurora, IAM and AgentCore infrastructure
│   ├── scripts/                # predeploy and guarded deploy
│   ├── database/               # example migrations: NOT applied to AWS
│   ├── test/                   # CDK assertions
│   └── package.json            # build/test/synth scripts
├── scripts/
│   ├── local-db.sh             # local PostgreSQL helper
│   ├── apply_local_schema.py   # only local dev schema
│   ├── validate-baseline.sh    # offline application + infrastructure checks
│   └── start-local-app.sh      # local API starter
├── tests/                      # Python unit/integration tests
├── pyproject.toml
└── docker-compose.yml          # optional local Postgres
```

## Commands
Run from repo root. Requires Node 22+, npm, Python 3.12 and uv. For API tests, start the local PostgreSQL dev server, then set DATABASE_URL.

```bash
./scripts/local-db.sh start
export DATABASE_URL=postgresql://quantic@127.0.0.1:5433/quantic_hr
bash scripts/validate-baseline.sh
bash scripts/start-local-app.sh
# second terminal
npm --prefix frontend run dev
```

The React UI normally uses Vite on port 5173; FastAPI on 8000. See `.env.example`. Scripts are offline and do not deploy. React/FastAPI **code exists**; a shared public URL has **not** been verified.

## AWS services: explicit distinction
- **CDK definitions:** AWS Bedrock model permissions and AgentCore Hello World resource configured in CDK. These are not proof of live model invocation or running AgentCore.
- **Aurora:** PostgreSQL 17.4 cluster in Café Fausse exists but is stopped; proposed reuse of the same cluster. Creating `quantic_hr` inside it requires the writer to be running, database access and a separately approved operation. No schema decisions have been approved.
- **AgentCore:** A Hello World Python handler is present. No runtime has been deployed or invoked.
- **Bedrock:** IAM/model ARNs are in infrastructure code. Model access/inference have **not** been validated.
- **GitHub CI:** app and infrastructure workflows run offline checks; they do not deploy.
- **Deployment gate:** `deploy-sandbox.sh` requires `QUANTIC_ALLOW_AWS_DEPLOY=yes`. Do not deploy until costs and connectivity are approved.

## Gate before adding any business story
Review Quantic requirements as a group and approve one story, its acceptance criteria and data entities. Do not treat prototype MCP/HR logic as approved scope. Keep AWS infra changes, snapshot, starting or deleting existing clusters separate decisions.
