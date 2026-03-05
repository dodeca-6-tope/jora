from jora import tmux
from jora.git import find_worktree, remove_worktree
from jora.actions.action import Action


class ReviewDelete(Action):
    key = "d"
    label = "delete"

    def run(self, s, pr):
        wt_key = f"review-{pr['number']}"
        if not find_worktree(wt_key):
            s.menu.message = "No worktree for this PR"
            return
        name = tmux.session_name(wt_key)
        if tmux.has_session(name):
            try:
                tmux.kill_session(name)
            except Exception:
                pass
        try:
            s.menu.run_blocking(f"Removing #{pr['number']}", lambda: remove_worktree(wt_key), inline=True)
            s.menu.message = f"Removed worktree for #{pr['number']}"
        except Exception as e:
            s.menu.message = f"Error: {e}"
        s.rebuild()
