# AI News Bot

Bot de Telegram que envía un resumen diario de las noticias más relevantes de IA a las 9am (hora Lima). Funciona 100% gratis usando GitHub Actions como scheduler y Gemini 2.0 Flash para generar el resumen.

## Cómo funciona

1. GitHub Actions dispara el script cada día a las 14:00 UTC (9am Lima)
2. `bot.py` lee 4 feeds RSS de fuentes de IA y filtra las noticias de las últimas 24 horas
3. Gemini 2.0 Flash selecciona las 5-7 más relevantes y genera un resumen en español
4. El resumen se envía a tu chat de Telegram

**Fuentes de noticias:**
- The Verge AI
- TechCrunch AI
- Ars Technica Technology Lab
- MIT Technology Review

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

A partir de ahora el bot se ejecutará automáticamente cada día a las 9am Lima.

---

## Ejecución local (para testing)

```bash
# 1. Clonar el repositorio
git clone <tu-repo>
cd news_agent

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Edita .env y rellena los 3 valores

# 5. Ejecutar
python bot.py
```

---

## Estructura del proyecto

```
news_agent/
├── .github/
│   └── workflows/
│       └── daily_news.yml   # Cron de GitHub Actions
├── bot.py                   # Script principal
├── requirements.txt         # Dependencias pinneadas
├── .env.example             # Plantilla de variables de entorno
└── README.md
```

## Stack

- **Python 3.11**
- **feedparser** — lectura de RSS feeds
- **google-genai** — Gemini 2.0 Flash API
- **python-telegram-bot** — envío de mensajes a Telegram
- **GitHub Actions** — ejecución gratuita del cron
