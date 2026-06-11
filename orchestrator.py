from __future__ import annotations
from datetime import datetime
from agents.inbox_agent import InboxAgent
from agents.scout_agent import ScoutAgent
from agents.reader_agent import ReaderAgent
from agents.research_agent import ResearchAgent
from agents.synthesizer_agent import SynthesizerAgent
from agents.writer_agent import WriterAgent
from agents.podcast_agent import PodcastAgent
import config


class Orchestrator:
    """
    Pipeline:
      Newsletters: Inbox → filter priority → Scout → Reader → (Research?) → Synthesizer
      Podcasts:    PodcastAgent
      Final step:  WriterAgent assembles everything into one daily digest file.
    """

    def __init__(self):
        self.inbox = InboxAgent()
        self.scout = ScoutAgent()
        self.reader = ReaderAgent()
        self.research = ResearchAgent()
        self.synthesizer = SynthesizerAgent()
        self.writer = WriterAgent()
        self.podcast = PodcastAgent()

    def run(self, days_back: int = 1):
        newsletter_entries = self._run_newsletters(days_back)
        podcast_entries = self._run_podcasts(days_back)
        self._write_digest(newsletter_entries, podcast_entries)

    # ── Newsletter pipeline ───────────────────────────────────────────────

    def _is_priority(self, email: dict) -> bool:
        sender = email["sender"].lower()
        return any(
            pattern.lower() in sender
            for src in config.PRIORITY_SOURCES.values()
            for pattern in src["email_patterns"]
        )

    def _run_newsletters(self, days_back: int) -> list[dict]:
        print(f"\nFetching newsletters (last {days_back} day(s))...")
        emails = self.inbox.run(days_back=days_back)
        if not emails:
            print("No new newsletters.")
            return []

        priority = [e for e in emails if self._is_priority(e)]
        print(f"Found {len(emails)} total, {len(priority)} from priority sources.\n")
        if not priority:
            print("No priority newsletters today.")
            return []

        entries = []
        for i, email in enumerate(priority, 1):
            print(f"[{i}/{len(priority)}] {email['subject']} ★")
            print(f"    From: {email['sender']}")
            try:
                entry = self._process_newsletter(email)
                entries.append(entry)
            except Exception as e:
                print(f"  ✗ Skipped — {e}\n")

        return entries

    def _process_newsletter(self, email: dict) -> dict:
        print("  → Scouting...")
        scout = self.scout.run(email)
        print(f"     completeness={scout.get('completeness')}%  paywalled={scout.get('is_paywalled')}")

        print("  → Fetching links...")
        fetched = self.reader.run(scout.get("priority_links", []))
        print(f"     {len(fetched)} link(s) fetched")

        research = {}
        if self.research.should_run(scout):
            print("  → Researching (paywall gap)...")
            research = self.research.run(email, scout)

        print("  → Synthesizing...")
        trimmed = {**email, "body": email["body"][:config.MAX_EMAIL_BODY_CHARS]}
        summary = self.synthesizer.run(trimmed, fetched, research, scout)

        self.writer.mark_processed(email["id"])
        self.writer.update_profile(email["sender"], scout)
        print(f"  ✓ Done\n")

        return {
            "type": "newsletter",
            "sender": email["sender"],
            "subject": email["subject"],
            "summary": summary,
        }

    # ── Podcast pipeline ──────────────────────────────────────────────────

    def _run_podcasts(self, days_back: int) -> list[dict]:
        if not config.YOUTUBE_CHANNELS:
            return []
        print(f"Checking {len(config.YOUTUBE_CHANNELS)} YouTube channel(s)...\n")
        entries = []
        for source_id, channel_url in config.YOUTUBE_CHANNELS.items():
            name = config.PRIORITY_SOURCES[source_id]["name"]
            print(f"  → {name}")
            results = self.podcast.run(name, channel_url, days_back=days_back)
            if not results:
                print("     No new videos.\n")
                continue
            for result in results:
                self.writer.mark_processed(result["video_id"])
                entries.append({
                    "type": "podcast",
                    "channel": result["channel"],
                    "title": result["title"],
                    "url": result["url"],
                    "summary": result["summary"],
                })
                print(f"  ✓ {result['title']}\n")
        return entries

    # ── Daily digest ──────────────────────────────────────────────────────

    def _write_digest(self, newsletters: list[dict], podcasts: list[dict]):
        if not newsletters and not podcasts:
            print("Nothing to write.")
            return

        today = datetime.now().strftime("%B %d, %Y")
        date_slug = datetime.now().strftime("%Y-%m-%d")
        sections = [f"# Daily Digest — {today}\n"]

        if newsletters:
            sections.append("---\n")
            for entry in newsletters:
                sections.append(entry["summary"])
                sections.append("\n---\n")

        if podcasts:
            sections.append("\n# Podcasts\n")
            for entry in podcasts:
                sections.append(entry["summary"])
                sections.append("\n---\n")

        digest = "\n".join(sections)
        path = self.writer.save_digest(digest, date_slug)
        print(f"\nDigest saved → {path}")
