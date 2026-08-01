"""Dialogue-first hunt planning for JPS One."""

__all__ = ["HuntCopilotService"]


def __getattr__(name: str):
    if name == "HuntCopilotService":
        from hunt_copilot.service import HuntCopilotService

        return HuntCopilotService
    raise AttributeError(name)
