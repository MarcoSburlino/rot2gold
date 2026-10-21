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
    hint = "Log into TikTok in the browser set for this collection (its ⋯ menu → Cookies), then try again."


class ListingFailed(VNError):
    hint = ("TikTok may have changed. Update the downloaders (Settings → About → Update downloaders, "
            "or `r2g update-downloaders`), or paste the post URLs into the collection by hand.")


class Blocked(VNError):
    hint = ("TikTok may be blocking downloads. Update the downloaders (Settings → About → Update downloaders, "
            "or `r2g update-downloaders`), and wait a while before the next Extract.")


class UsageLimit(VNError):
    hint = "Everything finished so far is saved. Run it again after the reset time."


class AgentFailed(VNError):
    hint = "The posts stay waiting and are retried on the next run."


class BrainError(VNError):
    hint = "Check your vault: `git status` in it, and any after-write commands in your config.toml."


class ToolMissing(VNError):
    pass
