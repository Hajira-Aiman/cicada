"""T10: head-office AI assistant + incident narratives. Local Ollama (qwen2.5:7b) through the OpenAI client.

The model only ever sees evidence facts for ONE tenant, each with an ID tag. Rules are enforced in code, not trusted to the model:
  - questions asking for raw values (passwords, usernames, IPs, hostnames, log lines...) are refused before the model is called
  - questions about another tenant are refused before the model is called
  - the answer must cite real evidence IDs; invented tags are stripped; an answer with no valid citation becomes the refusal
Narratives are written when an incident opens: a deterministic text first (always available), an LLM rewrite after (kept only
if every number in it appears in the facts)."""
import os, re
from datetime import datetime, timezone

REFUSAL = "I don't have that, raw data stays in the customer's environment."
TENANT_REGION = {"acme": "in", "contoso": "in", "globex": "eu", "guests": "eu"}   # same as scripts/init_postgres.sql
SHOP_ALIAS = {"shop a": "acme", "shop b": "globex", "organizer": "contoso"}
SENSITIVE = re.compile(r"\b(passwords?|passwd|secrets?|tokens?|api[- ]?keys?|credentials?|usernames?|user names?|logins? names?|"
                       r"ip addresses?|ips?|hostnames?|host names?|raw logs?|log lines?|request bod(?:y|ies)|command lines?|file paths?|card numbers?)\b", re.I)
ASKING = re.compile(r"\b(what|which|who|show|give|tell|list|reveal|display|print|read|share)\b", re.I)
TAG = re.compile(r"\[([^\[\]]+)\]")
SYSTEM = ("You are the head-office assistant of an observability product. Answer ONLY from the evidence facts below. "
          "After every claim put the fact tag(s) in square brackets exactly as written, for example [health:host-1]. "
          f"If the evidence does not answer the question, reply exactly: {REFUSAL} "
          "Never guess and never mention anything that is not in the facts. Answer in at most 4 short sentences. "
          "Passwords, usernames, IP addresses, hostnames, file paths and log lines are not in the evidence and must never be stated.")


