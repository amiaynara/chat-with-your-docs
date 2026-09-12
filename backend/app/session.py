import uuid

from fastapi import Request, Response

from app.config import settings


def get_session_id(request: Request, response: Response) -> str:
    """Anonymous session identity via an httpOnly, secure cookie — no login/accounts.

    Scopes each user's documents to their own browser session. `secure=True` is
    safe even for local http://localhost dev — browsers treat localhost as a
    secure context and still send Secure cookies over plain HTTP there.
    """
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id is None:
        session_id = str(uuid.uuid4())
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_id,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
        )
    return session_id
