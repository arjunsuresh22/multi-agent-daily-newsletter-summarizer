# Daily Newsletter Summarizer — Multi-Agent Pipeline

A multi-agent AI pipeline that reads your Gmail newsletters and YouTube podcast transcripts, summarizes them with full narrative fidelity, and produces a single daily digest. Built with the Anthropic SDK, Gmail API, and YouTube Transcript API.

---

## Motivation

Imagine asking a single AI agent to go through your inbox and summarize each newsletter. The agent reads emails one at a time using tool calls — fetch email 1, summarize it, fetch email 2, summarize it, and so on. This feels natural. But here is what is actually happening to your bill.

Every time the agent makes an API call to read the next email, the **entire conversation history is sent again**. The context is cumulative. By the time the agent reaches email 6, the API call carries emails 1 through 5 in its history plus email 6 — and you pay for all of them again:

```
API call 1 — read email 1:
  context = [email 1 body + link]              = 10,000 tokens  → $0.030

API call 2 — read email 2:
  context = [email 1 + email 2 + their links]  = 20,000 tokens  → $0.060
                                                  ↑
                                        you already paid for
                                        email 1 in call 1,
                                        and you're paying for it again

API call 3 — read email 3:
  context = [emails 1–3 + all links]           = 30,000 tokens  → $0.090

API call 4 — read email 4:
  context = [emails 1–4 + all links]           = 40,000 tokens  → $0.120

API call 5 — read email 5:
  context = [emails 1–5 + all links]           = 50,000 tokens  → $0.150

API call 6 — read email 6:
  context = [emails 1–6 + all links]           = 60,000 tokens  → $0.180

API call 7 — read email 7:
  context = [emails 1–7 + all links]           = 70,000 tokens  → $0.210

API call 8 — read email 8:
  context = [emails 1–8 + all links]           = 80,000 tokens  → $0.240
                                                ─────────────────────────
Total tokens billed:  10K+20K+30K+40K+50K+60K+70K+80K = 360,000 tokens
Total cost:                                                       $1.08
```

You paid for email 1 eight times. Email 2 seven times. The cost does not grow linearly with the number of emails — it grows **quadratically**. With 8 emails you pay for 36 email-equivalents. With 16 emails you would pay for 136.

And this still assumes every email is a newsletter you care about. In reality, 27 of the 35 emails in a typical inbox day are noise — yoga studio promos, Medium digests, university newsletters, product announcements. A single agent reads all of them with full attention, and re-reads them on every subsequent call.

**This pipeline solves both problems.** First, a free priority filter drops non-relevant senders before any LLM sees them. Second, every LLM call is scoped to exactly one job — Scout reads only the first 3,000 chars of one email; Synthesizer receives only the curated content for that one email. No history accumulates across emails. Each call starts clean.

The result: a typical daily run costs **$0.10–0.20** regardless of inbox size, preserves full stories and examples, and never re-pays for an email it already read.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                            run.py                                   │
│                    --days N  --budget $N                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Orchestrator                               │
│          coordinates pipeline · assembles daily digest              │
└──────┬───────────────────────────────────────────────┬─────────────┘
       │                                               │
       ▼                                               ▼
┌──────────────────┐                       ┌───────────────────────┐
│   Inbox Agent    │                       │    Podcast Agent      │
│                  │                       │                       │
│ IN:  days_back   │                       │ IN:  channel_url,     │
│ OUT: emails[]    │                       │      days_back        │
│                  │                       │ OUT: summaries[]      │
│ Gmail OAuth2     │                       │                       │
│ label:Newsletters│                       │ YouTube RSS feed      │
│ + has:unsubscribe│                       │ → ReaderAgent         │
│ dedup by msg ID  │                       │   (full transcript,   │
└──────┬───────────┘                       │    cached to disk)    │
       │                                   │ → Single Sonnet call  │
       │ for each email                    └───────────┬───────────┘
       ▼                                               │
  ┌──────────────┐                                     │
  │  Priority?   │── NO ──► skip (never touches LLM)  │
  └──────┬───────┘                                     │
         │ YES                                         │
         ▼                                             │
