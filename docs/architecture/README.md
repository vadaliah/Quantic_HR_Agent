# Architecture views

These Archify views describe the Quantic HR Agent at deploy-branch revision `f95840c` (14 Nov 2026), the revision documented as running on Render.

- **Current architecture (15 Nov 2026):** the live Render + Aurora + Bedrock application, including the eight MCP tools and the abstain fix.
- **Target architecture v4 (15 Nov 2026):** the same design with status cards updated to “live” (cold-start behaviour, health, and remaining follow-ups). It is a planned-vs-live architecture view, not a second deployed stack.

Open an HTML file in a browser for the interactive diagram; the PNG is a static snapshot of the same view.

The files were checked before they were added: they contain no access codes, credentials, or private-network details. They do name identifiers that are already in this repository (AWS account `287238357427`, IAM user `quantic-hr-render`, and the Secrets Manager secret name). They do not include secret values, access keys, or database passwords.

| View | Interactive HTML | PNG snapshot |
| --- | --- | --- |
| Current architecture (15 Nov 2026) | [hiren-quantic-hr-agent.architecture-2026-11-15.html](hiren-quantic-hr-agent.architecture-2026-11-15.html) | [hiren-quantic-hr-agent-2026-11-15-full.png](hiren-quantic-hr-agent-2026-11-15-full.png) |
| Target architecture v4 (15 Nov 2026, live) | [hiren-target-architecture-2026-11-15-v4.html](hiren-target-architecture-2026-11-15-v4.html) | [hiren-target-architecture-2026-11-15-v4.png](hiren-target-architecture-2026-11-15-v4.png) |

GitHub renders the PNG files inline. The HTML files are self-contained; download them and open them locally. They are not served as GitHub Pages from this repository.
