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
