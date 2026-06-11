from __future__ import annotations
import re
import requests
import feedparser
import anthropic
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config import SYNTHESIZER_MODEL, MEMORY_DIR
from .base_agent import run_agentic_loop
from .reader_agent import ReaderAgent

SYSTEM = """You are a podcast summarizer. Given a full transcript, write a summary for someone who didn't listen.

CRITICAL RULE: Examples, stories, and specific instances must be written out in full with their context.
The reader wants the narrative — not just that a story was told.
Only skip filler, pleasantries, sponsor reads, and off-topic banter.

OUTPUT FORMAT (strict markdown):
# {Episode Title}
**Channel:** {channel} | **Date:** {date} | **Watch:** {url}

## TL;DR
- (3–5 bullets: key takeaways)

## Stories & Examples
(Each story/example gets a ### subheading. Write the full narrative with context. Do not compress.)

## Key Arguments
(Main points and frameworks — can be compact)

## Quotable Moments
(2–4 direct quotes with speaker attribution if known)

Omit sections with no content."""


class PodcastAgent:
    """
    Contract:
      Input:  channel_name, channel_url, days_back
      Output: list of {video_id, title, url, published, summary, channel}
      Memory: reads processed_ids.json to skip already-summarized episodes

    Single Sonnet call with full transcript — no chunking needed since a
    1.5hr podcast (~16K tokens) fits well within Sonnet's 200K context window.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.reader = ReaderAgent()
        self.processed = self._load_processed()

    def _load_processed(self) -> set:
        import json
        path = MEMORY_DIR / "processed_ids.json"
        return set(json.loads(path.read_text())) if path.exists() else set()

    def run(self, channel_name: str, channel_url: str, days_back: int = 7) -> list[dict]:
        channel_id = self._resolve_channel_id(channel_url)
        if not channel_id:
            print(f"    Could not resolve channel ID for {channel_url}")
            return []

        feed = feedparser.parse(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        )
        cutoff = datetime.now() - timedelta(days=days_back)
        results = []

        for entry in feed.entries:
            video_id = entry.get("yt_videoid")
            if not video_id or video_id in self.processed:
                continue
            published = datetime(*entry.published_parsed[:6])
            if published < cutoff:
                continue

            content = self.reader._fetch_transcript(video_id)
            if not content:
                continue

            print(f"     Transcript: {len(content['text']):,} chars")
            summary = self._summarize(
                channel_name,
                entry.get("title", video_id),
                published,
                f"https://www.youtube.com/watch?v={video_id}",
                content["text"],
            )
            results.append({
                "video_id": video_id,
                "title": entry.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published": published.isoformat(),
                "summary": summary,
                "channel": channel_name,
            })

        return results

    def _summarize(self, channel: str, title: str, published: datetime, url: str, transcript: str) -> str:
        messages = [{
            "role": "user",
            "content": (
                f"Channel: {channel}\n"
                f"Episode: {title}\n"
                f"Date: {published.strftime('%B %d, %Y')}\n"
                f"URL: {url}\n\n"
                f"Transcript:\n{transcript}"
            ),
        }]
        return run_agentic_loop(
            self.client, SYNTHESIZER_MODEL, SYSTEM, messages,
            tools=None, tool_executor=None, max_tokens=4096,
        )

    def _resolve_channel_id(self, channel_url: str) -> str | None:
        m = re.search(r"/channel/([^/?]+)", channel_url)
        if m:
            return m.group(1)
        try:
            resp = requests.get(channel_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")
            link = soup.find("link", {"rel": "canonical"})
            if link and "/channel/" in (link.get("href") or ""):
                return link["href"].split("/channel/")[-1]
        except Exception:
            pass
        return None
