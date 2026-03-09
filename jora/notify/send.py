import subprocess


def send(body: str):
    safe = body.replace('"', '\\"')
    subprocess.Popen(
        ["osascript", "-e", f'display notification "{safe}" with title "Jora"'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
