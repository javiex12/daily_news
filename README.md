# AI News Bot

Bot de Telegram que envía un resumen diario de las noticias más relevantes de IA a las 8am (hora Lima). Funciona 100% gratis usando GitHub Actions como scheduler y Gemini 2.5 Flash para generar el resumen.

## Cómo funciona

1. GitHub Actions dispara el script cada día a las 13:00 UTC (8am Lima)
2. `bot.py` lee 7 feeds RSS de fuentes de IA de las últimas 72 horas
3. Filtra artículos por keywords de IA, los puntúa por fuente y recencia, y toma el top 25
4. Gemini 2.5 Flash selecciona las 5-7 más relevantes y genera un resumen en español
5. El resumen se envía a tu chat de Telegram

**Fuentes de noticias:**
| Fuente | Cobertura | Peso |
|--------|-----------|------|
| Synced Review | IA global, fuerte en China | 1.0 |
| The Verge AI | Sección exclusiva de IA | 1.0 |
| TechCrunch AI | Startups y producto | 0.9 |
| MIT Technology Review | Análisis en profundidad | 0.8 |
| Pandaily | Tech china en general | 0.7 |
| Rest of World | Perspectiva global no-USA | 0.7 |
| Ars Technica | Tech generalista | 0.6 |

---

## Setup

### 1. Crear el bot de Telegram

1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot` y sigue las instrucciones
3. BotFather te dará un **token** como `123456789:ABCdef...` — guárdalo

### 2. Obtener tu Chat ID

1. Envía cualquier mensaje a tu nuevo bot
2. Abre esta URL en el navegador (reemplaza `<TOKEN>` con tu token real):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Busca el campo `"chat"` → `"id"` en la respuesta JSON — ese es tu **chat_id**

> Tip: si quieres recibir los mensajes en un grupo, añade el bot al grupo y usa el chat_id del grupo (será un número negativo).

### 3. Obtener la API key de Gemini

1. Ve a [Google AI Studio](https://aistudio.google.com/apikey)
2. Crea una nueva API key (el tier gratuito es suficiente)
3. Guarda la key

### 4. Configurar los secretos en GitHub

En tu repositorio de GitHub, ve a **Settings → Secrets and variables → Actions** y añade estos 3 secretos:

| Nombre | Valor |
|--------|-------|
| `TELEGRAM_TOKEN` | El token de tu bot |
| `TELEGRAM_CHAT_ID` | Tu chat id (número) |
| `GEMINI_API_KEY` | Tu API key de Google |

### 5. Activar el workflow

1. Ve a la pestaña **Actions** en tu repositorio
2. Si Actions no está habilitado, haz clic en "I understand my workflows, go ahead and enable them"
3. Haz clic en **"Daily AI News Bot"** → **"Run workflow"** para hacer una prueba manual
4. Verifica que el mensaje llegue a tu Telegram en ~1-2 minutos

A partir de ahora el bot se ejecutará automáticamente cada día a las 8am Lima.

---

## Ejecución local (para testing)

```bash
# 1. Clonar el repositorio
git clone <tu-repo>
cd news_agent

# 2. Crear entorno virtual e instalar dependencias
./setup.sh
source .venv/bin/activate

# 3. Configurar variables de entorno
cp .env.example .env
# Edita .env y rellena los 3 valores

# 4. Ejecutar
python bot.py
```

**Para probar el recap mode** (simula que no hay noticias nuevas):
```bash
python -c "
import json, datetime
fake = [{'url': f'https://fake.com/{i}', 'title': f'Fake {i}', 'date': datetime.date.today().isoformat()} for i in range(200)]
json.dump(fake, open('sent_history.json', 'w'))
"
python bot.py
# Luego borra el historial falso:
rm sent_history.json
```

---

## Estructura del proyecto

```
news_agent/
├── .github/
│   └── workflows/
│       └── daily_news.yml   # Cron de GitHub Actions + cache de historial
├── bot.py                   # Script principal
├── requirements.txt         # Dependencias pinneadas
├── .env.example             # Plantilla de variables de entorno
└── README.md
```

## Stack

- **Python 3.11**
- **feedparser** — lectura de RSS feeds
- **google-genai** — Gemini 2.5 Flash API
- **python-telegram-bot** — envío de mensajes a Telegram
- **GitHub Actions** — ejecución gratuita del cron + persistencia del historial
