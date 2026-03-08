"""Help bar: filter enabled actions and format for display."""


def render_help(actions, state, row):
    """Return formatted help string from actions list."""
    pairs = [(a.key, a.label) for a in actions if a.enabled(state, row)]
    if not pairs:
        return ""
    return "  ".join(f"[{k}] {l}" for k, l in pairs)
