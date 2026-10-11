"""Safe YouTube player URLs; arbitrary admin URLs remain ordinary links."""

import re
from urllib.parse import parse_qs, urlsplit


VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_clip_seconds(url):
    """Optional end= seconds for an embedded demonstration clip."""
    if not youtube_embed_url(url):
        return 0
    try:
        values = parse_qs(urlsplit(url).query).get("end", [])
        seconds = int(values[0]) if len(values) == 1 else 0
        return seconds if 10 <= seconds <= 7200 else 0
    except (ValueError, TypeError):
        return 0


def youtube_embed_url(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return ""
        if host == "youtu.be":
            video_id = parsed.path.strip("/") if parsed.path.count("/") == 1 else ""
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                ids = parse_qs(parsed.query).get("v", [])
                video_id = ids[0] if len(ids) == 1 else ""
            elif parsed.path.startswith("/embed/") and parsed.path.count("/") == 2:
                video_id = parsed.path.split("/")[-1]
            else:
                return ""
        else:
            return ""
        return f"https://www.youtube-nocookie.com/embed/{video_id}" if VIDEO_ID.fullmatch(video_id) else ""
    except ValueError:
        return ""
