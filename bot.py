import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import feedparser
from dotenv import load_dotenv
from google import genai
from openai import OpenAI
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RSS_FEEDS: list[tuple[str, float]] = [
    ("https://syncedreview.com/feed", 1.0),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 1.0),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", 0.9),
    ("https://www.technologyreview.com/feed/", 0.8),
    ("https://pandaily.com/feed/", 0.7),
    ("https://restofworld.org/feed/latest", 0.7),
    ("https://feeds.arstechnica.com/arstechnica/technology-lab", 0.6),
]

AI_KEYWORDS: set[str] = {
    "ai", "artificial intelligence", "llm", "model", "agent", "deepseek",
    "gemini", "claude", "openai", "gpt", "neural", "robot", "machine learning",
    "chatbot", "generative", "kimi", "technology", "transformer",
}

MAX_CHUNK_SIZE = 4096
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
MAX_POOL_SIZE = 25
RECENCY_BONUS_HOURS = 6
RECENCY_BONUS = 0.2
HISTORY_FILE = "sent_history.json"
HISTORY_DAYS = 2  # how many days to keep in history


def load_history() -> list[dict[str, str]]:
    """Load sent articles history from disk."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not load history file: {exc}")
        return []


def save_history(history: list[dict[str, str]], new_articles: list[dict[str, str]]) -> None:
    """Append new articles to history and prune entries older than HISTORY_DAYS."""
    today = datetime.now(timezone.utc).date().isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)).date().isoformat()

    for article in new_articles:
        history.append({"url": article["url"], "title": article["title"], "date": today})

    pruned = [e for e in history if e.get("date", "") >= cutoff]

    with open(HISTORY_FILE, "w") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)
    logger.info(f"History saved: {len(pruned)} entries ({len(new_articles)} new).")


def passes_keyword_filter(article: dict) -> bool:
    """Return True if the article title or description contains an AI-related keyword."""
    text = (article["title"] + " " + article["description"]).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def score_and_trim(articles: list[dict]) -> list[dict]:
    """Score articles by source weight + recency bonus and return the top MAX_POOL_SIZE."""
    now = datetime.now(timezone.utc)
    for article in articles:
        pub_date = datetime.fromisoformat(article["pub_date"])
        hours_old = (now - pub_date).total_seconds() / 3600
        recency_bonus = RECENCY_BONUS if hours_old <= RECENCY_BONUS_HOURS else 0.0
        article["score"] = article["weight"] + recency_bonus
    return sorted(articles, key=lambda a: a["score"], reverse=True)[:MAX_POOL_SIZE]


async def fetch_feed(url: str, weight: float) -> list[dict]:
    """Fetch a single RSS feed and return articles from the last 24 hours."""
    try:
        logger.info(f"Fetching feed: {url}")
        feed = await asyncio.to_thread(feedparser.parse, url)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        articles: list[dict] = []

        for entry in feed.entries:
            # Parse publication date
            pub_date: datetime | None = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            # Skip entries without a parseable date or older than 24h
            if pub_date is None or pub_date < cutoff:
                continue

            title = entry.get("title", "Sin título").strip()
            link = entry.get("link", "").strip()
            description = (
                entry.get("summary", "")
                or entry.get("description", "")
            ).strip()
            # Truncate long descriptions
            if len(description) > 500:
                description = description[:497] + "..."

            if link:
                articles.append({
                    "title": title,
                    "url": link,
                    "description": description,
                    "weight": weight,
                    "pub_date": pub_date.isoformat(),
                })

        logger.info(f"  → {len(articles)} articles from the last 24h")
        return articles

    except Exception as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return []


async def fetch_all_news() -> list[dict]:
    """Fetch all RSS feeds concurrently and return deduplicated articles."""
    results: list[list[dict]] = await asyncio.gather(
        *[fetch_feed(url, weight) for url, weight in RSS_FEEDS]
    )

    seen_urls: set[str] = set()
    articles: list[dict] = []
    for feed_articles in results:
        for article in feed_articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                articles.append(article)

    logger.info(f"Total unique articles collected: {len(articles)}")
    return articles


def generate_summary(
    articles: list[dict],
    api_key: str,
    recent_titles: list[str] | None = None,
    recap_mode: bool = False,
) -> tuple[str, str]:
    """Call Gemini 2.5 Flash to generate a curated Spanish summary. Returns (text, provider)."""
    articles_text = "\n\n".join(
        f"Título: {a['title']}\nURL: {a['url']}\nDescripción: {a['description']}"
        for a in articles
    )

    if recap_mode:
        prompt = f"""Eres un curador de noticias de inteligencia artificial para desarrolladores hispanohablantes.

