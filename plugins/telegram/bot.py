"""Telegram bot that bridges messages to a Claude agent with jora tools."""

import json
import os
import subprocess
import sys
import threading

import telebot

SYSTEM_PROMPT = """\
You are a task management assistant. You can inspect the user's tasks, \
reviews, and worktrees by running jora commands.

Available commands:
  jora get tasks      — list tasks as JSON
  jora get reviews    — list reviews as JSON
  jora peek <task_id> — show tmux session content for a task
  jora diff <task_id> — show git diff for a task worktree

Be brief — 1-3 sentences max. Use plain text, not markdown.\
"""

_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
_session_id = None
_lock = threading.Lock()


def _ask_agent(text: str) -> str:
    global _session_id
    with _lock:
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--append-system-prompt",
            SYSTEM_PROMPT,
            "--allowedTools",
            "Bash(jora *)",
        ]
        if _session_id:
            cmd += ["--resume", _session_id]
        cmd += ["--", text]
        result = subprocess.run(cmd, capture_output=True, text=True, env=_env)
        if result.returncode != 0:
            return f"Error: {result.stderr.strip() or 'unknown failure'}"
        try:
            data = json.loads(result.stdout)
            _session_id = data.get("session_id", _session_id)
            return data.get("result", result.stdout.strip())
        except json.JSONDecodeError:
            return result.stdout.strip() or "(no response)"


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)

    allowed_user = os.environ.get("TELEGRAM_USER_ID")

    bot = telebot.TeleBot(token)

    @bot.message_handler(content_types=["text"])
    def handle(message):
        if allowed_user and str(message.from_user.id) != allowed_user:
            return
        stop = threading.Event()

        def typing_loop():
            while not stop.is_set():
                bot.send_chat_action(message.chat.id, "typing")
                stop.wait(3)

        t = threading.Thread(target=typing_loop, daemon=True)
        t.start()
        try:
            reply = _ask_agent(message.text)
        except Exception as e:
            reply = f"Error: {e}"
        finally:
            stop.set()
            t.join()
        bot.reply_to(message, reply)

    print("Bot started")
    bot.infinity_polling()


if __name__ == "__main__":
    main()
