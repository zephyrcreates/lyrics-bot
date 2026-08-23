# Lyrics Bot API

A lightweight, serverless Python API designed to fetch, transliterate, and format song lyrics for Twitch and YouTube chat bots like Nightbot.

## Features
- **Fetch Lyrics**: Automatically searches and retrieves lyrics using the [lrclib](https://lrclib.net/) API.
- **Transliteration**: Uses the **Azure Translator API** to convert Devanagari (Hindi) scripts into Latin (Roman) alphabet so viewers can easily read the lyrics in chat.
- **Chunking**: Intelligently splits lyrics into Nightbot-safe chunks (under 400 characters) without breaking words.
- **Chat-Friendly Formatting**: Replaces newlines with slashes (` / `) to prevent text from being squished together in live chats.
- **Serverless**: Built with Flask and designed to be deployed directly to Vercel.

## Setup

### 1. Environment Variables
To run this project, you will need to set up the following environment variables (in Vercel, or a local `.env` file):
- `AZURE_TRANSLATOR_KEY` - Your Microsoft Azure Translator API key.
- `AZURE_TRANSLATOR_REGION` - The region of your Azure resource (e.g., `global`, `eastus`).

### 2. Deployment
This project is configured to deploy directly to Vercel via the `vercel.json` file.
```bash
npm i -g vercel
vercel --prod
```

## Nightbot Integration
You can link this API to Nightbot using the `$(urlfetch)` variable.

**Part 1:**
```text
!addcom !req $(urlfetch https://YOUR-VERCEL-URL.vercel.app/api/lyrics?song=$(querystring)&part=1&format=text)
```
**Part 2:**
```text
!addcom !req2 $(urlfetch https://YOUR-VERCEL-URL.vercel.app/api/lyrics?song=$(querystring)&part=2&format=text)
```
