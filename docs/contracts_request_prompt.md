Read AGENTS.md first. I am Adithya (role A, AIOps and AI). My code (hq/aiops, hq/ai, tools/simulate.py) is built
against a DRAFT contract in contracts/models.py (pydantic v2, extra="forbid"). Please produce or confirm each item
below as files in contracts/, plus a short contracts/CHANGES.md listing every difference from my draft and why.
Do not change anything silently. Send me the whole contracts/ folder when done.

=== A. FROM THE GUARD OWNER (Hajira), needed by H2 ===
1. Payload airlock.v1: contracts/payload.schema.json + pydantic model, field for field:
   schema, payload_id, tenant_id, guard_id, seq, prev_hash, policy_version, sent_at,
   window{start,end,source_tz}, metrics[{name,source,avg,max}],
   events[{category,severity,source,actor,count,window_s}],
   log_patterns[{pattern_id,level,count,is_new}],
   health{guard_version,guard_cpu_pct,guard_mem_mb,buffer_depth,config_ok,canaries_planted,secrets_redacted}.
   Enums: 11 metric names, 13 event categories (incl. app_restarted, version_changed, config_changed, new_process),
   severities info..critical, pseudonym regex ^(host|src|user|proc)-[0-9a-f]{8}$.
2. Signing scheme. I assume: headers X-Guard-Id, X-Timestamp (UTC ISO Z), X-Signature = hex HMAC-SHA256 over
   (timestamp + "." + raw body bytes) with the per-guard secret. Confirm or give the exact scheme.
3. Registry: tenant IDs, guard IDs, region per tenant, source_tz, how per-guard secrets are provisioned.
   I assume: acme/guard-acme-01/in/Asia/Kolkata, globex/guard-globex-01/eu/Europe/Berlin,
   contoso/guard-contoso-01/in/Asia/Kolkata, phones tenant "guests".
4. How a pseudonym relates to a component: which `source` value is the host, and how the guard names services
   (shop-api, login, checkout, db) so my topology/damage map can match them. Is service state sent only as
   metric service_up, or also with a component label? (Schema has no component field today.)
5. Change events (app_restarted, version_changed, config_changed, new_process): confirm they travel as events with
   a `source`, and tell me by H12 when they are really emitted.
6. Examples: contracts/examples/payload.json (normal), plus one each for login burst, honeypot, power on battery,
   change event.

=== B. FROM THE HEAD-OFFICE OWNER (Sahiti), needed by H2 (shape) and H6 (running) ===
7. Ingest endpoint: URL path (I assume POST /ingest on :8001 India, :8002 Europe), response/receipt body
   {payload_id, sha256, received_at, status: stored|duplicate}, error codes (401 bad signature, 422 schema,
   403 wrong region), HTTP vs HTTPS and mkcert details for my simulator.
8. PostgreSQL table schemas I READ, per region database (airlock_in, airlock_eu): payloads, metrics, events,
   log_patterns, heartbeats. My draft columns:
   payloads(payload_id pk, tenant_id, guard_id, seq, window_start timestamptz, received_at timestamptz)
   metrics(payload_id, tenant_id, source, name, ts, avg, max)
   events(payload_id, tenant_id, source, category, severity, actor, count, window_s, ts)
   heartbeats(tenant_id, guard_id, ts, version, buffer_depth)
   Confirm names/types, that `ts` is window.start (event time), that received_at is arrival time, and that all
   rows of a payload are written in one transaction.
9. Tables I WRITE (please create or grant me): health_history, health_current, incidents (jsonb in the Incident
   shape + status/updated), alerts/raw_alert counters, tenant_thresholds(tenant_id, config jsonb),
   feedback(thumbs-down with who/when/alert id), topology(tenant_id, graph jsonb). Tell me if you want these
   names changed, and confirm row-level security does not block my worker (give it an engineer-level role).
10. Which DB user/role my worker uses, and whether it may read both region databases (it must; no data is copied
    across regions).
11. WebSocket messages hq-api pushes, with JSON examples: health_change, incident_opened, incident_updated,
    counters (raw alerts N -> incidents M, flaps prevented), latency meter. I assume my worker only writes
    to Postgres and hq-api pushes; confirm, or tell me to call an endpoint instead.
12. API endpoints I need: POST feedback (thumbs down: alert id, user), GET incident by id, POST /ai/chat
    (tenant from the login, question) that hq-api proxies to my hq/ai service, and the shape of the response
    (answer + evidence_ids[]).
13. Action intent shape that my incident `recommendation` feeds into (action, target pseudonym, risk, reversible,
    rollback, expiry, dry_run flag), so my recommendation fields map one-to-one. My allowed actions:
    kill_process, block_source, restart_service, investigate.
14. Chaos console: the exact scenario names and what each one injects, so the simulator and the real chaos agent
    produce the same signals (cpu_spike, latency, login_burst, outage, duplicates, out_of_order, kill_chain,
    backup_job, restart_app). Also whether chaos scenarios send a marker I can show in "alert delay".

=== C. FROM THE FRONTEND OWNER (Anisa), needed by H2 ===
15. Which incident and health fields the UI needs beyond my draft (e.g. repeat_count, suppressed_reason,
    changes_before, damage-map node list, formula text for the confidence hover). Say now so I add them before
    the freeze.
16. Whether the damage map wants a fixed per-tenant topology (nodes + edges + which metric lights a node), and
    the preferred JSON shape.

=== D. SHARED, frozen together at H2 ===
17. contracts/ports.md (all ports and machines), tenant/guard/region list, time rules (UTC Z everywhere,
    ordering by window.start), version number of the contract, and who may bump it.

For every item reply with: DONE (file path) / DIFFERENT (what changed) / NOT DECIDED (who decides, by when).
```
