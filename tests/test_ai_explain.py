"""Explain one alert: the model's answer is kept only when it is grounded; otherwise the rules-based explanation answers."""
from hq.ai.assistant import explain

FACTS = [("alert:a1", "[alert:a1] ALERT 'CPU usage spike' kind usage_spike, severity info, status open, opened 04:10:00Z."),
         ("metric:cpu_pct", "[metric:cpu_pct] cpu_pct averaged 9.0 in the 5 minutes before, peaked at 72.0 during, latest 15.0.")]
RULES = {"what": "CPU usage spike (status open).", "why": "Signals: cpu_pct 72.0 vs baseline 9.0.", "serious": "Severity info.", "next": "No action is recommended; keep watching it."}
load = lambda tenant, kind, item_id: (FACTS, RULES)
GOOD = ("WHAT HAPPENED: CPU rose from 9.0 to 72.0 [metric:cpu_pct].\nWHY FLAGGED: It left its normal band [alert:a1].\n"
        "HOW SERIOUS: Info only [alert:a1].\nWHAT NEXT: Keep watching it [alert:a1].")


def test_a_grounded_four_part_answer_is_kept():
    out = explain("acme", "alert", "a1", llm=lambda s, u: GOOD, load=load)
    assert out["source"] == "model" and set(out["parts"]) == {"what", "why", "serious", "next"}
    assert out["evidence_ids"] == ["metric:cpu_pct", "alert:a1"]


def test_an_invented_number_falls_back_to_rules():
    bad = GOOD.replace("72.0 [", "97.0 [")   # 97.0 is not in the facts
    out = explain("acme", "alert", "a1", llm=lambda s, u: bad, load=load)
    assert out["source"] == "rules" and out["parts"] == RULES


def test_missing_parts_or_no_citation_fall_back_and_a_dead_model_still_answers():
    assert explain("acme", "alert", "a1", llm=lambda s, u: "WHAT HAPPENED: something.", load=load)["source"] == "rules"
    assert explain("acme", "alert", "a1", llm=lambda s, u: GOOD.replace("[alert:a1]", "").replace("[metric:cpu_pct]", ""), load=load)["source"] == "rules"

    def down(s, u):
        raise RuntimeError("ollama is not running")
    out = explain("acme", "alert", "a1", llm=down, load=load)
    assert out["source"] == "rules" and out["parts"]["next"].startswith("No action")


def test_an_item_that_is_not_theirs_is_refused():
    out = explain("acme", "alert", "someone-elses", llm=lambda s, u: GOOD, load=lambda *a: None)
    assert out["parts"] is None and "not in your environment" in out["message"]


def test_a_one_line_answer_is_still_split_into_four_parts():
    one_line = GOOD.replace("\n", " ")
    out = explain("acme", "alert", "a1", llm=lambda s, u: one_line, load=load)
    assert out["source"] == "model" and out["parts"]["what"].startswith("CPU rose") and out["parts"]["next"].startswith("Keep watching")
