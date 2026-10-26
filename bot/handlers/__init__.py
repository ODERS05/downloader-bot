from aiogram import Router

from bot.handlers import download, start


def build_router() -> Router:
    """Order matters: commands first, then the catch-all text handler."""
    root = Router(name="root")
    root.include_routers(start.router, download.router)
    return root
