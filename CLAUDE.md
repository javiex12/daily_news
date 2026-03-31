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
- Si no hay noticias o Gemini falla, se envía un mensaje de fallback a Telegram avisando del error
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
```python
RSS_FEEDS = [
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.technologyreview.com/feed/",
]
```

Para añadir o quitar fuentes, editar esta lista en `bot.py`. Cada feed que falle se ignora automáticamente.

## Prompt de Gemini
El prompt está definido en `generate_summary()` en `bot.py`. Instrucciones clave:
- Seleccionar 5-7 noticias más relevantes
- Resumen de 2-3 líneas por noticia explicando qué pasó y por qué importa
- Sección final "🔮 Tendencia del día"
- Formato Telegram Markdown (`*negrita*`, `_cursiva_`, `[texto](url)`)
- Tono informativo y conversacional, en español

Si se cambia el modelo de Gemini, actualizar tanto `bot.py` como este archivo.
