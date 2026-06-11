#!/usr/bin/env python3
"""
One-time Gmail OAuth2 setup. Run this once before using run.py.

Steps:
  1. Go to console.cloud.google.com
  2. Create a project → Enable the Gmail API
  3. Create OAuth2 credentials (Desktop app) → Download as credentials.json
  4. Place credentials.json in this folder
  5. Run: python setup_oauth.py
  6. Authorize in the browser window that opens
  7. token.json is saved — you're done. run.py will use it automatically.
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import config


def main():
    if not config.GMAIL_CREDENTIALS_PATH.exists():
        print(f"ERROR: credentials.json not found at {config.GMAIL_CREDENTIALS_PATH}")
        print()
        print("To get it:")
        print("  1. Go to https://console.cloud.google.com")
        print("  2. Create a project → APIs & Services → Enable Gmail API")
        print("  3. APIs & Services → Credentials → Create OAuth client ID (Desktop app)")
        print("  4. Download JSON → rename to credentials.json → place in this folder")
        print("  5. Re-run this script")
        return

    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.GMAIL_CREDENTIALS_PATH), config.GMAIL_SCOPES
    )
    creds = flow.run_local_server(port=0)
    config.GMAIL_TOKEN_PATH.write_text(creds.to_json())
    print(f"✓ Token saved to {config.GMAIL_TOKEN_PATH}")
    print("You can now run:  python run.py")


if __name__ == "__main__":
    main()
