from jora import agent, tmux
from jora.git import find_worktree, is_worktree_clean
from jora.actions.select import _ensure_task_worktree
from jora.actions.action import Action


class Fix(Action):
    key = "f"
    label = "fix"

    def run(self, s, row):
        task_id = row.data["identifier"]
        name = tmux.session_name(row.wt_key)
        if tmux.has_session(name):
            s.menu.message = "Session already running — use ⏎ to attach"
            return
        wt = find_worktree(row.wt_key)
        if wt and not is_worktree_clean(wt):
            s.menu.message = "Worktree has changes — use ⏎ to attach"
            return
        if not wt:
            wt = _ensure_task_worktree(s, task_id)
            if not wt:
                return
        try:
            tmux.create_session(name, str(wt))
        except Exception as e:
            s.menu.message = f"Error: {e}"
            return
        tmux.send_keys(name, agent.command(task_id))
        s.rebuild()
