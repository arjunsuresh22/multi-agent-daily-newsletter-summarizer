from duckduckgo_search import DDGS
from config import PAYWALL_THRESHOLD


class ResearchAgent:
    """
    Contract:
      Input:  email dict + scout_report dict
      Output: {snippets: [{title, body, url}]}  — or {} if not needed
      Memory: none
    No LLM. One quick web search, top 3 snippets passed raw to Synthesizer.
    Fires only when paywalled or completeness < threshold.
    """

    def should_run(self, scout: dict) -> bool:
        return scout.get("is_paywalled") or scout.get("completeness", 100) < PAYWALL_THRESHOLD

    def run(self, email: dict, scout: dict) -> dict:
        if not self.should_run(scout):
            return {}

        query = f"{email['subject']} {scout.get('topic_summary', '')}".strip()
        try:
            results = list(DDGS(timeout=8).text(query, max_results=3))
            snippets = [{"title": r["title"], "body": r["body"], "url": r["href"]} for r in results]
            return {"snippets": snippets}
        except Exception:
            return {}
