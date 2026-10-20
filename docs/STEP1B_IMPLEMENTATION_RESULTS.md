# Step 1B implementation results

**Status:** Code, local tests, and offline synth only. Nothing was deployed, started, or changed in AWS. Café Fausse and AEA stay as they were. **Stop here for deploy approval.**

## What was added

- `runtime/hello_world/` — stdlib HTTP AgentCore contract (`GET /ping`, `POST /invocations`). Returns `{ "message": "Hello World" }` and echoes `prompt`. No Bedrock, Aurora, MCP, or HR tools.
- `infrastructure/lib/constructs/hello-world-runtime.ts` — CDK `AWS::BedrockAgentCore::Runtime` named `QuanticHelloWorld`, `networkMode=VPC`, Python 3.12 direct code deploy.
- `infrastructure/scripts/predeploy-check.sh` and `check-availability-zones.ts` — identity, AZ IDs `use2-az1`/`use2-az2`, stack inventory, runtime list. No create/update.
- Deploy script now fails closed until those AZ IDs match.

SQL migrations from Step 1 are still **not executed**. No RAG index, no MCP server, no FastAPI/Vite work.

## Local verification

From this machine:

- `python3 -m unittest discover -s runtime/hello_world -p 'test_*.py'` — 4 passed
- `cd infrastructure && npm test` — 13 passed
- `npm run build` — passed
- `npm run synth -- --lookups false` — `QuanticHrAgentStack` includes one NAT, isolated Aurora `quantic_hr`, role `quantic-hr-agent-dev-runtime`, and runtime `QuanticHelloWorld` on private subnets

## Pre-deployment AWS checks (blocked)

`scripts/predeploy-check.sh` stopped at the read-only identity step:

```
aws: [ERROR]: The config profile (AEA-Sandbox-PowerUser) could not be found
```

Default credentials were also missing (`Unable to locate credentials`). Account `287238357427`, AZ IDs, live stack list, and `list-agent-runtimes` were **not** re-verified in this session. Re-run after `aws login` / profile restore:

```bash
cd infrastructure
bash scripts/predeploy-check.sh
```

Do not run `scripts/deploy-sandbox.sh` until that script finishes and this change set is approved.

## Safe deploy, after a separate approval

1. Restore profile `AEA-Sandbox-PowerUser` (or export credentials for account `287238357427`, region `us-east-2`).
2. Pass `scripts/predeploy-check.sh`.
3. Run `infrastructure/scripts/deploy-sandbox.sh` only if the printed change set is accepted. Type `QuanticHrAgentStack`, then `deploy`.
4. After create: do not start Aurora until a read-only `SELECT` on `pg_available_extensions`. Hello World invoke does not need the database.
5. Do not bootstrap a second CDKToolkit.

Estimated cost if left up is unchanged from Step 1 (NAT ~$33/month plus data, Aurora ~$44/month at 0.5 ACU while running, admin host a few dollars while running). The Hello World runtime itself has no extra reserved capacity; invoke and logs are usage-based. Rejecting deploy avoids all of that.

## Still unverified without approval

- Live AZ ID mapping for `us-east-2a` / `us-east-2b`
- End-to-end `InvokeAgentRuntime` against `QuanticHelloWorld`
- ENI placement in the new VPC
- `CREATE EXTENSION vector` and any HR/RAG path (out of scope for 1B)
