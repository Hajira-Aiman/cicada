# Airlock rules for coding agents
- Read contracts/ before writing code. Never change contracts/ without telling the team; bump the version if you do.
- Python 3.11, FastAPI, pydantic v2 with extra="forbid" on every payload model. Vue 3 + ECharts for UI.
- All times are UTC ISO-8601 with Z. Every window also carries source_tz.
- Never send raw text, usernames, IPs, hostnames, paths or secrets from guard/ to hq/. Only fields in contracts/payload.schema.json.
- Every function that touches the network must time out, retry with backoff, and log what happened.
- Config comes from a .env per machine (ports, tenant, region URL, keys). No hard-coded IPs.
- Write a small test for every rule that protects privacy or prevents duplicates.
- Keep modules small; one file per concern. Explain non-obvious logic in a one-line comment.
- reference/ is read-only inspiration. Do not copy code from it; write our own.