Hoy no hay artículos completamente nuevos, pero estos son los más relevantes de los últimos días que merecen destacarse.

1. Selecciona las 3-5 más importantes e impactantes.
2. Para cada una escribe:
   - El título en *negrita*
   - Un resumen de 2-3 líneas explicando qué pasó y por qué sigue siendo relevante
   - El link como [Leer más](url)
3. Al final añade una sección titulada "🔮 Tendencia del día" con 3-4 líneas sobre el patrón dominante de estos días.

Reglas de formato (Telegram Markdown):
- Usa *texto* para negrita
- Usa _texto_ para cursiva
- Usa [texto](url) para links
- Separa cada noticia con una línea en blanco
- NO uses ## ni # ni otros marcadores de encabezado

Tono: informativo y conversacional, como un newsletter para desarrolladores. Escribe en español.

NOTICIAS:
{articles_text}
"""
    else:
        avoid_section = ""
        if recent_titles:
            titles_list = "\n".join(f"- {t}" for t in recent_titles)
            avoid_section = f"\nTEMAS YA CUBIERTOS AYER (evita repetirlos aunque aparezcan con otro artículo):\n{titles_list}\n"

        prompt = f"""Eres un curador de noticias de inteligencia artificial para desarrolladores hispanohablantes.

Analiza estas {len(articles)} noticias de las últimas 24 horas y realiza lo siguiente:

1. Selecciona las 5-7 más relevantes e impactantes para el ecosistema de IA. Si hay menos de 5, incluye todas.
2. Para cada noticia seleccionada escribe:
   - El título en *negrita*
   - Un resumen de 2-3 líneas explicando qué pasó y por qué importa para devs o la industria
   - El link como [Leer más](url)
3. Al final añade una sección titulada "🔮 Tendencia del día" con 3-4 líneas analizando el patrón o tema dominante en las noticias de hoy.
{avoid_section}
Reglas de formato (Telegram Markdown):
- Usa *texto* para negrita
- Usa _texto_ para cursiva
- Usa [texto](url) para links
- Separa cada noticia con una línea en blanco
- NO uses ## ni # ni otros marcadores de encabezado

Tono: informativo y conversacional, como un newsletter para desarrolladores. Escribe en español.

NOTICIAS:
{articles_text}
"""

    logger.info(f"Generating summary with Gemini 2.5 Flash (recap_mode={recap_mode})...")
    gemini_error: Exception | None = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            logger.info("Summary generated successfully.")
            return response.text, "gemini"
        except Exception as exc:
            gemini_error = exc
            wait = 2 ** attempt  # 1s, 2s, 4s
            if attempt < max_retries - 1:
                logger.warning(f"Gemini attempt {attempt + 1}/{max_retries} failed: {exc}. Retrying in {wait}s...")
                time.sleep(wait)

    logger.warning(f"[WARN] Gemini unavailable after {max_retries} retries, switching to DeepSeek")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not deepseek_key:
        raise RuntimeError(
            f"All providers failed. Gemini: {gemini_error}. DEEPSEEK_API_KEY not configured."
        )
    try:
        ds_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        ds_response = ds_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
        )
        logger.info("Summary generated successfully via DeepSeek.")
        return ds_response.choices[0].message.content, "deepseek"
    except Exception as ds_exc:
        raise RuntimeError(
            f"All providers failed. Gemini: {gemini_error}. DeepSeek: {ds_exc}"
        )


def chunk_message(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split a message into chunks that fit within Telegram's limit."""
    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for paragraph in paragraphs:
        # A single paragraph exceeding max_size gets hard-split
        if len(paragraph) > max_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            for i in range(0, len(paragraph), max_size):
                chunks.append(paragraph[i : i + max_size])
            continue

        candidate = (current_chunk + "\n\n" + paragraph).lstrip("\n")
        if len(candidate) <= max_size:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


