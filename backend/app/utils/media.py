"""Media paths exposed to browser clients."""


def playable_media_path(asset: object | None) -> str | None:
    """Return a safe browser playback path.

    Video previews are deliberately proxy-only.  Serving the original video
    when a proxy is missing makes the editor download/decode 4K or otherwise
    expensive source media and can leave the preview stuck on its poster frame.
    Images and audio do not need the video proxy and may use their source path.
    """
    if asset is None:
        return None
    media_type = getattr(asset, "media_type", None)
    preview_path = getattr(asset, "preview_path", None)
    file_path = getattr(asset, "file_path", None)
    if media_type == "video":
        return preview_path
    return preview_path or file_path
