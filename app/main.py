from typing import Any
from urllib.parse import quote_plus
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlmodel import select
from app.db import open_session
from app.models import User
from app.routers import root, search, settings, wishlist
from app.util.auth import RequiresLoginException

app = FastAPI()

app.include_router(root.router)
app.include_router(search.router)
app.include_router(wishlist.router)
app.include_router(settings.router)

user_exists = False


@app.exception_handler(RequiresLoginException)
async def redirect_to_login(request: Request, exc: RequiresLoginException):
    if request.method == "GET":
        if exc.detail:
            return RedirectResponse(f"/login?error={quote_plus(exc.detail)}")
        return RedirectResponse("/login")
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.middleware("http")
async def redirect_to_init(request: Request, call_next: Any):
    """
    Initial redirect if no user exists. We force the user to create a new login
    """
    global user_exists
    if (
        not user_exists
        and request.url.path not in ["/init", "/globals.css"]
        and request.method == "GET"
    ):
        with open_session() as session:
            user_count = session.exec(select(func.count()).select_from(User)).one()
            if user_count == 0:
                return RedirectResponse("/init")
            else:
                user_exists = True
    elif user_exists and request.url.path.startswith("/init"):
        return RedirectResponse("/")
    response = await call_next(request)
    return response
