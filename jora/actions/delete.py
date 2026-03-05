from jora import tmux
from jora.git import find_worktree, remove_worktree
from jora.actions.action import Action


class Delete(Action):
    key = "d"
    label = "delete"

    def run(self, s, row):
        if not find_worktree(row.wt_key):
            s.menu.message = "No worktree for this PR"
            return
        name = tmux.session_name(row.wt_key)
        if tmux.has_session(name):
            try:
                tmux.kill_session(name)
            except Exception:
                pass
        try:
            s.menu.run_blocking(f"Removing {row.key}", lambda: remove_worktree(row.wt_key), inline=True)
            s.menu.message = f"Removed worktree for {row.key}"
        except Exception as e:
            s.menu.message = f"Error: {e}"
        s.rebuild()
