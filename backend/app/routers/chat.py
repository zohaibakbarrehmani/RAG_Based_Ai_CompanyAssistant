from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ChatMessage, ChatSession, PinnedChatSession, User
from app.schemas import (
    ChatAskRequest,
    ChatAskResponse,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionRead,
    ChatSessionUpdate,
)
from app.services.rag import answer_question, recent_session_history

router = APIRouter(prefix="/chat", tags=["chat"])


def _session_read(session: ChatSession, pinned: bool = False) -> ChatSessionRead:
    return ChatSessionRead(
        id=session.id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        pinned=pinned,
    )


def _owned_session(db: Session, session_id: int, user_id: int) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )
    return session


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionRead:
    title = (payload.title or "").strip() or "New chat"
    session = ChatSession(user_id=current_user.id, title=title[:120])
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_read(session)


@router.get("/sessions", response_model=list[ChatSessionRead])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionRead]:
    pinned_ids = {
        item.session_id
        for item in db.query(PinnedChatSession)
        .filter(PinnedChatSession.user_id == current_user.id)
        .all()
    }
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .all()
    )
    sessions.sort(
        key=lambda session: (
            session.id not in pinned_ids,
            -session.created_at.timestamp(),
            -session.id,
        )
    )
    return [_session_read(session, session.id in pinned_ids) for session in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    session = _owned_session(db, session_id, current_user.id)
    pinned = (
        db.query(PinnedChatSession)
        .filter(
            PinnedChatSession.user_id == current_user.id,
            PinnedChatSession.session_id == session.id,
        )
        .first()
        is not None
    )
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
        .all()
    )
    return ChatSessionDetail(
        **_session_read(session, pinned).model_dump(),
        messages=[
            ChatMessageRead(
                id=message.id,
                role=message.role,
                content=message.content,
                citations=json.loads(message.citations_json or "[]"),
                created_at=message.created_at.isoformat(),
            )
            for message in messages
        ],
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionRead)
def update_session(
    session_id: int,
    payload: ChatSessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionRead:
    session = _owned_session(db, session_id, current_user.id)
    pin = (
        db.query(PinnedChatSession)
        .filter(
            PinnedChatSession.user_id == current_user.id,
            PinnedChatSession.session_id == session.id,
        )
        .first()
    )
    if payload.pinned and pin is None:
        db.add(PinnedChatSession(user_id=current_user.id, session_id=session.id))
    elif not payload.pinned and pin is not None:
        db.delete(pin)
    db.commit()
    return _session_read(session, payload.pinned)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    session = _owned_session(db, session_id, current_user.id)
    db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
    db.query(PinnedChatSession).filter(
        PinnedChatSession.user_id == current_user.id,
        PinnedChatSession.session_id == session.id,
    ).delete()
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ask", response_model=ChatAskResponse)
def ask(
    payload: ChatAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatAskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question must not be empty.",
        )

    if payload.session_id is None:
        session = ChatSession(user_id=current_user.id, title=question[:120])
        db.add(session)
        db.commit()
        db.refresh(session)
        history: list[dict[str, str]] = []
    else:
        session = _owned_session(db, payload.session_id, current_user.id)
        history = recent_session_history(db, session.id)

    result = answer_question(db, question, history)
    citations = result["citations"]
    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=question,
            citations_json="[]",
        )
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=result["answer"],
            citations_json=json.dumps(citations, ensure_ascii=False),
        )
    )
    if session.title == "New chat":
        session.title = question[:120]
    db.commit()

    return ChatAskResponse(
        session_id=session.id,
        answer=result["answer"],
        citations=citations,
        cached=result["cached"],
    )