async def send_message(token: str, chat_id: str, text: str) -> None:
    """Send a message to Telegram with retry logic."""
    bot = Bot(token=token)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            return
        except TelegramError as exc:
            logger.warning(f"Telegram send attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                raise


async def send_fallback(token: str, chat_id: str, reason: str) -> None:
    """Send a plain-text error notification."""
    message = f"⚠️ *AI News Bot* — error al generar el resumen de hoy.\n\n_{reason}_"
    try:
        await send_message(token, chat_id, message)
    except Exception as exc:
        logger.error(f"Could not send fallback message: {exc}")


async def main() -> None:
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if not token or not chat_id or not gemini_key:
        logger.error("Missing required environment variables: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY")
        sys.exit(1)

    # 1. Load history
    history = load_history()
    seen_urls: set[str] = {e["url"] for e in history}
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    recent_titles = [e["title"] for e in history if e.get("date", "") >= yesterday]

    # 2. Fetch all news
    all_articles = await fetch_all_news()

    if not all_articles:
        logger.error("All feeds failed — no articles collected.")
        await send_fallback(token, chat_id, "No se pudo obtener noticias de ningún feed RSS.")
        return

    # 3. Deduplicate by history, filter by keywords, score and trim
    new_articles = [a for a in all_articles if a["url"] not in seen_urls]
    logger.info(f"After dedup: {len(new_articles)} new articles (filtered {len(all_articles) - len(new_articles)} already seen)")

    filtered = [a for a in new_articles if passes_keyword_filter(a)]
    logger.info(f"After keyword filter: {len(filtered)} articles")

    recap_mode = False
    if filtered:
        pool = score_and_trim(filtered)
    else:
        # No new articles — recap mode with best of all_articles
        logger.warning("No new articles after dedup+filter. Switching to recap mode.")
        recap_mode = True
        recent_titles = None  # don't pass yesterday's titles in recap mode
        pool = score_and_trim([a for a in all_articles if passes_keyword_filter(a)])

    logger.info(f"Pool sent to Gemini: {len(pool)} articles (recap_mode={recap_mode})")

    # 4. Generate summary
    try:
        summary, provider = generate_summary(pool, gemini_key, recent_titles, recap_mode)
    except Exception as exc:
        logger.error(f"Gemini API error: {exc}")
        await send_fallback(token, chat_id, f"Error al conectar con Gemini API: {exc}")
        return

    # 5. Send to Telegram
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    if recap_mode:
        header = f"*📰 Lo más relevante — {date_str}*\n\n"
    else:
        header = f"*📰 Noticias de IA — {date_str}*\n\n"

    footer = "\n\n_Generado con Gemini 2.5 Flash_" if provider == "gemini" else "\n\n_Generado con DeepSeek Chat_"
    full_message = header + summary + footer
    chunks = chunk_message(full_message)

    logger.info(f"Sending {len(chunks)} message chunk(s) to Telegram...")
    try:
        for i, chunk in enumerate(chunks, 1):
            await send_message(token, chat_id, chunk)
            if i < len(chunks):
                await asyncio.sleep(1)  # avoid hitting rate limits
        logger.info("All chunks sent successfully.")
    except TelegramError as exc:
        logger.error(f"Failed to send message after {MAX_RETRIES} attempts: {exc}")
        sys.exit(1)

    # 6. Persist history (only in normal mode — recap articles are already in history)
    if not recap_mode:
        save_history(history, pool)


if __name__ == "__main__":
    asyncio.run(main())
