export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Citation {
  filename: string;
  page: number;
  section: string;
  snippet: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface ChatSession {
  id: number;
  title: string;
  created_at: string;
  pinned: boolean;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface ChatAnswer {
  session_id: number;
  answer: string;
  citations: Citation[];
  cached: boolean;
}

export interface CompanyDocument {
  id: number;
  filename: string;
  bucket: string;
  file_hash: string;
  status: "uploaded" | "indexing" | "indexed" | "failed";
  error_message?: string | null;
  page_count: number;
  version: number;
  uploaded_by?: number | null;
}

export interface RetrievedChunk {
  document_id: number;
  filename: string;
  bucket: string;
  page: number;
  section: string;
  chunk_ids: number[];
  text: string;
  score: number;
  token_estimate: number;
}

export interface DebugRetrieveResponse {
  buckets: string[];
  route_source: string;
  results: RetrievedChunk[];
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // Keep the HTTP status message when the response has no JSON body.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function listChatSessions(token: string): Promise<ChatSession[]> {
  return request<ChatSession[]>("/chat/sessions", token);
}

export function getChatSession(
  token: string,
  sessionId: number,
): Promise<ChatSessionDetail> {
  return request<ChatSessionDetail>(`/chat/sessions/${sessionId}`, token);
}

export function createChatSession(token: string): Promise<ChatSession> {
  return request<ChatSession>("/chat/sessions", token, {
    method: "POST",
    body: JSON.stringify({ title: "New chat" }),
  });
}

export function updateChatSession(
  token: string,
  sessionId: number,
  pinned: boolean,
): Promise<ChatSession> {
  return request<ChatSession>(`/chat/sessions/${sessionId}`, token, {
    method: "PATCH",
    body: JSON.stringify({ pinned }),
  });
}

export function deleteChatSession(token: string, sessionId: number): Promise<void> {
  return request<void>(`/chat/sessions/${sessionId}`, token, {
    method: "DELETE",
  });
}

export function askQuestion(
  token: string,
  question: string,
  sessionId: number,
): Promise<ChatAnswer> {
  return request<ChatAnswer>("/chat/ask", token, {
    method: "POST",
    body: JSON.stringify({ question, session_id: sessionId }),
  });
}

// Admin Document APIs
export function listDocuments(token: string): Promise<CompanyDocument[]> {
  return request<CompanyDocument[]>("/admin/documents", token);
}

export function reindexDocument(token: string, documentId: number): Promise<CompanyDocument> {
  return request<CompanyDocument>(`/admin/documents/${documentId}/reindex`, token, {
    method: "POST",
  });
}

export function deleteDocument(token: string, documentId: number): Promise<void> {
  return request<void>(`/admin/documents/${documentId}`, token, {
    method: "DELETE",
  });
}

export function debugRetrieve(token: string, question: string): Promise<DebugRetrieveResponse> {
  return request<DebugRetrieveResponse>("/admin/debug/retrieve", token, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
