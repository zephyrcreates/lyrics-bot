from flask import Flask, request, jsonify
import requests
import os
import uuid
import re

app = Flask(__name__)

LRCLIB_URL = "https://lrclib.net/api/search"

MAX_CHARS = 320
MAX_PARTS = 3


# --------------------------------------------------
# Transliteration
# --------------------------------------------------

def transliterate_lyrics(text):
    # Keep English / Roman lyrics unchanged
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
    # Preserve line breaks initially
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    chunks = []
    current = ""

    for line in lines:

        # If the entire line fits
        if len(current) + len(line) + 1 <= MAX_CHARS:
            current += (
                "\n" if current else ""
            ) + line

        else:
            # Save current chunk
            if current:
                chunks.append(current)

            # If line itself is too long, split by words
            if len(line) > MAX_CHARS:

                words = line.split()
                current = ""

                for word in words:

                    candidate = (
                        word
                        if not current
                        else current + " " + word
                    )

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

    song = request.args.get("song", "").strip()
    out_format = request.args.get("format", "json").lower()

    try:
        part = int(request.args.get("part", "1"))
    except ValueError:
        part = 1

    if not song:
        return "Error: No song provided" if out_format == "text" else jsonify({"error": "No song provided"}), 400

    if part < 1 or part > 3:
        return "Error: Part must be 1, 2 or 3" if out_format == "text" else jsonify({"error": "Part must be 1, 2 or 3"}), 400

    try:

        response = requests.get(
            LRCLIB_URL,
            params={"q": song},
            timeout=10
        )

        response.raise_for_status()

        results = response.json()

        if not results:
            return "Error: Song not found" if out_format == "text" else jsonify({"error": "Song not found"}), 404

        result = results[0]

        title = result.get(
            "trackName",
            "Unknown Title"
        )

        artist = result.get(
            "artistName",
            "Unknown Artist"
        )

        lyrics = result.get("plainLyrics")

        if not lyrics:
            return "Error: Lyrics unavailable" if out_format == "text" else jsonify({"error": "Lyrics unavailable"}), 404

        # Transliterate
        lyrics = transliterate_lyrics(lyrics)

        # Split
        chunks = split_lyrics(lyrics)

        if part > len(chunks):
            msg = f"No more lyrics for {title} by {artist}."
            return msg if out_format == "text" else jsonify({
                "message": msg,
                "title": title,
                "artist": artist
            })

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
