# syntax=docker/dockerfile:1
# Quantic HR agent for Amazon Bedrock AgentCore Runtime (HTTP protocol contract):
# linux/arm64, listens on 0.0.0.0:8080, POST /invocations, GET /ping.
# Build: docker buildx build --platform linux/arm64 -t quantic-hr-agent .
# CDK builds and pushes this image at deploy time (DockerImageAsset, LINUX_ARM64).
# No secrets or credentials are baked in: AWS access comes from the runtime role,
# the database from an IAM auth token generated at connect time.

FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src

FROM python:3.12-slim AS runtime
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QUANTIC_RUNTIME=agentcore \
    AWS_REGION=us-east-2
USER app
EXPOSE 8080
CMD ["uvicorn", "quantic_hr.bff:app", "--app-dir", "/app/src", "--host", "0.0.0.0", "--port", "8080"]
