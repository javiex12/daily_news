import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

import feedparser
from dotenv import load_dotenv
from google import genai
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RSS_FEEDS: list[str] = [
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.technologyreview.com/feed/",
]

MAX_CHUNK_SIZE = 4096
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


async def fetch_feed(url: str) -> list[dict[str, str]]:
    """Fetch a single RSS feed and return articles from the last 24 hours."""
    try:
        logger.info(f"Fetching feed: {url}")
        feed = await asyncio.to_thread(feedparser.parse, url)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles: list[dict[str, str]] = []

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
                articles.append({"title": title, "url": link, "description": description})

        logger.info(f"  → {len(articles)} articles from the last 24h")
        return articles

    except Exception as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return []


async def fetch_all_news() -> list[dict[str, str]]:
    """Fetch all RSS feeds concurrently and return deduplicated articles."""
    results: list[list[dict[str, str]]] = await asyncio.gather(
        *[fetch_feed(url) for url in RSS_FEEDS]
    )

    seen_urls: set[str] = set()
    articles: list[dict[str, str]] = []
    for feed_articles in results:
        for article in feed_articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                articles.append(article)

    logger.info(f"Total unique articles collected: {len(articles)}")
    return articles


def generate_summary(articles: list[dict[str, str]], api_key: str) -> str:
    """Call Gemini 2.5 Flash to generate a curated Spanish summary."""
    articles_text = "\n\n".join(
        f"Título: {a['title']}\nURL: {a['url']}\nDescripción: {a['description']}"
        for a in articles
    )

    prompt = f"""Eres un curador de noticias de inteligencia artificial para desarrolladores hispanohablantes.

Analiza estas {len(articles)} noticias de las últimas 24 horas y realiza lo siguiente:

1. Selecciona las 5-7 más relevantes e impactantes para el ecosistema de IA.
2. Para cada noticia seleccionada escribe:
   - El título en *negrita*
   - Un resumen de 2-3 líneas explicando qué pasó y por qué importa para devs o la industria
   - El link como [Leer más](url)
3. Al final añade una sección titulada "🔮 Tendencia del día" con 3-4 líneas analizando el patrón o tema dominante en las noticias de hoy.

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

    logger.info("Generating summary with Gemini 2.5 Flash...")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    logger.info("Summary generated successfully.")
    return response.text


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

    # 1. Fetch news
    articles = await fetch_all_news()

    if not articles:
        logger.warning("No articles found in the last 24 hours.")
        await send_fallback(token, chat_id, "No se encontraron noticias de IA en las últimas 24 horas.")
        return

    # 2. Generate summary
    try:
        summary = generate_summary(articles, gemini_key)
    except Exception as exc:
        logger.error(f"Gemini API error: {exc}")
        await send_fallback(token, chat_id, f"Error al conectar con Gemini API: {exc}")
        return

    # 3. Send to Telegram
    header = f"*📰 Noticias de IA — {datetime.now(timezone.utc).strftime('%d/%m/%Y')}*\n\n"
    full_message = header + summary
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


if __name__ == "__main__":
    asyncio.run(main())
