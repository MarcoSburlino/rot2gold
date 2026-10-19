"""Errors a stage can raise. Each has a message and a hint saying what to do next.

The CLI prints both and exits; the UI shows them as a banner.
"""


class VNError(Exception):
    hint = ""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        if hint is not None:
            self.hint = hint

    def __str__(self) -> str:
        msg = super().__str__()
        return f"{msg}\n{self.hint}" if self.hint else msg


class LockHeld(VNError):
    hint = "Wait for it to finish, or stop it (Ctrl+C in its terminal, or Stop in the app)."


class CookiesNeeded(VNError):
    hint = "Open Firefox, log into TikTok, then try again. Firefox can stay open."


class ListingFailed(VNError):
    hint = ("TikTok may have changed. Update the downloaders: "
            "uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl. "
            "Or paste the post URLs into the connection by hand.")


class Blocked(VNError):
    hint = ("TikTok may be blocking downloads. Update the downloaders: "
            "uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl")


class UsageLimit(VNError):
    hint = "Everything finished so far is saved. Run Extract again after the reset time."


class AgentFailed(VNError):
    hint = "The posts stay waiting and are retried on the next run."


class BrainError(VNError):
    hint = "Check `git -C ~/Projects/brain status` and `brain-index --check`."


class ToolMissing(VNError):
    pass
