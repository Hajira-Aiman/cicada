"""
guard/log_patterns.py
Drain3 log-pattern mining (PRD #3): every scrubbed log line becomes a pattern id (tpl-xxxx) with a level; only
{pattern_id, level, count, is_new} leave the guard, never the pattern text. Without the drain3 package the guard keeps
working and simply sends no patterns.
"""
import json
import logging
from typing import Dict, List, Set, Tuple

from contracts.models import LogPatternSample

logger = logging.getLogger("airlock.guard.patterns")
LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
MAX_PER_WINDOW = 20


class PatternMiner:
    def __init__(self):
        self.miner = None
        self.counts: Dict[Tuple[str, str], int] = {}
        self.seen: Set[str] = set()
        self.new: Set[str] = set()
        try:
            from drain3 import TemplateMiner
            from drain3.masking import MaskingInstruction
            from drain3.template_miner_config import TemplateMinerConfig

            cfg = TemplateMinerConfig()
            cfg.masking_instructions = [MaskingInstruction(r"\d+(\.\d+)*", "NUM")]   # ids, ports, counts, timestamps collapse
            cfg.profiling_enabled = False
            self.miner = TemplateMiner(config=cfg)
        except Exception as exc:   # package missing or incompatible
            logger.warning(f"Drain3 unavailable, log patterns disabled: {exc}")

    def add(self, scrubbed_line: str) -> None:
        """Mine one already-scrubbed line (JSON lines contribute their message and level; anything else is mined as text)."""
        if self.miner is None:
            return
        text, level = scrubbed_line, "INFO"
        try:
            obj = json.loads(scrubbed_line)
            if isinstance(obj, dict):
                text = str(obj.get("message") or obj.get("event") or scrubbed_line)
                level = str(obj.get("level", "INFO")).upper()
        except ValueError:
            pass
        if level == "WARN":
            level = "WARNING"
        if level not in LEVELS:
            level = "INFO"
        pid = "tpl-%04x" % self.miner.add_log_message(text)["cluster_id"]
        self.counts[(pid, level)] = self.counts.get((pid, level), 0) + 1
        if pid not in self.seen:
            self.seen.add(pid)
            self.new.add(pid)

    def drain(self) -> List[LogPatternSample]:
        """Counts since the last call as payload samples, busiest first."""
        out = [
            LogPatternSample(pattern_id=pid, level=level, count=n, is_new=pid in self.new)
            for (pid, level), n in sorted(self.counts.items(), key=lambda kv: -kv[1])[:MAX_PER_WINDOW]
        ]
        self.counts.clear()
        self.new.clear()
        return out
