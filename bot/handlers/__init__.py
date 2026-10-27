from aiogram import Router

from bot.handlers import admin, download, start


def build_router() -> Router:
    """Order matters: commands and owner-only buttons first, then the catch-all text handler."""
    root = Router(name="root")
    root.include_routers(start.router, admin.router, download.router)
    return root
