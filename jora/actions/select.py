from jora.actions.action import Action
from jora.term import pick, suspend, resume


def pick_repo(s, task_id):
    repos = s.repos()
    if not repos:
        s.menu.message = "No repos. Run: jora add <path>"
        return None
    idx = pick(f"Repo for {task_id}", repos)
    return repos[idx] if idx is not None else None


class Select(Action):
    key = "⏎"
    label = "open"
    aliases = ("enter", "s")

    def run(self, s, row):
        if not s.has_session(row.wt_key):
            try:
                if "identifier" in row.data:
                    repo = pick_repo(s, row.data["identifier"]) if not s.has_worktree(row.wt_key) else None
                    if not s.has_worktree(row.wt_key) and not repo:
                        return
                    s.menu.spin("Opening", lambda: s.open_task(row.data["identifier"], repo))
                else:
                    s.menu.spin("Opening", lambda: s.open_review(row.data))
            except Exception as e:
                s.menu.message = f"Error: {e}"
                return

        suspend()
        s.attach(row.wt_key)
        resume()
