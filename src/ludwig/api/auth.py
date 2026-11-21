"""Personal logins (PLAN 6.5): scrypt password hashes, server-side sessions, admin-managed users.

Once one user exists, every API call needs a session cookie or the shared API token. With
no users and no token the service stays open, as for a local single-person install.
"""


import base64
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ludwig.api.activity import log
from ludwig.api.db import User, UserSession, iso
from ludwig.api.guards import token_ok

COOKIE = "ludwig_session"
MIN_PASSWORD = 10
# OWASP password storage cheat sheet, scrypt: N=2^17, r=8, p=1 (about 128 MiB per hash).
_N, _R, _P = 2**17, 8, 1
_MAXMEM = 256 * 1024 * 1024
_FAILS: dict[str, list[float]] = {}
FAIL_WINDOW_S, FAIL_LIMIT = 15 * 60, 10


def hash_password(password: str) -> str:
    """scrypt hash with a random salt, as `scrypt$N$r$p$salt$hash` (base64)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """True when the password matches the stored hash (constant-time compare)."""
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        found = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n),
                               r=int(r), p=int(p), maxmem=_MAXMEM)  # fmt: skip
        return hmac.compare_digest(found, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


_DUMMY = hash_password(secrets.token_urlsafe(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    # Stored naive in UTC, as SQLite returns it.
    return datetime.now(UTC).replace(tzinfo=None)


def check_password(password: str) -> None:
    """Raise ValueError when a new password is too weak to accept."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"a password needs at least {MIN_PASSWORD} characters")


def create_user(session: Session, name: str, password: str, admin: bool = False) -> User:
    """Add a user; raises ValueError for a taken name or a short password."""
    name = name.strip()
    if not name:
        raise ValueError("a user needs a name")
    if session.query(User).filter(User.name == name).first():
        raise ValueError(f"user {name!r} exists")
    check_password(password)
    user = User(name=name, password_hash=hash_password(password), is_admin=admin)
    session.add(user)
    session.commit()
    return user


def has_users(session: Session) -> bool:
    """True once anyone can sign in; from then on the API needs a signed-in user."""
    return session.query(User.id).first() is not None


class LoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)
    admin: bool = False


class UserChange(BaseModel):
    password: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    admin: bool | None = None


def _user(u: User) -> dict[str, Any]:
    return {"id": u.id, "name": u.name, "admin": u.is_admin, "active": u.active,
            "created": iso(u.created)}  # fmt: skip


def router(settings: Any, sessions: Any) -> tuple[APIRouter, Any, Any]:
    """The /api/auth and /api/users routes, plus the dependencies that guard the API."""

    def db() -> Any:
        with sessions() as session:
            yield session

    DB = Annotated[Session, Depends(db)]

    def identify(request: Request, session: Session) -> tuple[bool, User | None, str | None]:
        """(allowed, user, name to log) for this request."""
        auth = request.headers.get("authorization", "")
        if settings.api_token and auth.startswith("Bearer "):
            ok = token_ok(settings.api_token, auth.removeprefix("Bearer ").strip())
            return ok, None, "api token" if ok else None
        cookie = request.cookies.get(COOKIE)
        if cookie:
            row = (session.query(UserSession)
                   .filter(UserSession.token_hash == _token_hash(cookie)).first())  # fmt: skip
            if row is not None and row.expires > _now():
                user = session.get(User, row.user_id)
                if user is not None and user.active:
                    return True, user, user.name
        if settings.api_token is None and not has_users(session):
            return True, None, None
        return False, None, None

    def require_user(request: Request, session: DB) -> None:
        allowed, user, name = identify(request, session)
        if not allowed:
            raise HTTPException(401, "sign in first")
        request.state.user = user
        request.state.user_name = name

    def require_admin(request: Request, session: DB) -> None:
        require_user(request, session)
        user = request.state.user
        # An open install (no users yet) may create the first admin.
        if user is None and has_users(session):
            raise HTTPException(403, "only an admin can do this")
        if user is not None and not user.is_admin:
            raise HTTPException(403, "only an admin can do this")

    auth = APIRouter(prefix="/api")

    @auth.post("/auth/login")
    def login(body: LoginIn, request: Request, response: Response, session: DB) -> dict:
        now = time.monotonic()
        fails = [t for t in _FAILS.get(body.name, []) if now - t < FAIL_WINDOW_S]
        if len(fails) >= FAIL_LIMIT:
            raise HTTPException(429, "too many failed sign-ins; try again in 15 minutes")
        user = session.query(User).filter(User.name == body.name.strip()).first()
        # Hash even for an unknown name, so timing does not tell which names exist.
        stored = user.password_hash if user is not None else _DUMMY
        good = verify_password(body.password, stored)
        if user is None or not user.active or not good:
            _FAILS[body.name] = [*fails, now]
            raise HTTPException(401, "wrong name or password")
        _FAILS.pop(body.name, None)
        token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(days=settings.session_days)
        session.add(UserSession(token_hash=_token_hash(token), user_id=user.id,
                                created=_now(), expires=expires))  # fmt: skip
        log(session, user.name, "sign in")
        session.commit()
        response.set_cookie(COOKIE, token, max_age=settings.session_days * 86400,
                            httponly=True, samesite="lax", secure=settings.secure_cookies,
                            path="/")  # fmt: skip
        return _user(user)

    @auth.post("/auth/logout")
    def logout(request: Request, response: Response, session: DB) -> dict:
        cookie = request.cookies.get(COOKIE)
        if cookie:
            session.query(UserSession).filter(
                UserSession.token_hash == _token_hash(cookie)).delete()  # fmt: skip
            session.commit()
        response.delete_cookie(COOKIE, path="/")
        return {"signed_out": True}

    @auth.get("/auth/me")
    def me(request: Request, session: DB) -> dict:
        allowed, user, name = identify(request, session)
        return {"signed_in": allowed, "user": _user(user) if user else None, "name": name,
                "login_required": has_users(session) or settings.api_token is not None}  # fmt: skip

    users = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])

    @users.get("/users")
    def list_users(session: DB) -> list[dict]:
        return [_user(u) for u in session.query(User).order_by(User.name)]

    @users.post("/users", status_code=201)
    def add_user(body: UserIn, request: Request, session: DB) -> dict:
        first = not has_users(session)
        try:
            # The first user is always an admin, or nobody could manage the others.
            user = create_user(session, body.name, body.password, admin=body.admin or first)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        log(session, request.state.user_name, "user added", user=user.name, admin=user.is_admin)
        session.commit()
        return _user(user)

    @users.patch("/users/{user_id}")
    def change_user(user_id: int, body: UserChange, request: Request, session: DB) -> dict:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(404, "no such user")
        me_ = request.state.user
        if me_ is not None and me_.id == user.id and (body.active is False or body.admin is False):
            raise HTTPException(422, "you cannot remove your own admin rights or account")
        changed = []
        if body.password is not None:
            try:
                check_password(body.password)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            user.password_hash = hash_password(body.password)
            session.query(UserSession).filter(UserSession.user_id == user.id).delete()
            changed.append("password")
        if body.active is not None:
            user.active = body.active
            if not body.active:
                session.query(UserSession).filter(UserSession.user_id == user.id).delete()
            changed.append("active" if body.active else "deactivated")
        if body.admin is not None:
            user.is_admin = body.admin
            changed.append("admin" if body.admin else "not admin")
        log(session, request.state.user_name, "user changed", user=user.name, changes=changed)
        session.commit()
        return _user(user)

    return auth, users, require_user
