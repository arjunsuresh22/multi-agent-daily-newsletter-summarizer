import json
import re
import anthropic
from config import SCOUT_MODEL, MEMORY_DIR
from .base_agent import run_agentic_loop

SYSTEM = """You are a newsletter scout. Given an email, output a JSON object with exactly these keys:
- is_paywalled: bool (true if content is cut off or behind a subscription prompt)
- completeness: int 0-100 (how complete the content feels; 100 = full article present)
- content_type: "full" | "teaser" | "partial"
- priority_links: list of {url, reason, importance: "high"|"medium"|"low"}
  Include only: article links, referenced studies, named examples, key resources.
  Exclude: unsubscribe, tracking, pixel, email-open, social share links.
- topic_summary: str (2 sentences max on what this newsletter is about)
Output ONLY valid JSON. No markdown fences."""


class ScoutAgent:
    """
    Contract:
      Input:  email dict (uses subject, sender, body[:3000])
      Output: {is_paywalled, completeness, content_type, priority_links[], topic_summary}
      Memory: reads sender_profiles.json for known-sender context (saves tokens on repeat senders)
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        self._profiles = self._load_profiles()

    def _load_profiles(self) -> dict:
        path = MEMORY_DIR / "sender_profiles.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def run(self, email: dict) -> dict:
        profile = self._profiles.get(email["sender"], {})
        context = f"Known sender profile: {json.dumps(profile)}\n\n" if profile else ""

        messages = [{
            "role": "user",
            "content": (
                f"{context}"
                f"Subject: {email['subject']}\n"
                f"Sender: {email['sender']}\n\n"
                f"{email['body'][:3000]}"
            ),
        }]

        raw = run_agentic_loop(
            self.client, SCOUT_MODEL, SYSTEM, messages,
            tools=None, tool_executor=None, max_tokens=512,
        )

        try:
            return json.loads(re.sub(r"```(?:json)?|```", "", raw).strip())
        except json.JSONDecodeError:
            return {
                "is_paywalled": False,
                "completeness": 80,
                "content_type": "full",
                "priority_links": self._fallback_links(email["body"]),
                "topic_summary": email.get("snippet", ""),
            }

    def _fallback_links(self, body: str) -> list[dict]:
        skip = {"unsubscribe", "tracking", "pixel", "open.php", "click.php", "mailchimp", "sendgrid"}
        urls = re.findall(r'https?://[^\s<>"]+', body)
        return [
            {"url": u, "reason": "extracted", "importance": "medium"}
            for u in urls[:5]
            if not any(s in u.lower() for s in skip)
        ]