┌─────────────────────────────────────────────────────┤
│                    Scout Agent                      │
│                                                     │
│ MODEL: Haiku (cheapest — $0.80/$4.00 per M)        │
│ IN:    first 3,000 chars of email body              │
│ OUT:   { is_paywalled, completeness%,               │
│          priority_links[], topic_summary }          │
└──────┬──────────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────────────────────────┐
       │                                                             │
       ▼                                                             ▼
┌──────────────────────────────────────┐      ┌──────────────────────────────────────┐
│           Reader Agent               │      │         Research Agent               │
│         (no LLM — pure fetch)        │      │        (no LLM — pure search)        │
│                                      │      │                                      │
│ IN:    priority_links[] from Scout   │      │ Fires only when:                     │
│ OUT:   [{ url, title, text,          │      │   is_paywalled = true  OR            │
│           type: "youtube"|"web" }]   │      │   completeness < 60%                 │
│                                      │      │                                      │
│ YouTube ──► TranscriptApi            │      │ IN:    email + scout output          │
│             (cookie-authenticated,   │      │ OUT:   { snippets: [] }              │
│              cached to disk)         │      │                                      │
│ Web     ──► BeautifulSoup scrape     │      │ Single DuckDuckGo search             │
│             (yt-dlp fallback)        │      │ max 3 snippets · no AI cost          │
└──────────────────┬───────────────────┘      └──────────────────┬───────────────────┘
                   │                                             │
                   └───────────────────┬─────────────────────────┘
                                       │ (both feed into Synthesizer)
                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Synthesizer Agent                              │
│                                                                     │
│ MODEL: Sonnet ($3.00/$15.00 per M — highest quality)               │
│ IN:    email body (capped 5,000 chars)                              │
│      + scraped link text (capped 1,500 chars/link)                 │
│      + research snippets (if fired)                                 │
│      + user_feedback.json     ← raw preference notes               │
│      + quality_calibration.json ← distilled rules per sender       │
│ OUT:   Structured markdown summary:                                 │
│        TL;DR → Stories & Examples (full narrative, never cut) →    │
│        Key Insights → From the Links → Research Fills              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Writer Agent                                  │
│                      (no LLM — pure I/O)                            │
│                                                                     │
│ save_digest()      ──► summaries/YYYY-MM-DD_digest.md              │
│ mark_processed()   ──► memory/processed_ids.json                   │
│ update_profile()   ──► memory/sender_profiles.json                 │
└─────────────────────────────────────────────────────────────────────┘


── Cross-cutting: CostTracker (singleton) ───────────────────────────

  Every Haiku/Sonnet API response ──► CostTracker.add()
                                           │
                                  total > budget limit?
                                           │ YES
                                      pkill -9 run.py
                                      raise BudgetExceeded


── Memory Layer ─────────────────────────────────────────────────────

  memory/processed_ids.json       ← dedup across runs
  memory/sender_profiles.json     ← per-sender stats from Scout
  memory/user_feedback.json       ← raw feedback text per sender
  memory/quality_calibration.json ← Haiku-distilled summary rules
```

---

## Why Multi-Agent? Token Efficiency

The core question: why not just send everything to one Claude call and ask it to summarize?

Because of how LLM billing works: **you pay for every token in the context window, not just the tokens you care about.** In a single-agent design, every piece of fetched content — every email, every linked article, every transcript — accumulates in the same context and is billed together. In a multi-agent design, each call is scoped: it only sees what it needs to do its one job.

Here's the same day's work as two different sequences of API calls.

---

### Single-Agent: context accumulates across every API call

A single agent reads emails one at a time using tool calls. Each tool call appends to the conversation history. Every subsequent API call re-sends the full history. You pay for every prior email again on every new call:

```
API call 1 — fetch + summarize email 1 (a16z):
  context = [email 1 body + link]                    10,000 tok → $0.030

