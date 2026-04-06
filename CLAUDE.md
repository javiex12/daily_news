# CLAUDE.md — AI News Bot

## Description
Telegram bot that sends a daily AI news summary at 8am Lima time (13:00 UTC) using GitHub Actions as a cron scheduler and Gemini 2.5 Flash to generate the summary in Spanish.

## Stack
- **Python 3.11**
- **feedparser** — RSS feed reading
- **google-genai** — Gemini 2.5 Flash API
- **python-telegram-bot v21** — message sending
- **GitHub Actions** — cron execution (free)

## Structure
```
news_agent/
├── .github/workflows/daily_news.yml  # cron + workflow_dispatch
├── bot.py                            # main script (single logic file)
├── requirements.txt                  # pinned dependencies
├── .env.example                      # variable template (no real values)
├── .gitignore                        # excludes .env and .venv
├── setup.sh                          # creates venv and installs dependencies
└── README.md                         # full setup guide
```

## Required environment variables
| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token (obtained from @BotFather) |
| `TELEGRAM_CHAT_ID` | Target chat or group ID |
| `GEMINI_API_KEY` | Google AI Studio API key |

Loaded locally from `.env` (via python-dotenv). In production, configured as GitHub Secrets.

## Code conventions

### Style
- Type hints on all functions
- Logging at every relevant step (`logger.info` / `logger.warning` / `logger.error`)
- Small, single-responsibility functions
- No hardcoded keys, tokens, or configuration

### Async
- `main()` is async, executed with `asyncio.run(main())`
- Feeds are fetched in parallel with `asyncio.gather` + `asyncio.to_thread`
- Gemini is called synchronously (single call, doesn't justify async)
- Telegram sending is async (python-telegram-bot v21 requires it)

### Error handling
- If a feed fails, log a warning and continue with the rest (never breaks the flow)
- If there are no new articles, **recap mode** activates (see below)
- If all feeds fail or Gemini fails, a fallback message is sent to Telegram
- Telegram sending retries up to 3 times with 5s backoff

### Telegram limits
- Maximum 4096 characters per message (`MAX_CHUNK_SIZE`)
- Long messages are split into chunks respecting paragraph boundaries
- 1s delay between chunks to avoid saturating the API

## Running locally
```bash
./setup.sh                   # creates venv and installs deps (first time only)
source .venv/bin/activate    # activate the venv
cp .env.example .env         # create .env (first time only)
# edit .env with your keys
python bot.py
```

## Important rules
- **Never** commit `.env` to the repo — it's in `.gitignore`
- **Never** hardcode API keys or tokens in the code
- **Do not** add databases, web servers, webhooks, or Docker
- **Do not** use `requirements.txt` without pinned versions
- Keep everything in a single `bot.py` file — do not create additional modules unless complexity clearly justifies it
- The bot is **unidirectional**: it only sends messages, it does not listen or respond

## Configured RSS sources
`RSS_FEEDS` is a list of tuples `(url, weight)`. The weight (0.0–1.0) determines article priority in the final scoring.

```python
RSS_FEEDS = [
    ("https://syncedreview.com/feed", 1.0),           # global AI, strong China coverage
    ("https://www.theverge.com/rss/ai-...", 1.0),     # exclusive AI section
    ("https://techcrunch.com/.../feed/", 0.9),         # AI category
    ("https://www.technologyreview.com/feed/", 0.8),   # MIT Tech Review
    ("https://pandaily.com/feed/", 0.7),               # general Chinese tech
    ("https://restofworld.org/feed/latest", 0.7),      # non-USA global perspective
    ("https://feeds.arstechnica.com/...", 0.6),        # generalist, more noise
]
```

To add or remove sources, edit this list in `bot.py`. Any feed that fails is automatically ignored.

## Article filtering pipeline
The bot applies these steps before sending articles to Gemini:

1. **Time window** — only articles from the last 72h
2. **History deduplication** — discards URLs already sent in the last 2 days (`sent_history.json`)
3. **Keyword filter** — discards articles without at least one AI keyword in title or description
4. **Scoring and trimming** — sorts by `source_weight + recency_bonus` and takes the top 25

The history (`sent_history.json`) is persisted between GitHub Actions runs using `actions/cache`.

## Recap mode
If after filtering no new articles remain, the bot enters **recap mode**:
- Uses the full pool from the last 72h (ignoring dedup history)
- Gemini receives a different prompt: presents news as "the most relevant from recent days" (3-5 instead of 5-7)
- Message header changes to `📰 Lo más relevante — {date}`
- History is not updated (articles were already recorded)

## Gemini prompt
Two prompts are defined in `generate_summary()` in `bot.py`:

**Normal mode** — selects 5-7 news items from the last 24h, includes a list of yesterday's covered topics to avoid thematic repetition.

**Recap mode** — selects 3-5 news items from recent days, no topic restrictions.

Both use:
- Telegram Markdown format (`*bold*`, `_italic_`, `[text](url)`)
- Final section "🔮 Tendencia del día"
- Informative and conversational tone, in Spanish

If the Gemini model is changed, update both `bot.py` and this file.
