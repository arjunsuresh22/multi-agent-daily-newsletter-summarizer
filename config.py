import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
MEMORY_DIR = BASE_DIR / "memory"
SUMMARIES_DIR = BASE_DIR / "summaries"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GMAIL_CREDENTIALS_PATH = BASE_DIR / "credentials.json"
GMAIL_TOKEN_PATH = BASE_DIR / "token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_NEWSLETTER_LABEL = os.getenv("GMAIL_NEWSLETTER_LABEL", "Newsletters")
DAYS_BACK = int(os.getenv("DAYS_BACK", "1"))

SCOUT_MODEL = "claude-haiku-4-5-20251001"
RESEARCH_MODEL = "claude-sonnet-4-6"
SYNTHESIZER_MODEL = "claude-sonnet-4-6"

PAYWALL_THRESHOLD = 60     # completeness % below which Research Agent fires
MAX_LINK_TEXT_CHARS = 1500
MAX_EMAIL_BODY_CHARS = 5000

# Priority sources — always processed even if not labeled in Gmail
PRIORITY_SOURCES = {
    "a16z": {
        "name": "a16z",
        "email_patterns": ["@a16z.com", "a16z"],
        "youtube_channel": None,
    },
    "lennys_newsletter": {
        "name": "Lenny's Newsletter",
        "email_patterns": ["lenny@substack.com", "lenny@lenny.pm", "lennys-newsletter", "lenny.substack"],
        "youtube_channel": None,
    },
    "lennys_podcast": {
        "name": "Lenny's Podcast",
        "email_patterns": [],
        "youtube_channel": "https://www.youtube.com/channel/UC6t1O76G0jYXOAoYCm153dA",
    },
    "chamath": {
        "name": "Chamath Palihapitiya",
        "email_patterns": ["chamath", "socialcapital"],
        "youtube_channel": None,
    },
    "nates_substack": {
        "name": "Nate's Substack",
        "email_patterns": ["natesnewsletter@substack.com", "natesnewsletter"],
        "youtube_channel": None,
    },
    "alpha_signal": {
        "name": "Alpha Signal",
        "email_patterns": ["alphasignal.ai", "alphasignal", "alpha-signal"],
        "youtube_channel": None,
    },
    "aishwarya": {
        "name": "Aishwarya Srinivasan",
        "email_patterns": ["aishwarya", "thegenacademy.com"],
        "youtube_channel": None,
    },
    "semi_analysis": {
        "name": "Semi-Analysis",
        "email_patterns": ["semianalysis", "semi-analysis"],
        "youtube_channel": None,
    },
}

YOUTUBE_CHANNELS = {
    sid: src["youtube_channel"]
    for sid, src in PRIORITY_SOURCES.items()
    if src["youtube_channel"]
}
