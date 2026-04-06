# CLAUDE.md — AI News Bot

## Descripción
Bot de Telegram que envía un resumen diario de noticias de IA a las 8am Lima (13:00 UTC) usando GitHub Actions como cron y Gemini 2.5 Flash para generar el resumen en español.

## Stack
- **Python 3.11**
- **feedparser** — lectura de RSS feeds
- **google-genai** — Gemini 2.5 Flash API
- **python-telegram-bot v21** — envío de mensajes
- **GitHub Actions** — ejecución del cron (gratis)

## Estructura
```
news_agent/
├── .github/workflows/daily_news.yml  # cron + workflow_dispatch
├── bot.py                            # script principal (único archivo de lógica)
├── requirements.txt                  # dependencias pinneadas
├── .env.example                      # plantilla de variables (sin valores reales)
├── .gitignore                        # excluye .env y .venv
├── setup.sh                          # crea venv e instala dependencias
└── README.md                         # guía de setup completa
```

## Variables de entorno requeridas
| Variable | Descripción |
|----------|-------------|
| `TELEGRAM_TOKEN` | Token del bot (obtenido con @BotFather) |
| `TELEGRAM_CHAT_ID` | ID del chat o grupo destino |
| `GEMINI_API_KEY` | API key de Google AI Studio |

Localmente se cargan desde `.env` (via python-dotenv). En producción se configuran como GitHub Secrets.

## Convenciones del código

### Estilo
- Type hints en todas las funciones
- Logging en cada paso relevante (`logger.info` / `logger.warning` / `logger.error`)
- Funciones pequeñas y con una sola responsabilidad
- Sin hardcodeo de keys, tokens ni configuración

### Async
- `main()` es async, se ejecuta con `asyncio.run(main())`
- Los feeds se fetchean en paralelo con `asyncio.gather` + `asyncio.to_thread`
- Gemini se llama de forma síncrona (una sola llamada, no justifica async)
- El envío a Telegram es async (python-telegram-bot v21 lo requiere)

### Manejo de errores
- Si un feed falla, se loggea el warning y se continúa con los demás (nunca rompe el flujo)
- Si no hay noticias nuevas, se activa **recap mode** (ver abajo)
- Si todos los feeds fallan o Gemini falla, se envía un mensaje de fallback a Telegram
- El envío a Telegram tiene retry de hasta 3 intentos con 5s de backoff

### Límites de Telegram
- Máximo 4096 caracteres por mensaje (`MAX_CHUNK_SIZE`)
- Los mensajes largos se dividen en chunks respetando los límites de párrafo
- Se espera 1s entre chunks para no saturar la API

## Cómo correr localmente
```bash
./setup.sh                   # crea venv e instala deps (solo la primera vez)
source .venv/bin/activate    # activa el venv
cp .env.example .env         # crea el .env (solo la primera vez)
# edita .env con tus keys
python bot.py
```

## Reglas importantes
- **Nunca** subir `.env` al repo — está en `.gitignore`
- **Nunca** hardcodear API keys ni tokens en el código
- **No** añadir bases de datos, servidores web, webhooks ni Docker
- **No** usar `requirements.txt` sin versiones pinneadas
- Mantener todo en un solo archivo `bot.py` — no crear módulos adicionales salvo que la complejidad lo justifique claramente
- El bot es **unidireccional**: solo envía mensajes, no escucha ni responde

## Fuentes RSS configuradas
`RSS_FEEDS` es una lista de tuplas `(url, peso)`. El peso (0.0–1.0) determina la prioridad del artículo en el scoring final.

```python
RSS_FEEDS = [
    ("https://syncedreview.com/feed", 1.0),           # IA global, fuerte cobertura China
    ("https://www.theverge.com/rss/ai-...", 1.0),     # sección exclusiva de IA
    ("https://techcrunch.com/.../feed/", 0.9),         # categoría AI
    ("https://www.technologyreview.com/feed/", 0.8),   # MIT Tech Review
    ("https://pandaily.com/feed/", 0.7),               # tech china en general
    ("https://restofworld.org/feed/latest", 0.7),      # perspectiva global no-USA
    ("https://feeds.arstechnica.com/...", 0.6),        # generalista, más ruido
]
```

Para añadir o quitar fuentes, editar esta lista en `bot.py`. Cada feed que falle se ignora automáticamente.

## Pipeline de filtrado de artículos
El bot aplica estos pasos antes de enviar artículos a Gemini:

1. **Ventana de tiempo** — solo artículos de las últimas 72h
2. **Deduplicación por historial** — descarta URLs ya enviadas en los últimos 2 días (`sent_history.json`)
3. **Filtro de keywords** — descarta artículos sin al menos una keyword de IA en título o descripción
4. **Scoring y recorte** — ordena por `peso_fuente + bonus_recencia` y toma el top 25

El historial (`sent_history.json`) se persiste entre runs de GitHub Actions usando `actions/cache`.

## Recap mode
Si después del filtrado no quedan artículos nuevos, el bot entra en **recap mode**:
- Usa el pool completo de las últimas 72h (ignorando el historial de dedup)
- Gemini recibe un prompt diferente: presenta las noticias como "lo más relevante de los últimos días" (3-5 en lugar de 5-7)
- El header del mensaje cambia a `📰 Lo más relevante — {fecha}`
- No se actualiza el historial (los artículos ya estaban registrados)

## Prompt de Gemini
Hay dos prompts definidos en `generate_summary()` en `bot.py`:

**Modo normal** — selecciona 5-7 noticias de las últimas 24h, incluye lista de temas cubiertos ayer para evitar repetición temática.

**Recap mode** — selecciona 3-5 noticias de los últimos días, sin restricción de temas previos.

Ambos usan:
- Formato Telegram Markdown (`*negrita*`, `_cursiva_`, `[texto](url)`)
- Sección final "🔮 Tendencia del día"
- Tono informativo y conversacional, en español

Si se cambia el modelo de Gemini, actualizar tanto `bot.py` como este archivo.
