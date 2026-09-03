from datetime import datetime, timedelta, timezone
import hashlib, hmac
from pwdlib import PasswordHash
from .config import get_settings

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str: return password_hash.hash(password)
def verify_password(password: str, value: str) -> bool: return password_hash.verify(password, value)

def make_session(user_id: int) -> str:
    expires = int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
    body = f"{user_id}.{expires}"
    sig = hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def read_session(token: str | None) -> int | None:
    try:
        uid, expires, sig = (token or "").split(".")
        body = f"{uid}.{expires}"
        expected = hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected) or int(expires) < datetime.now(timezone.utc).timestamp(): return None
        return int(uid)
    except (ValueError, AttributeError): return None