# ---------------------------------------------------------------- LLM ----
def llm_chat(system, user, timeout=90.0):
    """One call to the local model. Raises on any failure (callers fall back)."""
    from openai import OpenAI
    client = OpenAI(base_url=os.getenv("OLLAMA_URL", "http://localhost:11434/v1"), api_key="ollama", timeout=timeout)
    r = client.chat.completions.create(model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"), temperature=0.1,
                                       messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return (r.choices[0].message.content or "").strip()


# ----------------------------------------------------------- evidence ----
def _dsn(region):
    g = os.getenv
    return (f"postgresql://{g('AIOPS_DB_USER', 'aiops_worker')}:{g('AIOPS_DB_PASSWORD', 'aiops_secret_2026')}"
            f"@{g('DB_HOST', 'localhost')}:{g('DB_PORT', 5432)}/airlock_{region}")


def incident_facts(inc, status=None):
    """Facts for one incident dict (contract shape). IDs: <incident_id> and <incident_id>:ev-N."""
    iid, out = inc["incident_id"], []
    rec = inc.get("recommendation") or {}
    head = (f"[{iid}] INCIDENT {inc['title']}" + (f" (status {status})" if status else "") + f": severity {inc['severity']}, confidence {inc['confidence']}, started {inc['started_at']}, "
            f"affected {', '.join(inc.get('affected', []))}, seen {inc.get('repeat_count', 1)} time(s). "
            f"Reasoning: {'; '.join(inc.get('reasoning_path', []))}.")
    if inc.get("counterfactual"):
        head += f" Counterfactual: {inc['counterfactual']}."
    if rec:
        head += f" Recommended action: {rec['action']} on {rec.get('target') or 'n/a'} because {rec['why']} (risk {rec['risk']}, rollback: {rec.get('rollback') or 'n/a'})."
    if inc.get("changes_before"):
        head += f" Changes before: {'; '.join(inc['changes_before'])}."
    out.append((iid, head))
    for s in inc.get("signals", []):
        z = f", z {s['z']}" if s.get("z") is not None else ""
        out.append((f"{iid}:{s['evidence_id']}", f"[{iid}:{s['evidence_id']}] signal {s['name']}: value {s['value']}, baseline {s['baseline']}{z}, "
                                                  f"contribution {s['contribution_pct']} %."))
    return out


def load_evidence(tenant, minutes=10):
    """Evidence facts for ONE tenant from its regional database: incidents, health, alerts and a metric summary."""
    import psycopg
    facts = []   # [(id, text)]
    region = TENANT_REGION.get(tenant)
    if not region:
        return facts
    with psycopg.connect(_dsn(region), connect_timeout=5) as db:
        for body, status in db.execute("SELECT body,status FROM incidents WHERE tenant_id=%s ORDER BY updated_at DESC LIMIT 5", (tenant,)):
            facts += incident_facts(body if isinstance(body, dict) else __import__("json").loads(body), status)
        for src, state, reasons, since in db.execute("SELECT source,state,reasons,since FROM health_current WHERE tenant_id=%s ORDER BY source", (tenant,)):
            facts.append((f"health:{src}", f"[health:{src}] {src} is {state.capitalize()} since {since:%H:%M:%SZ}: {'; '.join(reasons or [])}."))
        for aid, title, sev, status, body in db.execute(
                "SELECT alert_id,title,severity,status,body FROM aiops_alerts WHERE tenant_id=%s AND updated_at > now() - interval '30 minutes' "
                "ORDER BY updated_at DESC LIMIT 5", (tenant,)):
            why = (body or {}).get("suppressed_reason") if isinstance(body, dict) else None
            facts.append((f"alert:{aid}", f"[alert:{aid}] alert '{title}' severity {sev}, status {status}." + (f" Reason: {why}." if why else "")))
        for src, name, avg, mx, n, last in db.execute(
                "SELECT source,name,avg(avg),max(max),count(*),(array_agg(avg ORDER BY event_time DESC))[1] FROM metrics "
                "WHERE tenant_id=%s AND event_time > now() - make_interval(mins => %s) GROUP BY source,name ORDER BY source,name", (tenant, minutes)):
            facts.append((f"metric:{name}@{src}", f"[metric:{name}@{src}] last {minutes} min: average {avg:.1f}, maximum {mx:.1f}, latest {last:.1f} ({n} windows)."))
    return facts


# ------------------------------------------------------------ guardrails ----
def blocked(tenant, question):
    """Returns a refusal text if the question must not reach the model, else None."""
    q = question.lower()
    for alias, owner in SHOP_ALIAS.items():
        if re.search(rf"\b{re.escape(alias)}\b", q) and owner != tenant and tenant in TENANT_REGION:
            return "I only have evidence for your own environment."
    for other in TENANT_REGION:
        if other != tenant and re.search(rf"\b{other}\b", q):
            return "I only have evidence for your own environment."
    if SENSITIVE.search(question) and ASKING.search(question):
        return REFUSAL
    return None


def ask(tenant, question, llm=llm_chat, load=load_evidence):
    """Returns {"answer", "evidence_ids"}. Never raises: failures become honest messages, never made-up answers."""
    why = blocked(tenant, question)
    if why:
        return {"answer": why, "evidence_ids": []}
    try:
        facts = load(tenant)
    except Exception:
        return {"answer": "The evidence store is not reachable right now, so I cannot answer.", "evidence_ids": []}
    if not facts:
        return {"answer": "I have no evidence for this environment yet.", "evidence_ids": []}
    ids = {i for i, _ in facts}
    user = "EVIDENCE FACTS:\n" + "\n".join(t for _, t in facts) + f"\n\nQUESTION: {question}"
    for attempt in range(2):
        try:
            text = llm(SYSTEM if attempt == 0 else SYSTEM + " You MUST cite at least one fact tag.", user)
        except Exception:
            return {"answer": "The AI model is not reachable right now, so I cannot answer.", "evidence_ids": []}
        cited = list(dict.fromkeys(t for t in TAG.findall(text) if t in ids))
        text = TAG.sub(lambda m: m.group(0) if m.group(1) in ids else "", text).replace("  ", " ").strip()
        if cited:   # a grounded answer must not also carry the refusal sentence
            text = text.replace(REFUSAL, "").strip()
            if len(TAG.sub("", text).strip()) < 8:   # only tags left (the model refused and cited): say what the evidence says
                text = " ".join(t for i, t in facts if i in cited[:2])
            return {"answer": text, "evidence_ids": cited}
        if REFUSAL in text:
            return {"answer": text, "evidence_ids": []}
    return {"answer": REFUSAL, "evidence_ids": []}   # could not ground the answer in evidence


# ------------------------------------------------------------ explain one alert / incident ----
# Small on purpose: a handful of facts (about 10 lines), because the local model has little VRAM and long contexts make it drift.
PARTS = ("what", "why", "serious", "next")
LABELS = {"what": "WHAT HAPPENED", "why": "WHY FLAGGED", "serious": "HOW SERIOUS", "next": "WHAT NEXT"}
SYSTEM_EXPLAIN = ("You explain one alert to an on-call engineer. Use ONLY the evidence facts below. Reply with exactly four lines, "
                  "each at most two short sentences, starting with these labels: WHAT HAPPENED: / WHY FLAGGED: / HOW SERIOUS: / WHAT NEXT: . "
                  "After every claim put the fact tag(s) in square brackets exactly as written, for example [alert:x]. "
                  "Do not add numbers, names or causes that are not in the facts, and do not describe sizes such as 'times higher' or 'orders of magnitude'. "
                  "Only call an event related when the facts show it within a minute of the alert. If the facts give no action, say to keep watching.")


def _metric_names(signals):
    return [s["name"] for s in signals if s.get("name") and not s["name"].startswith(("auth_", "login_", "honeypot", "service_", "log_"))][:3]


def _around(db, tenant, t, names, events=True):
    """Facts about what the metrics and events did just before / during / after time t (a datetime)."""
    out = []
    if names:
        for name, before, peak, latest in db.execute(
                "SELECT name, avg(avg) FILTER (WHERE event_time < %s), max(max) FILTER (WHERE event_time >= %s), "
                "(array_agg(avg ORDER BY event_time DESC))[1] FROM metrics WHERE tenant_id=%s AND name = ANY(%s) "
                "AND event_time >= %s - interval '5 minutes' AND event_time <= %s + interval '3 minutes' GROUP BY name", (t, t, tenant, names, t, t)):
            if before is not None and peak is not None:
                out.append((f"metric:{name}", f"[metric:{name}] {name} averaged {before:.1f} in the 5 minutes before, peaked at {peak:.1f} during, latest {latest:.1f}."))
    if events:
        for cat, n in db.execute("SELECT category, sum(count) FROM events WHERE tenant_id=%s AND event_time >= %s - interval '90 seconds' "
                                 "AND event_time <= %s + interval '30 seconds' AND category NOT IN ('secret_redacted','new_log_pattern') "
                                 "GROUP BY category ORDER BY sum(count) DESC LIMIT 3", (tenant, t, t)):
            out.append((f"event:{cat}", f"[event:{cat}] {cat}: {int(n)} occurrence(s) reported around that time."))
    return out


def _health(db, tenant):
    return [(f"health:{src}", f"[health:{src}] {src} is {state.capitalize()}: {'; '.join(reasons or [])}.")
            for src, state, reasons in db.execute("SELECT source,state,reasons FROM health_current WHERE tenant_id=%s AND state <> 'excellent' ORDER BY state DESC LIMIT 1", (tenant,))]


def _parts_from(head_id, title, severity, status, signals, rec, joined):
    sig = ", ".join(f"{s['name']} {s.get('value')} vs baseline {s.get('baseline')}" + (f" (z {s['z']})" if s.get("z") is not None else "") for s in signals[:3]) or "no signal detail"
    nxt = (f"{rec['action']} on {rec.get('target') or 'the affected system'} ({rec.get('why')}; risk {rec.get('risk')}, rollback: {rec.get('rollback') or 'n/a'})"
           if rec else (f"it belongs to incident {joined}: follow that card" if joined else "no action is recommended; keep watching it"))
    return {"what": f"{title} (status {status}).", "why": f"Signals: {sig}.", "serious": f"Severity {severity}.", "next": nxt.capitalize() + "."}, head_id


def explain_facts(tenant, kind, item_id):
    """(facts, deterministic four parts) for one alert or incident of ONE tenant, or None if it is not theirs / does not exist."""
    import json
    import psycopg
    region = TENANT_REGION.get(tenant)
    if not region:
        return None
    with psycopg.connect(_dsn(region), connect_timeout=5) as db:
        if kind == "incident":
            row = db.execute("SELECT body,status FROM incidents WHERE tenant_id=%s AND incident_id=%s", (tenant, item_id)).fetchone()
            if not row:
                return None
            body, status = (row[0] if isinstance(row[0], dict) else json.loads(row[0])), row[1]
            facts = incident_facts({**body, "signals": body.get("signals", [])[:4]}, status)
            t = datetime.fromisoformat(body["started_at"].replace("Z", "+00:00"))
            facts += _around(db, tenant, t, _metric_names(body.get("signals", [])))
            facts += _health(db, tenant)
            parts, _ = _parts_from(item_id, body["title"], body["severity"], status, body.get("signals", []), body.get("recommendation"), None)
            parts["serious"] = f"Severity {body['severity']}, confidence {body['confidence']}."
            return facts, parts
        row = db.execute("SELECT title,severity,status,body,created_at FROM aiops_alerts WHERE tenant_id=%s AND alert_id=%s", (tenant, item_id)).fetchone()
        if not row:
            return None
        title, sev, status, body, t = row
        body = body if isinstance(body, dict) else (json.loads(body) if body else {})
        signals = body.get("signals", []) if isinstance(body, dict) else []
        head = f"[alert:{item_id}] ALERT '{title}' kind {body.get('kind', 'security')}, severity {sev}, status {status}, opened {t:%H:%M:%SZ}."
        if body.get("suppressed_reason"):
            head += f" Suppressed: {body['suppressed_reason']}."
        facts = [(f"alert:{item_id}", head)]
        for s in signals[:3]:
            if s.get("name"):
                z = f", z {s['z']}" if s.get("z") is not None else ""
                facts.append((f"alert:{item_id}:{s['name']}", f"[alert:{item_id}:{s['name']}] signal {s['name']}: value {s.get('value')}, baseline {s.get('baseline')}{z}."))
        facts += _around(db, tenant, t, _metric_names(signals))
        joined = None
        inc = db.execute("SELECT incident_id, body, status FROM incidents WHERE tenant_id=%s AND started_at::timestamptz BETWEEN %s - interval '5 minutes' "
                         "AND %s + interval '5 minutes' ORDER BY updated_at DESC LIMIT 1", (tenant, t, t)).fetchone()
        rec = None
        if inc:
            ib = inc[1] if isinstance(inc[1], dict) else json.loads(inc[1])
            joined, rec = inc[0], ib.get("recommendation")
            facts.append((inc[0], incident_facts({**ib, "signals": []}, inc[2])[0][1]))
        facts += _health(db, tenant)
        parts, _ = _parts_from(item_id, title, sev, status, signals, rec, joined)
        return facts, parts


def _split_parts(text):
    """The four labelled lines of an answer, or None when one is missing."""
    found = {}
    for key, label in LABELS.items():
        m = re.search(rf"{label}\s*:\s*(.+?)(?=\s+(?:{'|'.join(LABELS.values())})\s*:|\Z)", text, re.S | re.I)
        if m:
            found[key] = m.group(1).strip()
    return found if len(found) == 4 else None


def explain(tenant, kind, item_id, llm=llm_chat, load=explain_facts):
    """{"parts": {what, why, serious, next}, "evidence_ids": [...], "source": "model" | "rules"}. Never raises.
    The model's answer is kept only if it has all four parts, cites real fact tags and adds no number that is not in the facts;
    otherwise the rules-based explanation (built straight from the same facts) is returned, so the button always answers."""
    try:
        loaded = load(tenant, kind, item_id)
    except Exception:
        return {"parts": None, "evidence_ids": [], "source": "error", "message": "The evidence store is not reachable right now."}
    if not loaded:
        return {"parts": None, "evidence_ids": [], "source": "error", "message": "That alert is not in your environment's evidence."}
    facts, rules = loaded
    ids = {i for i, _ in facts}
    allowed = _numbers("\n".join(t for _, t in facts))
    user = "EVIDENCE FACTS:\n" + "\n".join(t for _, t in facts) + "\n\nExplain this alert."
    try:
        text = llm(SYSTEM_EXPLAIN, user)
    except Exception:
        text = ""
    parts = _split_parts(text) if text else None
    cited = list(dict.fromkeys(t for t in TAG.findall(text) if t in ids)) if text else []
    if parts and cited and _numbers(text) <= allowed:
        parts = {k: TAG.sub(lambda m: m.group(0) if m.group(1) in ids else "", v).replace("  ", " ").strip() for k, v in parts.items()}
        return {"parts": parts, "evidence_ids": cited, "source": "model"}
    return {"parts": rules, "evidence_ids": [facts[0][0]], "source": "rules"}


# ------------------------------------------------------------ narratives ----
def deterministic_narrative(inc):
    """Plain text built only from the incident fields. Always available, so the card is never empty."""
    sigs = ", ".join(f"{s['name']} ({s['contribution_pct']:g} %)" for s in sorted(inc["signals"], key=lambda s: -s["contribution_pct"]))
    text = f"{inc['title']} (severity {inc['severity']}, confidence {inc['confidence']}). Started {inc['started_at']}. Signals: {sigs}."
    if inc.get("changes_before"):
        text += f" It {inc['changes_before'][0]}."
    if inc.get("counterfactual"):
        text += f" {inc['counterfactual']}."
    rec = inc.get("recommendation")
    if rec:
        text += f" Recommended: {rec['action']}" + (f" on {rec['target']}" if rec.get("target") else "") + f" ({rec['why']}; risk {rec['risk']})."
    return text


def _numbers(s):
    """Standalone numbers by value ("96" == "96.0"); digits inside identifiers or timestamps (host-7f3a, 04:10:02Z) do not count."""
    return {float(x) for x in re.findall(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])", s)}


def llm_narrative(inc, llm=llm_chat):
    """LLM rewrite of the narrative. Returns None unless every number in it appears in the incident facts."""
    facts = "\n".join(t for _, t in incident_facts(inc))
    sys_ = ("Write a 2 to 3 sentence incident summary for an on-call engineer. Use only the facts given. "
            "Do not add numbers, names, causes or advice that are not in the facts.")
    try:
        text = llm(sys_, facts)
    except Exception:
        return None
    return text if text and _numbers(text) <= _numbers(facts) else None


def write_narrative(inc, llm=llm_chat):
    return llm_narrative(inc, llm) or deterministic_narrative(inc)
