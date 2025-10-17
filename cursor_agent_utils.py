#!/usr/bin/env python3

import json
import subprocess
import sys
import time
from io import StringIO
from rich.console import Console
from rich.text import Text

console = Console()


def print_stream(text: str, style: str = "bright_black", end: str = ""):
    """Print streaming output with continuous vertical line on each wrapped line."""
    # Create styled text object
    styled_text = Text(text, style=style)

    # Pre-render text with proper width to get wrapped lines
    temp_console = Console(file=StringIO(), width=console.width - 2, highlight=False)
    temp_console.print(styled_text, end="")
    wrapped_lines = temp_console.file.getvalue().split("\n")

    # Print each wrapped line with vertical bar prefix, preserving style
    for i, line in enumerate(wrapped_lines):
        is_last_line = i == len(wrapped_lines) - 1
        # Use Text object to preserve styling
        styled_line = Text()
        styled_line.append("│", style="dim")
        styled_line.append(" ")
        styled_line.append(line, style=style)
        console.print(styled_line, end=end if is_last_line else "\n", highlight=False)


class CursorAgentStreamHandler:
    """Handles formatting and display of cursor-agent streaming output."""

    def __init__(self):
        """Initialize the stream handler."""
        self.pending_assistant_text = ""
        self.last_flushed_assistant_text = ""
        self.tool_count = 0

    def _flush_assistant(self) -> None:
        """Print any pending assistant text once, avoiding duplicates and awkward breaks."""
        if (
            not self.pending_assistant_text
            or self.pending_assistant_text == self.last_flushed_assistant_text
        ):
            self.pending_assistant_text = ""
            return

        # Add 2 blank lines before assistant messages (except the very first one)
        if self.last_flushed_assistant_text or self.tool_count > 0:
            console.print()
            console.print()

        print_stream(self.pending_assistant_text, style="bright_black italic", end="\n")
        self.last_flushed_assistant_text = self.pending_assistant_text
        self.pending_assistant_text = ""

    def _get_tool_info(self, tool_call: dict) -> tuple[str, str]:
        """Extract tool name and target from tool_call data."""

        def get_arg(tool_type: str, arg_name: str, default: str = "unknown") -> str:
            return tool_call.get(tool_type, {}).get("args", {}).get(arg_name, default)

        tool_map = {
            "writeToolCall": (
                "🔧",
                lambda: f"Creating {get_arg('writeToolCall', 'path')}",
            ),
            "readToolCall": (
                "📖",
                lambda: f"Reading {get_arg('readToolCall', 'path')}",
            ),
            "grepToolCall": (
                "🔍",
                lambda: f"Searching for '{get_arg('grepToolCall', 'pattern')}'",
            ),
            "searchReplaceToolCall": (
                "✏️",
                lambda: f"Editing {get_arg('searchReplaceToolCall', 'file_path')}",
            ),
        }

        # Handle terminal/shell commands (they're the same)
        for cmd_type in ["terminalToolCall", "shellToolCall"]:
            if cmd_type in tool_call:
                cmd = get_arg(cmd_type, "command")
                cmd = cmd if len(cmd) <= 80 else cmd[:77] + "..."
                return "💻", f"Running {cmd}"

        # Handle other tool types
        for tool_type, (icon, desc_func) in tool_map.items():
            if tool_type in tool_call:
                return icon, desc_func()

        # Fallback for unknown tool types
        tool_name = list(tool_call.keys())[0] if tool_call else "unknown"
        return "🔧", tool_name

    def process_stream_line(self, line: str) -> None:
        """Process a single line of streaming JSON output and display it in a user-friendly format."""
        if not line.strip():
            return

        try:
            data = json.loads(line)
            event_type = data.get("type", "")
            subtype = data.get("subtype", "")

            if event_type == "system" and subtype == "init":
                model = data.get("model", "unknown")
                print_stream(f"🤖 Model: {model}", end="\n")
                console.print()

            elif event_type == "assistant":
                content = data.get("message", {}).get("content", [])
                if content and isinstance(content, list):
                    event_text = "".join(
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("text")
                    )
                    if event_text:
                        self.pending_assistant_text = event_text

            elif event_type == "tool_call":
                if subtype == "started":
                    self._flush_assistant()
                    self.tool_count += 1
                    icon, description = self._get_tool_info(data.get("tool_call", {}))
                    # Add newline before each tool call for clear separation
                    if self.tool_count > 1 or self.last_flushed_assistant_text:
                        console.print()
                    print_stream(f"{icon} {description}")

            elif event_type == "result":
                self._flush_assistant()
                console.print()
                print_stream(f"✓ Completed ({self.tool_count} tools)", end="\n")

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"\n⚠️  Error parsing stream: {e}", file=sys.stderr)

    def reset(self):
        """Reset the handler state for a new stream."""
        self.pending_assistant_text = ""
        self.last_flushed_assistant_text = ""
        self.tool_count = 0


def run_cursor_agent(
    prompt: str, handler: CursorAgentStreamHandler, phase_name: str = "Task"
) -> int:
    """Run cursor-agent with the given prompt and stream handler.

    Args:
        prompt: The prompt to send to cursor-agent
        handler: The stream handler to use for output
        phase_name: Name of the phase for display (e.g., "Implementation", "Review")

    Returns:
        The exit code from cursor-agent
    """
    start_time = time.time()

    # Run cursor-agent with streaming output
    process = subprocess.Popen(
        [
            "cursor-agent",
            "--force",
            "--model",
            "sonnet-4.5-thinking",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "-p",
            prompt,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Process streaming output line by line
    if process.stdout:
        for line in process.stdout:
            handler.process_stream_line(line)

    # Wait for process to complete
    process.wait()

    # Calculate elapsed time
    elapsed_time = int(time.time() - start_time)

    if process.returncode == 0:
        print(f"\n✅ {phase_name} completed successfully in {elapsed_time}s")
    else:
        print(f"\n❌ {phase_name} exited with code {process.returncode}")
        # Show stderr if there was an error
        if process.stderr:
            stderr_output = process.stderr.read()
            if stderr_output:
                print(f"Error output: {stderr_output}", file=sys.stderr)

    return process.returncode
