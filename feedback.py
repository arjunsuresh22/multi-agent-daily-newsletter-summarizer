#!/usr/bin/env python3
"""
Give feedback on a summary to calibrate future output for that sender.

Usage:
  python feedback.py "sender@example.com" "too much detail on links, focus on the main essay"
  python feedback.py "lenny@lenny.pm" "perfect depth on examples, keep this level"

Raw feedback is stored verbatim. Haiku distills it into calibration rules
that the Synthesizer reads on the next run — no re-reading of full feedback history.
"""
import json
import re
import argparse
import anthropic
import config

DISTILL_SYSTEM = (
    "Distill user feedback about newsletter summaries into JSON calibration rules. "
    "Output ONLY valid JSON with keys: "
    "detail_level (low/medium/high), preserve_examples (bool), "
    "follow_links (bool), research_paywalls (bool), notes (str one sentence)."
)


def distill(sender: str, raw_feedback: list[str]) -> dict:
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=DISTILL_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Sender: {sender}\nFeedback history:\n"
                + "\n".join(f"- {f}" for f in raw_feedback)
            ),
        }],
    )
    text = resp.content[0].text
    return json.loads(re.sub(r"```(?:json)?|```", "", text).strip())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("sender", help="Sender email address or name")
    p.add_argument("feedback", help="Your feedback in quotes")
    args = p.parse_args()

    # Append raw feedback
    fb_path = config.MEMORY_DIR / "user_feedback.json"
    all_fb = json.loads(fb_path.read_text()) if fb_path.exists() else {}
    all_fb.setdefault(args.sender, []).append(args.feedback)
    fb_path.write_text(json.dumps(all_fb, indent=2))

    # Re-distill calibration from full feedback history for this sender
    cal_path = config.MEMORY_DIR / "quality_calibration.json"
    cal = json.loads(cal_path.read_text()) if cal_path.exists() else {}
    cal[args.sender] = distill(args.sender, all_fb[args.sender])
    cal_path.write_text(json.dumps(cal, indent=2))

    print(f"Feedback saved.")
    print(f"Updated calibration for '{args.sender}': {json.dumps(cal[args.sender], indent=2)}")


if __name__ == "__main__":
    main()
