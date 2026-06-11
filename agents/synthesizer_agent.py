import json
import anthropic
from config import SYNTHESIZER_MODEL, MEMORY_DIR, MAX_EMAIL_BODY_CHARS
from .base_agent import run_agentic_loop

SYSTEM = """You are a newsletter synthesizer. Your job is NOT to compress — it is to preserve what matters.

CRITICAL RULE: Examples, stories, case studies, and specific instances must be kept with full narrative
context. The reader wants to feel they read the newsletter, not just heard about it.

OUTPUT FORMAT (strict markdown):
# {Newsletter Title} — {Date}
**Source:** {sender} | **Completeness:** {completeness}%

## TL;DR
- (3–5 bullets: what to actually take away)

## Examples & Stories
(For each example/story/case study: use a ### subheading, keep the full narrative. Do not compress.)

## Key Insights
(Distilled ideas — these can be compact)

## From the Links
(One ### subsection per fetched link. True summary: what is the takeaway from this link.)

## Research Fills
(Only include if paywalled. Independent research findings. Clearly label as research, not newsletter content.)

Omit any section that has no content."""


class SynthesizerAgent:
    """
    Contract:
      Input:  email, fetched_links[], research_findings{}, scout_report{}
      Output: markdown string (the final summary document)
      Memory: reads user_feedback.json (raw) + quality_calibration.json (distilled rules) per sender
    Orchestrator trims email body to MAX_EMAIL_BODY_CHARS before passing.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()

    def _memory_context(self, sender: str) -> str:
        parts = []
        fb_path = MEMORY_DIR / "user_feedback.json"
        cal_path = MEMORY_DIR / "quality_calibration.json"

        if fb_path.exists():
            feedback = json.loads(fb_path.read_text()).get(sender, [])
            if feedback:
                parts.append(
                    "Past user feedback for this sender (most recent 3):\n"
                    + "\n".join(f"- {f}" for f in feedback[-3:])
                )

        if cal_path.exists():
            cal = json.loads(cal_path.read_text()).get(sender, {})
            if cal:
                parts.append(f"Quality calibration rules: {json.dumps(cal)}")

        return "\n\n".join(parts)

    def run(
        self,
        email: dict,
        fetched_links: list[dict],
        research: dict,
        scout: dict,
    ) -> str:
        links_block = "\n\n".join(
            f"### {lc['title']}\nURL: {lc['url']}\n{lc['text']}"
            for lc in fetched_links
        )
        snippets = research.get("snippets", [])
        research_block = (
            "Web context (gap fill — use to supplement, not replace, newsletter content):\n"
            + "\n".join(f"- [{s['title']}]({s['url']}): {s['body']}" for s in snippets)
            if snippets else ""
        )

        parts = list(filter(bool, [
            f"Subject: {email['subject']}",
            f"Sender: {email['sender']}",
            f"Date: {email['date']}",
            f"Completeness: {scout.get('completeness', 100)}%",
            f"Content type: {scout.get('content_type', 'full')}",
            self._memory_context(email["sender"]),
            f"Newsletter body:\n{email['body'][:MAX_EMAIL_BODY_CHARS]}",
            f"Fetched links:\n{links_block}" if links_block else "",
            research_block,
        ]))

        messages = [{"role": "user", "content": "\n\n".join(parts)}]
        return run_agentic_loop(
            self.client, SYNTHESIZER_MODEL, SYSTEM, messages,
            tools=None, tool_executor=None, max_tokens=1500,
        )
