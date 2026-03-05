from jora import tmux
from jora.git import clean_worktrees
from jora.actions.action import Action


class Clean(Action):
    key = "c"
    label = "clean"

    def run(self, s, _row):
        try:
            removed = s.menu.run_blocking("Cleaning worktrees", clean_worktrees, inline=True)
            for key in removed:
                name = tmux.session_name(key)
                if tmux.has_session(name):
                    tmux.kill_session(name)
            n = len(removed)
            s.menu.message = f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean"
            if n:
                s.rebuild()
        except Exception as e:
            s.menu.message = f"Error: {e}"
