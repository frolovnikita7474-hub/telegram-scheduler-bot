"""Конфигурация бота"""
import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "0"))
    TIMEZONE_OFFSET: int = int(os.getenv("TIMEZONE_OFFSET", "3"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///bot.db")