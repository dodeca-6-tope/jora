from jora.actions.action import Action


def _pick_repo(s, task_id):
    from jora.app import pick

    repos = s.repos()
    if not repos:
        s.on_alert("No repos. Run: jora add <path>")
        return None
    idx = pick(f"Repo for {task_id}", repos)
    return repos[idx] if idx is not None else None


class Fix(Action):
    key = "f"
    label = "fix"

    def run(self, s, row):
        task_id = row.data.id
        if not s.worktree_path(task_id):
            repo = _pick_repo(s, task_id)
            if not repo:
                return
            s.run(lambda: s.fix(task_id, repo), "Starting fix")
        else:
            s.fix(task_id)
