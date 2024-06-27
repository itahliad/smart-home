import subprocess


def send(phone_number: str, message: str) -> None:
    script = f"""
        on run {{targetBuddyPhone, targetMessage}}
            tell application "Messages"
                set targetService to 1st service whose service type = iMessage
                set targetBuddy to buddy targetBuddyPhone of targetService
                send targetMessage to targetBuddy
            end tell
        end run
    """

    subprocess.Popen(
        ["osascript", "-"] + [phone_number, message],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).communicate(script.encode("utf-8"))
