from typing import Annotated, Optional

import sqlalchemy as sa
from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import (
    BookRequest,
    BookSearchResult,
    EventEnum,
    GroupEnum,
    ManualBookRequest,
    Notification,
)
from app.routers.wishlist import background_start_query, get_wishlist_books
from app.util.auth import DetailedUser, get_authenticated_user
from app.util.book_search import (
    audible_region_type,
    audible_regions,
    get_audnexus_book,
    list_audible_books,
)
from app.util.connection import get_connection
from app.util.notifications import send_manual_notification, send_notification
from app.util.ranking.quality import quality_config
from app.util.templates import template_response

router = APIRouter(prefix="/search")


def get_already_requested(session: Session, results: list[BookRequest], username: str):
    books: list[BookSearchResult] = []
    if len(results) > 0:
        # check what books are already requested by the user
        asins = {book.asin for book in results}
        requested_books = set(
            session.exec(
                select(BookRequest.asin).where(
                    col(BookRequest.asin).in_(asins),
                    BookRequest.user_username == username,
                )
            ).all()
        )

        for book in results:
            book_search = BookSearchResult.model_validate(book)
            if book.asin in requested_books:
                book_search.already_requested = True
            books.append(book_search)
    return books


@router.get("")
async def read_search(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
    q: Optional[str] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type = "us",
):
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if q:
        results = await list_audible_books(
            session=session,
            client_session=client_session,
            query=q,
            num_results=num_results,
            page=page,
            audible_region=region,
        )
    else:
        results = []

    books: list[BookSearchResult] = []
    if len(results) > 0:
        books = get_already_requested(session, results, user.username)

    return template_response(
        "search.html",
        request,
        user,
        {
            "search_term": q or "",
            "search_results": books,
            "regions": list(audible_regions.keys()),
            "selected_region": region,
            "page": page,
            "num_results": num_results,
            "auto_start_download": quality_config.get_auto_download(session)
            and user.is_above(GroupEnum.trusted),
        },
    )


@router.post("/request/{asin}")
async def add_request(
    request: Request,
    asin: str,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
):
    book = await get_audnexus_book(client_session, asin)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    book.user_username = user.username
    try:
        session.add(book)
        session.commit()
    except sa.exc.IntegrityError:
        pass  # ignore if already exists

    if quality_config.get_auto_download(session):
        background_task.add_task(
            background_start_query,
            asin=asin,
            start_auto_download=user.is_above(GroupEnum.trusted),
        )

    notifications = session.exec(
        select(Notification).where(Notification.event == EventEnum.on_new_request)
    ).all()
    for notif in notifications:
        background_task.add_task(
            send_notification,
            notification=notif,
            requester_username=user.username,
            book_asin=asin,
        )

    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.delete("/request/{asin}")
async def delete_request(
    request: Request,
    asin: str,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    downloaded: Optional[bool] = None,
):
    books = session.exec(select(BookRequest).where(BookRequest.asin == asin)).all()
    if books:
        [session.delete(b) for b in books]
        session.commit()

    books = get_wishlist_books(
        session, None, "downloaded" if downloaded else "not_downloaded"
    )

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        admin_user,
        {"books": books, "page": "downloaded" if downloaded else "wishlist"},
        block_name="book_wishlist",
    )


@router.get("/manual")
async def read_manual(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
):
    return template_response("manual.html", request, user, {})


@router.post("/manual")
async def add_manual(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    title: Annotated[str, Form()],
    author: Annotated[str, Form()],
    narrator: Annotated[Optional[str], Form()] = None,
    subtitle: Annotated[Optional[str], Form()] = None,
    publish_date: Annotated[Optional[str], Form()] = None,
    info: Annotated[Optional[str], Form()] = None,
):
    book_request = ManualBookRequest(
        user_username=user.username,
        title=title,
        authors=author.split(","),
        narrators=narrator.split(",") if narrator else [],
        subtitle=subtitle,
        publish_date=publish_date,
        additional_info=info,
    )
    session.add(book_request)
    session.flush()
    session.expunge_all()  # so that we can pass down the object without the session
    session.commit()

    notifications = session.exec(
        select(Notification).where(Notification.event == EventEnum.on_new_request)
    ).all()
    for notif in notifications:
        background_task.add_task(
            send_manual_notification,
            notification=notif,
            book=book_request,
            requester_username=user.username,
        )

    return template_response(
        "manual.html",
        request,
        user,
        {"success": "Successfully added request"},
        block_name="form",
    )
