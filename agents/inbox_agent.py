from __future__ import annotations
import json
import base64
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import config


class InboxAgent:
    """
    Contract:
      Input:  days_back (int)
      Output: list of {id, subject, sender, date, body, snippet}
      Memory: reads processed_ids.json to skip already-seen emails
    """

    def __init__(self):
        self.service = self._build_service()
        self.processed_ids = self._load_processed_ids()

    def _build_service(self):
        creds = None
        if config.GMAIL_TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(
                str(config.GMAIL_TOKEN_PATH), config.GMAIL_SCOPES
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(config.GMAIL_CREDENTIALS_PATH), config.GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)
            config.GMAIL_TOKEN_PATH.write_text(creds.to_json())
        return build("gmail", "v1", credentials=creds)

    def _load_processed_ids(self) -> set:
        path = config.MEMORY_DIR / "processed_ids.json"
        return set(json.loads(path.read_text())) if path.exists() else set()

    def run(self, days_back: int = 1) -> list[dict]:
        since = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")

        # Union of explicit label + has:unsubscribe to catch unlabeled newsletters
        queries = [
            f"label:{config.GMAIL_NEWSLETTER_LABEL} after:{since}",
            f"has:unsubscribe after:{since}",
        ]

        seen = set()
        emails = []
        for query in queries:
            result = self.service.users().messages().list(
                userId="me", q=query, maxResults=100
            ).execute()
            for ref in result.get("messages", []):
                msg_id = ref["id"]
                if msg_id in seen or msg_id in self.processed_ids:
                    continue
                seen.add(msg_id)
                data = self._fetch(msg_id)
                if data:
                    emails.append(data)

        return emails

    def _fetch(self, msg_id: str) -> dict | None:
        try:
            msg = self.service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            return {
                "id": msg_id,
                "subject": headers.get("Subject", ""),
                "sender": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "body": self._extract_body(msg["payload"]),
                "snippet": msg.get("snippet", ""),
            }
        except Exception:
            return None

    def _extract_body(self, payload: dict) -> str:
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="replace")

        if "parts" in payload:
            plain = html = ""
            for part in payload["parts"]:
                mime = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace") if data else ""
                if mime == "text/plain":
                    plain = decoded
                elif mime == "text/html":
                    html = decoded
                elif "parts" in part:
                    sub = self._extract_body(part)
                    if sub:
                        plain = sub
            return plain or html
        return ""
