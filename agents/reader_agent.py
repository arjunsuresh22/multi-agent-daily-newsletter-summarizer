from __future__ import annotations
import re
import json
import subprocess
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import IpBlocked, TranscriptsDisabled
from config import MAX_LINK_TEXT_CHARS, BASE_DIR

COOKIES_FILE = BASE_DIR / "youtube_cookies.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class ReaderAgent:
    """
    Contract:
      Input:  priority_links[] from ScoutAgent [{url, reason, importance}]
      Output: [{url, title, text, type: "youtube"|"web"}]
      Memory: none — stateless fetcher
    Skips low-importance links to save downstream token cost.
    YouTube links → transcript API. All others → BeautifulSoup scrape.
    """

    def run(self, links: list[dict]) -> list[dict]:
        results = []
        for link in links:
            if link.get("importance") == "low":
                continue
            video_id = self._youtube_id(link["url"])
            content = (
                self._fetch_transcript(video_id)
                if video_id
                else self._fetch_web(link["url"])
            )
            if content:
                results.append({
                    "url": link["url"],
                    "reason": link.get("reason", ""),
                    "title": content["title"],
                    "text": content["text"],
                    "type": "youtube" if video_id else "web",
                })
        return results

    def _youtube_id(self, url: str) -> str | None:
        for pattern in [
            r"youtube\.com/watch\?v=([^&\s]+)",
            r"youtu\.be/([^?\s]+)",
            r"youtube\.com/embed/([^?\s]+)",
        ]:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def _make_api(self):
        if COOKIES_FILE.exists():
            import requests as req
            from http.cookiejar import MozillaCookieJar
            session = req.Session()
            jar = MozillaCookieJar(str(COOKIES_FILE))
            jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies = jar
            return YouTubeTranscriptApi(http_client=session)
        return YouTubeTranscriptApi()

    def _transcript_cache_path(self, video_id: str) -> Path:
        return Path(f"/tmp/transcript_{video_id}.txt")

    def _fetch_transcript(self, video_id: str) -> dict | None:
        cache = self._transcript_cache_path(video_id)
        if cache.exists():
            print("     [transcript cache hit]")
            return {"title": f"YouTube video: {video_id}", "text": cache.read_text()}
        try:
            api = self._make_api()
            transcript = api.fetch(video_id)
            text = " ".join(s.text for s in transcript)
            cache.write_text(text)
            return {"title": f"YouTube video: {video_id}", "text": text}
        except (IpBlocked, TranscriptsDisabled):
            print("     [transcript-api blocked] falling back to yt-dlp...")
            return self._fetch_transcript_ytdlp(video_id)
        except Exception:
            return None

    def _fetch_transcript_ytdlp(self, video_id: str) -> dict | None:
        try:
            cmd = [
                "python3", "-m", "yt_dlp",
                "--skip-download",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "json3",
                "--print-json",
                "-o", "/tmp/yt-dlp-%(id)s",
            ]
            if COOKIES_FILE.exists():
                cmd += ["--cookies", str(COOKIES_FILE)]
            cmd.append(f"https://www.youtube.com/watch?v={video_id}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            title = video_id
            for line in result.stdout.splitlines():
                try:
                    meta = json.loads(line)
                    title = meta.get("title", video_id)
                    break
                except json.JSONDecodeError:
                    continue

            import glob, os
            sub_files = glob.glob(f"/tmp/yt-dlp-{video_id}*.json3")
            if not sub_files:
                return None
            sub_data = json.loads(open(sub_files[0]).read())
            words = []
            for event in sub_data.get("events", []):
                for seg in event.get("segs", []):
                    w = seg.get("utf8", "").strip()
                    if w and w != "\n":
                        words.append(w)
            for f in sub_files:
                os.remove(f)
            text = " ".join(words)
            if text:
                self._transcript_cache_path(video_id).write_text(text)
            return {"title": title, "text": text} if text else None
        except Exception as e:
            print(f"     [yt-dlp fallback failed] {e}")
            return None

    def _fetch_web(self, url: str) -> dict | None:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()
            title = soup.title.string.strip() if soup.title else url
            source = (
                soup.find("article")
                or soup.find(class_=["post-content", "entry-content", "article-body"])
                or soup.find("main")
                or soup
            )
            text = " ".join(source.get_text(separator=" ").split())
            return {"title": title, "text": text[:MAX_LINK_TEXT_CHARS]}
        except Exception:
            return None
