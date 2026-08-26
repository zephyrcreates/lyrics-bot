from flask import Flask, request, jsonify
import requests
import os
import uuid
import re
import redis
import json

app = Flask(__name__)

LRCLIB_URL = "https://lrclib.net/api/search"

MAX_CHARS = 320
MAX_PARTS = 20

# --------------------------------------------------
# Redis Setup
# --------------------------------------------------
def get_redis():
    redis_url = os.environ.get("lyrics_bot_REDIS_URL") or os.environ.get("KV_URL")
    if redis_url:
        return redis.from_url(redis_url)
    return None

# --------------------------------------------------
# Transliteration
# --------------------------------------------------
def transliterate_lyrics(text):
    if text.isascii():
        return text

    key = os.environ.get("AZURE_TRANSLATOR_KEY")
    if not key:
        return text

    region = os.environ.get("AZURE_TRANSLATOR_REGION", "global")
    endpoint = "https://api.cognitive.microsofttranslator.com"
    url = f"{endpoint}/transliterate?api-version=3.0&language=hi&fromScript=Deva&toScript=Latn"

    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Ocp-Apim-Subscription-Region": region,
        "Content-type": "application/json",
        "X-ClientTraceId": str(uuid.uuid4())
    }

    body = [{"text": text}]

    try:
        req = requests.post(url, headers=headers, json=body, timeout=10)
        req.raise_for_status()
        res = req.json()
        return res[0]["text"]
    except Exception:
        return text

# --------------------------------------------------
# Split lyrics
# --------------------------------------------------
def split_lyrics(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 <= MAX_CHARS:
            current += ("\n" if current else "") + line
        else:
            if current:
                chunks.append(current)
            if len(line) > MAX_CHARS:
                words = line.split()
                current = ""
                for word in words:
                    candidate = word if not current else current + " " + word
                    if len(candidate) <= MAX_CHARS:
                        current = candidate
                    else:
                        if current:
                            chunks.append(current)
                        current = word
                        if len(chunks) >= MAX_PARTS:
                            break
            else:
                current = line
        if len(chunks) >= MAX_PARTS:
            break

    if current and len(chunks) < MAX_PARTS:
        chunks.append(current)

    return chunks[:MAX_PARTS]

# --------------------------------------------------
# API
# --------------------------------------------------
@app.route("/api/lyrics")
def lyrics():
    out_format = request.args.get("format", "json").lower()
    r = get_redis()
    
    # --- HANDLE !next COMMAND ---
    if request.args.get("next") == "true":
        if not r:
            return "Error: Database not configured in Vercel" if out_format == "text" else jsonify({"error": "No db"}), 500
            
        state_data = r.get("bot_state")
        if not state_data:
            return "No song is currently playing. Use !req <song> first!" if out_format == "text" else jsonify({"error": "No song playing"}), 404
            
        state = json.loads(state_data)
        chunks = state.get("chunks", [])
        next_part = state.get("next_part", 1)
        
        if next_part >= len(chunks):
            msg = f"No more lyrics for {state.get('title')} by {state.get('artist')}."
            return msg if out_format == "text" else jsonify({"message": msg})
            
        # Get chunk and update state
        chunk = chunks[next_part]
        state["next_part"] = next_part + 1
        r.set("bot_state", json.dumps(state), ex=3600) # expire in 1 hour
        
        if out_format == "text":
            return chunk.replace("\n", " / ")
        return jsonify({"lyrics": chunk, "part": next_part + 1, "title": state.get("title")})

    # --- HANDLE !req COMMAND ---
    song = request.args.get("song", "").strip()

    try:
        part = int(request.args.get("part", "1"))
    except ValueError:
        part = 1

    if not song:
        return "Error: No song provided" if out_format == "text" else jsonify({"error": "No song provided"}), 400

    if part < 1 or part > MAX_PARTS:
        return f"Error: Part must be between 1 and {MAX_PARTS}" if out_format == "text" else jsonify({"error": "Invalid part"}), 400

    try:
        response = requests.get(LRCLIB_URL, params={"q": song}, timeout=10)
        response.raise_for_status()
        results = response.json()

        if not results:
            return "Error: Song not found" if out_format == "text" else jsonify({"error": "Song not found"}), 404

        result = results[0]
        title = result.get("trackName", "Unknown Title")
        artist = result.get("artistName", "Unknown Artist")
        lyrics = result.get("plainLyrics")

        if not lyrics:
            return "Error: Lyrics unavailable" if out_format == "text" else jsonify({"error": "Lyrics unavailable"}), 404

        # Transliterate
        lyrics = transliterate_lyrics(lyrics)

        # Snippet Jump Logic
        q_lower = song.lower()
        title_lower = title.lower()
        
        if q_lower not in title_lower:
            lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
            for i, line in enumerate(lines):
                if q_lower in line.lower():
                    start_idx = max(0, i - 1)
                    lyrics = "\n".join(lines[start_idx:])
                    break

        # Split
        chunks = split_lyrics(lyrics)
        
        # Save to Database for !next command
        if r:
            state = {
                "title": title,
                "artist": artist,
                "chunks": chunks,
                "next_part": part # if they ask for part 1, next is 2
            }
            r.set("bot_state", json.dumps(state), ex=3600) # Expire in 1 hr

        if part > len(chunks):
            msg = f"No more lyrics for {title} by {artist}."
            return msg if out_format == "text" else jsonify({"message": msg})

        if out_format == "text":
            return chunks[part - 1].replace("\n", " / ")

        return jsonify({
            "title": title,
            "artist": artist,
            "part": part,
            "total_parts": len(chunks),
            "lyrics": chunks[part - 1]
        })

    except Exception as e:
        return f"Error: {str(e)}" if out_format == "text" else jsonify({"error": str(e)}), 500
