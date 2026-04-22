# AI News Bot

Telegram bot that sends a daily summary of the most relevant AI news at 8am Lima time. Runs 100% free using GitHub Actions as a scheduler and Gemini 2.5 Flash to generate the summary.

## How it works

1. GitHub Actions triggers the script every day at 13:00 UTC (8am Lima)
2. `bot.py` reads 7 RSS feeds from AI sources over the last 72 hours
3. Filters articles by AI keywords, scores them by source and recency, and takes the top 25
4. Gemini 2.5 Flash selects the 5-7 most relevant and generates a summary in Spanish
5. If Gemini fails after 3 retries, DeepSeek Chat is used as a fallback provider
6. The summary is sent to your Telegram chat (the footer indicates which model generated it)

**News sources:**
| Source | Coverage | Weight |
|--------|----------|--------|
| Synced Review | Global AI, strong China coverage | 1.0 |
| The Verge AI | Exclusive AI section | 1.0 |
| TechCrunch AI | Startups and product | 0.9 |
| MIT Technology Review | In-depth analysis | 0.8 |
| Pandaily | General Chinese tech | 0.7 |
| Rest of World | Non-USA global perspective | 0.7 |
| Ars Technica | General tech | 0.6 |

---

## Setup

### 1. Create the Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the instructions
3. BotFather will give you a **token** like `123456789:ABCdef...` — save it

### 2. Get your Chat ID

1. Send any message to your new bot
2. Open this URL in your browser (replace `<TOKEN>` with your real token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Find the `"chat"` → `"id"` field in the JSON response — that is your **chat_id**

> Tip: if you want to receive messages in a group, add the bot to the group and use the group's chat_id (it will be a negative number).

### 3. Get the Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a new API key (the free tier is sufficient)
3. Save the key

### 4. Get the DeepSeek API key (fallback)

1. Go to [DeepSeek Platform](https://platform.deepseek.com/api_keys)
2. Create a new API key
3. Save the key — it will only be used if Gemini fails

### 5. Configure GitHub Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add these 4 secrets:

| Name | Value |
|------|-------|
| `TELEGRAM_TOKEN` | Your bot token |
| `TELEGRAM_CHAT_ID` | Your chat id (number) |
| `GEMINI_API_KEY` | Your Google API key |
| `DEEPSEEK_API_KEY` | Your DeepSeek API key (fallback) |

### 6. Enable the workflow

1. Go to the **Actions** tab in your repository
2. If Actions is not enabled, click "I understand my workflows, go ahead and enable them"
3. Click **"Daily AI News Bot"** → **"Run workflow"** to do a manual test
4. Verify the message arrives in your Telegram in ~1-2 minutes

From now on the bot will run automatically every day at 8am Lima time.

---

## Local execution (for testing)

```bash
# 1. Clone the repository
git clone <your-repo>
cd news_agent

# 2. Create virtual environment and install dependencies
./setup.sh
source .venv/bin/activate

# 3. Configure environment variables
cp .env.example .env
# Edit .env and fill in the 3 values

# 4. Run
python bot.py
```

**To test recap mode** (simulates no new articles):
```bash
python -c "
import json, datetime
fake = [{'url': f'https://fake.com/{i}', 'title': f'Fake {i}', 'date': datetime.date.today().isoformat()} for i in range(200)]
json.dump(fake, open('sent_history.json', 'w'))
"
python bot.py
# Then delete the fake history:
rm sent_history.json
```

---

## Project structure

```
news_agent/
├── .github/
│   └── workflows/
│       └── daily_news.yml   # GitHub Actions cron + history cache
├── bot.py                   # Main script
├── requirements.txt         # Pinned dependencies
├── .env.example             # Environment variable template
└── README.md
```

## Stack

- **Python 3.11**
- **feedparser** — RSS feed reading
- **google-genai** — Gemini 2.5 Flash API (primary)
- **openai** — DeepSeek Chat API via OpenAI-compatible client (fallback)
- **python-telegram-bot** — Telegram message sending
- **GitHub Actions** — free cron execution + history persistence

---

## Fallback flow (Gemini → DeepSeek)

To keep the daily digest reliable even when Gemini is rate-limited or down, the bot uses a two-provider chain:

1. **Gemini 2.5 Flash** is called first, with up to 3 retries and exponential backoff (1s → 2s → 4s)
2. If all 3 attempts fail, the bot switches to **DeepSeek Chat** (`deepseek-chat` via OpenAI-compatible endpoint `https://api.deepseek.com`) using the same prompt
3. If `DEEPSEEK_API_KEY` is missing, or DeepSeek also fails, a fallback error message is sent to Telegram explaining what went wrong

The Telegram message footer shows which model was actually used:
- `_Generado con Gemini 2.5 Flash_` — normal path
- `_Generado con DeepSeek Chat_` — fallback path (useful signal that Gemini is having issues)

---

## Subscribe

If you'd like to receive the daily AI news digest in my own Telegram, reach out at javiernv17@gmail.com
