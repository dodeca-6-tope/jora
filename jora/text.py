"""Text utilities for terminal display."""

from wcwidth import wcswidth

_SEP = "  "
_MARGIN = 1


def word_wrap(chunks: list[str], width: int) -> list[str]:
    """Wrap *chunks* into lines that fit within *width*, joining with two-space sep."""
    width -= _MARGIN
    lines: list[str] = []
    cur = ""
    cur_w = 0
    for chunk in chunks:
        chunk_w = wcswidth(chunk)
        new_w = chunk_w if not cur else cur_w + len(_SEP) + chunk_w
        if new_w <= width:
            cur = chunk if not cur else cur + _SEP + chunk
            cur_w = new_w
        else:
            if cur:
                lines.append(cur)
            cur = chunk
            cur_w = chunk_w
    if cur:
        lines.append(cur)
    return lines
