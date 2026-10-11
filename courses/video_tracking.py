"""A best-effort watch gate for supported YouTube embeds.

The server limits reported playback by elapsed wall time. A browser owner can
still forge requests, so this is a course flow rule, not proof of attendance.
"""

from .video import youtube_embed_url


def video_required(module):
    return bool(youtube_embed_url(module.video_url))


def video_watched(progress, module):
    return not video_required(module) or bool(
        progress and progress.video_completed_at and progress.video_url_seen == module.video_url
    )
