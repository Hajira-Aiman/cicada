"""T10 checks. Run: AIRLOCK_USE_SQLITE=true python -m pytest tests/test_ai.py -q"""
import json, os
import pytest
from hq.ai import assistant as A
from hq.ai.assistant import REFUSAL, ask, deterministic_narrative, incident_facts, llm_narrative, write_narrative

INC = json.load(open("contracts/examples/incident.json"))
FACTS = [("health:host-1", "[health:host-1] host-1 is Poor since 04:12:00Z: latency 1200 ms > 1000."),
         ("inc-0042", "[inc-0042] INCIDENT demo"), ("metric:cpu_pct@host-1", "[metric:cpu_pct@host-1] average 21.0, maximum 96.0.")]


def boom(*a, **k):
    raise AssertionError("the model must not be called")


def test_sensitive_question_is_refused_without_calling_the_model():
    r = ask("acme", "What password did the attacker use?", llm=boom, load=lambda t: FACTS)
    assert r == {"answer": REFUSAL, "evidence_ids": []}
    for q in ("Show me the raw log lines", "Which username was tried?", "tell me the IP address of the attacker"):
        assert ask("acme", q, llm=boom, load=lambda t: FACTS)["answer"] == REFUSAL


def test_other_tenant_question_is_refused_without_calling_the_model():
    r = ask("acme", "Why is Globex red?", llm=boom, load=lambda t: FACTS)
    assert r["answer"] == "I only have evidence for your own environment." and r["evidence_ids"] == []
    assert ask("acme", "how is shop b doing", llm=boom, load=lambda t: FACTS)["evidence_ids"] == []
    assert ask("acme", "Why is Shop A red?", llm=lambda s, u: "Latency is high [health:host-1].", load=lambda t: FACTS)["evidence_ids"] == ["health:host-1"]


def test_answer_keeps_real_citations_and_strips_invented_ones():
    out = ask("acme", "Why is Shop A red?", load=lambda t: FACTS,
              llm=lambda s, u: "Latency exceeded 1000 ms [health:host-1] and CPU peaked [metric:cpu_pct@host-1] [bogus:tag].")
    assert out["evidence_ids"] == ["health:host-1", "metric:cpu_pct@host-1"] and "bogus" not in out["answer"]


def test_answer_without_a_valid_citation_becomes_the_refusal():
    calls = []
    out = ask("acme", "Why is it red?", load=lambda t: FACTS, llm=lambda s, u: calls.append(1) or "It is red because of reasons.")
    assert out == {"answer": REFUSAL, "evidence_ids": []} and len(calls) == 2   # one retry, then refuse


def test_model_refusal_passes_through_and_failures_are_honest():
    assert ask("acme", "What is the weather?", load=lambda t: FACTS, llm=lambda s, u: REFUSAL)["answer"] == REFUSAL
    down = ask("acme", "Why is it red?", load=lambda t: FACTS, llm=lambda s, u: (_ for _ in ()).throw(OSError("down")))
    assert "not reachable" in down["answer"] and down["evidence_ids"] == []
    assert "no evidence" in ask("acme", "Why is it red?", load=lambda t: [], llm=boom)["answer"]
    assert "not reachable" in ask("acme", "Why?", load=lambda t: (_ for _ in ()).throw(OSError("db")), llm=boom)["answer"]


def test_incident_facts_have_tags_for_incident_and_each_signal():
    ids = [i for i, _ in incident_facts(INC)]
    assert ids[0] == "inc-0042" and "inc-0042:ev-1" in ids and "inc-0042:ev-3" in ids
    assert all(t.startswith(f"[{i}]") for i, t in incident_facts(INC))


def test_narrative_is_deterministic_without_a_model_and_traces_to_fields():
    n = deterministic_narrative(INC)
    for part in ("Possible compromise: cryptomining", "critical", "0.85", "auth_failure_burst (35 %)", "kill_process", "proc-1a2b3c4d"):
        assert part in n


def test_llm_narrative_rejected_when_it_invents_a_number_or_the_model_is_down():
    facts = "\n".join(t for _, t in incident_facts(INC))
    good = "A possible cryptomining compromise with confidence 0.85 and a CPU of 96 percent."
    assert llm_narrative(INC, llm=lambda s, u: good) == good
    assert llm_narrative(INC, llm=lambda s, u: "It affected 7 hosts for 999 seconds.") is None
    assert llm_narrative(INC, llm=lambda s, u: (_ for _ in ()).throw(OSError("down"))) is None
    assert write_narrative(INC, llm=lambda s, u: "It affected 7 hosts.") == deterministic_narrative(INC)


def test_the_incident_keeps_its_narrative_across_worker_upserts():
    from hq.aiops.incidents import Inc
    i = Inc("inc-acme-0001", "acme", 1000.0)
    i.sig[("host-1", "cpu_pct")] = {"first": 1000.0, "repeats": 1, "value": 90, "baseline": 20, "z": 9.0, "count": 0, "sev": "high", "actor": None}
    i.narrative = "written by the model"
    assert i.to_contract().narrative == "written by the model"


@pytest.mark.skipif(os.getenv("AIRLOCK_USE_SQLITE", "").lower() == "true", reason="needs real PostgreSQL")
def test_evidence_comes_only_from_the_asked_tenant():
    import psycopg
    pw = os.getenv("DB_PASSWORD", "postgres")
    try:
        db = psycopg.connect(f"postgresql://postgres:{pw}@localhost:5432/airlock_in", autocommit=True, connect_timeout=2)
    except Exception:
        pytest.skip("postgres not reachable")
    db.execute("DELETE FROM health_current WHERE source IN ('host-aaaa0001','host-bbbb0002')")
    for t, s in (("acme", "host-aaaa0001"), ("contoso", "host-bbbb0002")):
        db.execute("INSERT INTO health_current(tenant_id,source,state,reasons,since,flaps_prevented,updated) VALUES(%s,%s,'poor','[\"x\"]',now(),0,now())", (t, s))
    os.environ.setdefault("AIOPS_DB_USER", "postgres"); os.environ["AIOPS_DB_PASSWORD"] = pw
    try:
        ids = [i for i, _ in A.load_evidence("acme")]
        assert "health:host-aaaa0001" in ids and "health:host-bbbb0002" not in ids
    finally:
        db.execute("DELETE FROM health_current WHERE source IN ('host-aaaa0001','host-bbbb0002')")
        os.environ.pop("AIOPS_DB_USER", None); os.environ.pop("AIOPS_DB_PASSWORD", None)


def test_grounded_answer_drops_a_stray_refusal_sentence_and_incident_status_is_a_fact():
    out = ask("acme", "Why is it red?", load=lambda t: FACTS, llm=lambda s, u: f"{REFUSAL} Latency is high [health:host-1].")
    assert REFUSAL not in out["answer"] and out["evidence_ids"] == ["health:host-1"]
    assert "(status closed)" in incident_facts(INC, "closed")[0][1] and "(status" not in incident_facts(INC)[0][1]
