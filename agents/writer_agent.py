import json
import re
from datetime import datetime
from config import MEMORY_DIR, SUMMARIES_DIR


class WriterAgent:
    """
    Contract:
      - mark_processed(id)         — dedup log
      - update_profile(sender, scout) — sender learning
      - save_digest(content, date) — writes the single daily file
    No LLM — pure bookkeeping and file I/O.
    """

    def save_digest(self, content: str, date_slug: str) -> str:
        path = SUMMARIES_DIR / f"{date_slug}_digest.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def mark_processed(self, item_id: str):
        path = MEMORY_DIR / "processed_ids.json"
        ids = json.loads(path.read_text()) if path.exists() else []
        if item_id not in ids:
            ids.append(item_id)
        path.write_text(json.dumps(ids, indent=2))

    def update_profile(self, sender: str, scout: dict):
        path = MEMORY_DIR / "sender_profiles.json"
        profiles = json.loads(path.read_text()) if path.exists() else {}
        p = profiles.get(sender, {"run_count": 0})
        p["run_count"] = p.get("run_count", 0) + 1
        p["last_seen"] = datetime.now().isoformat()
        prev = p.get("typical_completeness", scout.get("completeness", 100))
        p["typical_completeness"] = round((prev + scout.get("completeness", 100)) / 2, 1)
        p["content_type"] = scout.get("content_type", "full")
        profiles[sender] = p
        path.write_text(json.dumps(profiles, indent=2))

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
