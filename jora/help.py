"""Help text formatting for key/label pairs."""

_DIM = "\033[90m"
_RESET = "\033[0m"


def format_help(items):
    """[key] label  [key] label — brackets dim, key normal, label dim."""
    return "  ".join(f"{_DIM}[{_RESET}{k}{_DIM}] {l}{_RESET}" for k, l in items)
