import os
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client = None
_balance_locks: dict[str, asyncio.Lock] = {}


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("❌ SUPABASE_URL y SUPABASE_KEY deben estar en el archivo .env")
        _client = create_client(url, key)
    return _client


def get_balance_lock(user_id: str) -> asyncio.Lock:
    """Devuelve un Lock por usuario para serializar actualizaciones de balance."""
    if user_id not in _balance_locks:
        _balance_locks[user_id] = asyncio.Lock()
    return _balance_locks[user_id]
