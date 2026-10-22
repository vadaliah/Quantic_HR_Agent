# Design and evaluation

Cost-first local spine is in place: FastAPI BFF → LangGraph → stdio MCP → local Postgres/pgvector. AWS Aurora/AgentCore/Bedrock remain coded in CDK but are not deployed.

Evaluation (20–30 gold cases, ablation, latency) is the next increment after both demo workflows complete locally through MCP.