API call 2 — fetch + summarize email 2 (Semi-Analysis):
  context = [email 1 + email 2 + their links]        20,000 tok → $0.060
             ^^^^^^^^
             paid for again — email 1 is still in history

API call 3 — fetch + summarize email 3 (Lenny's):
  context = [emails 1–3 + all links]                 30,000 tok → $0.090

API call 4 — fetch + summarize email 4 (Chamath):
  context = [emails 1–4 + all links]                 40,000 tok → $0.120

API call 5 — fetch + summarize email 5 (Alpha Signal):
  context = [emails 1–5 + all links]                 50,000 tok → $0.150

API call 6 — fetch + summarize email 6 (Aishwarya):
  context = [emails 1–6 + all links]                 60,000 tok → $0.180

API call 7 — fetch + summarize email 7 (Nate's):
  context = [emails 1–7 + all links]                 70,000 tok → $0.210

API call 8 — fetch + summarize email 8 (Lenny's NL):
  context = [emails 1–8 + all links]                 80,000 tok → $0.240
                                                     ────────────────────
  Total tokens billed: 10K+20K+30K+40K+50K+60K+70K+80K = 360,000 tokens
  Total cost (Sonnet input):                                      ~$1.08

  Email 1 was billed 8 times.
  Email 2 was billed 7 times.
  Cost grows quadratically: N emails = N×(N+1)/2 email-equivalents billed.
```

And this only counts the 8 priority senders. A real inbox has 35+ emails per day — the agent reads yoga studio promos and Medium digests too, re-paying for all of them on every subsequent call.

---

### Multi-Agent: small, scoped calls, tokens never accumulate

```
── Newsletter pipeline (per priority email) ─────────────────

API Call 1 — Scout (Haiku, cheapest model)
┌─────────────────────────────────────────┐
│ IN: first 3,000 chars of email body     │  ~800 tokens
│ OUT: { is_paywalled, completeness%,     │
│        priority_links[] }               │  ~150 tokens
│ Cost: ~$0.001                           │
└─────────────────────────────────────────┘
  → decides which links to fetch, whether research is needed
  → 27 non-priority emails never reach even this call

[No API call] — Reader Agent fetches links (HTTP only, free)
[No API call] — Research Agent searches DuckDuckGo (free)

API Call 2 — Synthesizer (Sonnet, only for curated content)
┌─────────────────────────────────────────┐
│ IN: email body (capped 5,000 chars)     │
│   + 1–2 scraped links (1,500 chars ea) │
│   + research snippets (if needed)       │
│   + calibration rules for this sender  │
│ Total input:                ~2,000 tok  │
│ Output summary:             ~600 tok    │
│ Cost: ~$0.015                           │
└─────────────────────────────────────────┘

Repeat for each of 8 priority emails:
  8 × Scout:       ~$0.008
  8 × Synthesizer: ~$0.120
  Subtotal newsletters: ~$0.128

── Podcast pipeline ─────────────────────────────────────────

[No API call] — transcript fetched from YouTube (free, cached)

API Call — Podcast Sonnet (single call, full transcript)
┌─────────────────────────────────────────┐
│ IN: full transcript        ~25,000 tok  │
│ OUT: narrative summary      ~4,000 tok  │
│ Cost: ~$0.135                           │
└─────────────────────────────────────────┘

── Total ────────────────────────────────────────────────────

  17 small API calls (Scout + Synthesizer × 8, Podcast × 1)
  Largest single context: ~25,000 tokens (podcast)
  Total spend: ~$0.15–0.20

  vs. single-agent: ~$0.67 and growing with inbox size
```

**The key difference:** in the single-agent approach, token counts add together inside one context window and you pay for all of them at once. In the multi-agent approach, each call sees only what it needs — Scout sees 800 tokens, Synthesizer sees 2,000 — and the costs never accumulate into a single enormous bill.

---

## Memory Layer

The pipeline persists four JSON files across runs. Without them, every run starts cold — re-processing emails already seen, ignoring your past preferences, writing summaries with no sense of how you like a particular author covered.

### `processed_ids.json` — deduplication

Stores Gmail message IDs and YouTube video IDs that have already been summarized. Every time an email or podcast episode is successfully processed, its ID is appended here. On the next run, Inbox Agent and Podcast Agent skip anything already in this list. This means you can safely re-run `--days 7` without duplicating last week's digests.

### `sender_profiles.json` — sender learning

After each email is scouted, Writer Agent records stats per sender: how many times they've been processed, their typical completeness percentage, and their content type (full article, teaser, roundup, etc.). Over time this builds a picture of each sender's habits. A sender who is consistently 30% complete is almost certainly paywalled every issue — the pipeline can infer this pattern without re-scouting from scratch.

### `user_feedback.json` — raw preference notes

When you run `python3 feedback.py "sender@example.com" "your note"`, your text is appended verbatim here, keyed by sender. This is intentionally unstructured. You might write "go deeper on the technical examples" for Semi-Analysis, or "I care more about the frameworks than the anecdotes" for a16z. The raw notes are preserved exactly as written — this is your ground truth.

### `quality_calibration.json` — distilled rules

Raw feedback notes accumulate over time and can become long and redundant. After each `feedback.py` call, a Haiku model reads all your raw notes for that sender and distills them into a concise set of rules — removing repetition, resolving contradictions, and extracting the actionable signal. This distilled version is what the Synthesizer actually reads on every run. The separation matters: your raw notes capture every nuance you expressed over time; the distilled rules give Sonnet a clean, non-contradictory instruction set without wasting tokens on history.

Together these two files create a **feedback loop**: you give raw guidance → Haiku distills it cheaply → Sonnet uses the rules → the summary improves → you give more feedback. The pipeline gets better at writing for your specific taste with each correction, without you having to re-explain your preferences from scratch every time.

---

## Example Output

<details>
<summary><strong>📋 Sample Daily Digest — June 10–11, 2026</strong> (click to expand)</summary>

> Real output from the pipeline over two consecutive days. Sources: a16z, SemiAnalysis, Aishwarya Srinivasan, Lenny's Podcast. Paywalled articles are supplemented with a web search fill. Podcast summaries are from full YouTube transcripts (~24K tokens).

---

### Everything is Recorded Now — a16z

**TL;DR**
- Work meetings are being recorded by default — this wasn't a policy decision, it just happened, and it's not reversible
- The right mental model: onboard AI like you onboard employees — through meetings and osmosis, not docs and wikis
- Two compounding advantages: bottom-up (ICs get a force-multiplied assistant) and top-down (executives get ambient oversight via AI proxies)
- A new enterprise software category is emerging — voice-first systems of record that make conversational context structured and queryable

**Stories & Examples**

*Bridgewater: The Eccentric Policy That Turned Out to Be Prescient* — Bridgewater made recording all internal meetings policy years ago. At the time it looked cult-like. The argument: it was simply early. The logic that made Bridgewater look weird in 2015 is the same logic that makes AI-native companies look smart in 2026: institutional knowledge lives in conversation, not documentation, and capturing it compounds.

*OpenAI: Agents Standing In for Senior Leaders* — AI agents now attend meetings on behalf of senior leaders who can't be present. The model that has ingested two years of internal discussion is simply a better assistant than the one that only read documentation.

*Granola: Better Context Than Any Other Tool at a16z* — Granola has better context on a16z's culture and investments than almost any other tool they use — because it's been in the room. Presence at meetings beats access to documentation.

**Key Insights**
- Meetings are where culture actually lives — nuance on a customer call, the real argument in a product review, the offhand comment that shifts the roadmap — all of this lived in conversation and until now evaporated
- The two advantages of recording are asymmetric: bottom-up (smarter assistants) is intuitive; top-down (executive visibility via AI proxies) gets less attention but may matter more
- Verbal-culture companies (Shopify, OpenAI) historically lost their best context when conversations ended — AI recording closes that gap permanently

---

### Intel Should Raise Capital — SemiAnalysis *(paywalled, 35% complete)*

**TL;DR**
- Intel's new board finally understands technology over financial engineering
- Has already raised ~$20B from U.S. government, SoftBank, Altera, Nvidia — SemiAnalysis argues keep going
- A 4–5% equity dilution at current prices would raise ~$25B — the cheapest capital available
- The Smart Capital JV strategy self-refuted: Intel spent $14.2B buying back a fab stake it had previously sold for $11.2B
- Window is now: Intel trades at its most expensive TTM valuation since the 2000 bubble

**Key Insights**
- The Smart Capital strategy proved expensive in hindsight — if the buyback is accretive, the original sale was expensive
- Intel carries ~$45B in debt; more debt isn't the answer; equity at a premium to recent strategic investors is accretive, not punitive
- Research fill: the Terafab announcement and overflow from N3 shortage create a genuine upside scenario Intel can't fund from operations alone

---

### Tony Fadell: How to Build Real Taste — Lenny's Podcast *(full transcript, ~24K tokens)*

**TL;DR**
- Great products require opinion-based decisions from people with genuine taste — data alone can't get you to a differentiated 1.0
- Every product needs three generations: make it, fix it, fix the business
- Marketing isn't separate from product — it *is* product
- AI makes it easier to ship fast, but "fast software" creates brittle foundations

**Stories & Examples**

*The iPhone Keyboard Debate* — The question dragged on for months at Apple. Hardware keyboard (BlackBerry loyalists, ~1–2% of mobile users) vs. virtual multi-touch (the other 98%). The team ran structured tests measuring speed and error rate. The virtual keyboard started "way down here" and improved slowly over months. The data didn't clearly favor either side. Jobs said: "We are going this way." Anyone not on board was told to leave the room. Steve's opinion won.

*The iPod and Windows — The Decision That Saved Apple* — The original iPod launched Mac-only. Jobs refused Windows: "Over my dead body." First generation sold well to Mac loyalists, then flatlined. Same for the second. Fadell ran a skunk works project anyway. Third-generation iPod shipped with Windows support and iTunes Music Store. That's when it took off. Fadell's framing: "If we don't have Windows connectivity, the iPod doesn't cost $349. It costs $3,000 — because you have to buy a Mac." The halo effect from the iPod made the iPhone possible. Without it, Fadell believes there may have been no Apple.

*The Nest Thermostat* — Pain: thermostats were universal but arcane; 50% of home energy bills went to heating/cooling nobody understood. New technology: AI that could learn household patterns automatically. Opinion-based leap: price it at $249 — five to six times more than existing thermostats — justified by $800–$1,200/year energy savings. Then reinvent purchase (Best Buy), installation (DIY), and the product itself. Nest wasn't a product; it was a system of innovations.

*The Anthropic Source Code Leak* — Engineers who examined leaked code were alarmed. The main Claude loop was written in a way architects found brittle and nearly unreadable — code that should have been 12–15 subfunctions collapsed into a monolith. It worked. It passed tests. But it was unauditable. His analogy: fast fashion. Looks fine on day one. Doesn't survive one wash. The right use of AI: prototype aggressively, then architect properly.

**Quotable Moments**
> "You still need humans in the loop. Don't surrender to the machine. We can use the machines, but don't cognitively surrender."

> "If we don't have Windows connectivity, the iPod doesn't cost $349. It costs $3,000. People aren't going to take a risk on a company that's almost bankrupt for $3,000."

> "Fast software is like fast fashion. It looks fine on day one. It doesn't survive one wash."

> "Marketing is product. If you don't understand how your customer finds, buys, installs, and lives with your product — you don't understand your product."

---

*Full sample digest (both days, all sources): [examples/sample-digest-june-10-11-2026.md](examples/sample-digest-june-10-11-2026.md)*

</details>

---

## Setup

### Prerequisites

- Python 3.10+ (3.9 works but is end-of-life)
- An [Anthropic API key](https://console.anthropic.com/)
- A Google account with Gmail

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/daily-newsletter.git
cd daily-newsletter
pip3 install -r requirements.txt
```

### 2. Anthropic API key

```bash
cp .env.example .env
# Edit .env and add your key:
# ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Gmail OAuth setup

This grants the app read-only access to your Gmail.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g. `newsletter-summarizer`)
3. Enable the **Gmail API** (APIs & Services → Enable APIs)
4. Create OAuth credentials:
   - Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON → save as `credentials.json` in the project root
5. Add your Gmail address as a test user:
   - OAuth consent screen → Test users → Add your email
6. Run the OAuth setup (opens a browser window once):
   ```bash
   python3 setup_oauth.py
   ```
   This creates `token.json` — subsequent runs use it silently.

### 4. YouTube cookies (for transcript access)

YouTube rate-limits automated transcript requests. Providing your session cookies lets the pipeline authenticate as a real user.

1. Install the **"Get cookies.txt LOCALLY"** Chrome extension
2. Go to `youtube.com` while logged in
3. Click the extension → Export → downloads `www.youtube.com_cookies.txt`
4. Move it into the project:
   ```bash
   mv ~/Downloads/www.youtube.com_cookies.txt ./youtube_cookies.txt
   ```

> **Note:** `youtube_cookies.txt` is gitignored and never leaves your machine. Re-export if YouTube starts blocking transcript fetches (cookies rotate periodically).

### 5. Configure your priority senders

Edit `config.py` → `PRIORITY_SOURCES` to add your own newsletter senders:

```python
PRIORITY_SOURCES = {
    "my_newsletter": {
        "name": "My Newsletter",
        "email_patterns": ["sender@example.com", "example"],
        "youtube_channel": None,
    },
    ...
}
```

The `email_patterns` list is matched as substrings against the email's `From` header — add the sender domain or address fragment.

### 6. Run

```bash
python3 -u run.py              # last 1 day, $0.50 budget
python3 -u run.py --days 3     # last 3 days
python3 -u run.py --budget 1.00  # raise budget to $1.00
```

Output: `summaries/YYYY-MM-DD_digest.md`

### 7. Feedback and calibration

```bash
python3 feedback.py "sender@example.com" "go deeper on the technical examples"
```

---

## Cost Reference

| Model | Input | Output | Used for |
|---|---|---|---|
| Haiku (`claude-haiku-4-5`) | $0.80/M | $4.00/M | Scout (triage), feedback distillation |
| Sonnet (`claude-sonnet-4-6`) | $3.00/M | $15.00/M | Synthesizer, Podcast summarization |

Typical daily run: **$0.10–0.20**

---

## Project Structure

```
daily-newsletter/
├── run.py                    # Entry point
├── orchestrator.py           # Pipeline coordinator
├── config.py                 # Priority senders, models, limits
├── feedback.py               # CLI for feedback/calibration
├── setup_oauth.py            # One-time Gmail OAuth flow
├── requirements.txt
├── .env.example
├── agents/
│   ├── base_agent.py         # Agentic loop with cost tracking
│   ├── inbox_agent.py        # Gmail fetch + dedup
│   ├── scout_agent.py        # Haiku triage
│   ├── reader_agent.py       # Link fetch + transcript
│   ├── research_agent.py     # DuckDuckGo gap-fill
│   ├── synthesizer_agent.py  # Sonnet summary
│   ├── podcast_agent.py      # YouTube RSS + Sonnet
│   └── writer_agent.py       # Digest writer + memory
├── tools/
│   └── cost_tracker.py       # Budget enforcement singleton
├── memory/                   # Runtime state (gitignored)
└── summaries/                # Output digests (gitignored)
```

---

## Security Notes

The following files contain credentials and are gitignored — **never commit them**:

- `credentials.json` — Google OAuth client secret
- `token.json` — Gmail access/refresh token
- `youtube_cookies.txt` — YouTube session cookies
- `.env` — Anthropic API key
