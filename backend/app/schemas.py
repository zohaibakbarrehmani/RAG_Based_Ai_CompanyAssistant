from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "employee"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    bucket: str
    file_hash: str
    status: str
    error_message: str | None = None
    page_count: int
    version: int
    uploaded_by: int | None = None


class DebugRetrieveRequest(BaseModel):
    question: str


class RetrievedChunkRead(BaseModel):
    document_id: int
    filename: str
    bucket: str
    page: int
    section: str
    chunk_ids: list[int]
    text: str
    score: float
    token_estimate: int


class DebugRetrieveResponse(BaseModel):
    buckets: list[str]
    route_source: str
    results: list[RetrievedChunkRead]


class ChatSessionCreate(BaseModel):
    title: str | None = None


class ChatSessionRead(BaseModel):
    id: int
    title: str
    created_at: str
    pinned: bool = False


class ChatSessionUpdate(BaseModel):
    pinned: bool


class ChatMessageRead(BaseModel):
    id: int
    role: str
    content: str
    citations: list[dict[str, str | int]]
    created_at: str


class ChatSessionDetail(ChatSessionRead):
    messages: list[ChatMessageRead]


class ChatAskRequest(BaseModel):
    question: str
    session_id: int | None = None


class CitationRead(BaseModel):
    filename: str
    page: int
    section: str
    snippet: str


class ChatAskResponse(BaseModel):
    session_id: int
    answer: str
    citations: list[CitationRead]
    cached: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
