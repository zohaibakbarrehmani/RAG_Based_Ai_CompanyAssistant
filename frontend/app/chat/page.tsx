"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  askQuestion,
  ApiError,
  ChatMessage,
  ChatSession,
  Citation,
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  updateChatSession,
} from "@/lib/api";

const NOT_FOUND_ANSWER = "I couldn't find this in the company documents.";

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(new Date(value));
  } catch {
    return "";
  }
}

export default function ChatPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [searchFilter, setSearchFilter] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [menuSessionId, setMenuSessionId] = useState<number | null>(null);
  const [updatingSessionId, setUpdatingSessionId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadSessions = useCallback(async (authToken: string) => {
    return listChatSessions(authToken);
  }, []);

  const openSession = useCallback(async (authToken: string, sessionId: number) => {
    const session = await getChatSession(authToken, sessionId);
    setActiveSessionId(session.id);
    setMessages(session.messages);
    setSelectedCitation(null);
  }, []);

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    const role = localStorage.getItem("user_role");
    const email = localStorage.getItem("user_email");
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    setUserRole(role);
    setUserEmail(email);

    void loadSessions(storedToken)
      .then((savedSessions) => {
        setSessions(savedSessions);
        if (savedSessions.length > 0) {
          return openSession(storedToken, savedSessions[0].id);
        }
      })
      .catch((loadError: unknown) => {
        if (loadError instanceof ApiError && loadError.status === 401) {
          localStorage.removeItem("token");
          localStorage.removeItem("user_role");
          router.replace("/login");
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load chats.");
      })
      .finally(() => setLoading(false));
  }, [loadSessions, openSession, router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function startNewChat() {
    if (!token) return;
    setError(null);
    try {
      const session = await createChatSession(token);
      setSessions((current) => [session, ...current]);
      setActiveSessionId(session.id);
      setMessages([]);
      setSelectedCitation(null);
      textareaRef.current?.focus();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to start a new chat.");
    }
  }

  async function selectSession(sessionId: number) {
    if (!token || sessionId === activeSessionId) return;
    setError(null);
    setMenuSessionId(null);
    setLoading(true);
    try {
      await openSession(token, sessionId);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to open this chat.");
    } finally {
      setLoading(false);
    }
  }

  async function togglePinned(session: ChatSession) {
    if (!token || updatingSessionId !== null) return;
    setUpdatingSessionId(session.id);
    setError(null);
    try {
      const updated = await updateChatSession(token, session.id, !session.pinned);
      setSessions((current) =>
        current
          .map((item) => (item.id === updated.id ? updated : item))
          .sort((left, right) => Number(right.pinned) - Number(left.pinned)),
      );
      setMenuSessionId(null);
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Unable to update this chat.");
    } finally {
      setUpdatingSessionId(null);
    }
  }

  async function removeSession(session: ChatSession) {
    if (!token || updatingSessionId !== null) return;
    if (!window.confirm(`Delete "${session.title}"? This conversation will be permanently removed.`)) return;

    setUpdatingSessionId(session.id);
    setError(null);
    try {
      await deleteChatSession(token, session.id);
      setSessions((current) => current.filter((item) => item.id !== session.id));
      setMenuSessionId(null);
      if (activeSessionId === session.id) {
        setActiveSessionId(null);
        setMessages([]);
        setSelectedCitation(null);
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete this chat.");
    } finally {
      setUpdatingSessionId(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!token || !submittedQuestion || sending) return;

    setError(null);
    setSending(true);
    setQuestion("");

    const optimisticMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: submittedQuestion,
      citations: [],
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimisticMessage]);

    try {
      let sessionId = activeSessionId;
      if (sessionId === null) {
        const session = await createChatSession(token);
        sessionId = session.id;
        setActiveSessionId(sessionId);
        setSessions((current) => [session, ...current]);
      }

      const answer = await askQuestion(token, submittedQuestion, sessionId);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: answer.answer,
          citations: answer.citations,
          created_at: new Date().toISOString(),
        },
      ]);
      const savedSessions = await loadSessions(token);
      setSessions(savedSessions);
    } catch (sendError) {
      setMessages((current) => current.filter((message) => message.id !== optimisticMessage.id));
      setQuestion(submittedQuestion);
      setError(sendError instanceof Error ? sendError.message : "Your question could not be processed.");
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function handleCopyAnswer(content: string, msgId: number) {
    void navigator.clipboard.writeText(content);
    setCopiedMessageId(msgId);
    setTimeout(() => setCopiedMessageId(null), 2000);
  }

  function handleSignOut() {
    localStorage.removeItem("token");
    localStorage.removeItem("user_role");
    localStorage.removeItem("user_email");
    router.replace("/login");
  }

  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(searchFilter.toLowerCase()),
  );

  const hasConversation = messages.length > 0;

  return (
    <main className="flex h-screen overflow-hidden bg-[#0a0e17] text-slate-100 selection:bg-indigo-500">
      {/* Sidebar */}
      <aside
        className={`${
          isSidebarOpen ? "w-72" : "w-0 -translate-x-full"
        } relative flex shrink-0 flex-col border-r border-white/10 bg-[#0f1422] transition-all duration-300 md:translate-x-0`}
      >
        {/* Workspace Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-white/10 px-4">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-md shadow-indigo-500/20">
              <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden="true">
                <path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.64 5.64l1.42 1.42m9.88 9.88 1.42 1.42m0-12.72-1.42 1.42m-9.88 9.88-1.42 1.42" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.8" />
              </svg>
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-bold text-white">Company Policy AI</p>
              <p className="text-[10px] text-slate-400">Knowledge Assistant</p>
            </div>
          </div>
          {userRole === "admin" ? (
            <button
              type="button"
              onClick={() => router.push("/admin")}
              className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-2 py-1 text-[10px] font-semibold text-indigo-300 hover:bg-indigo-500/20"
              title="Go to Admin Dashboard"
            >
              Admin
            </button>
          ) : null}
        </div>

        {/* New Chat Button */}
        <div className="p-3">
          <button
            type="button"
            onClick={startNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:from-indigo-500 hover:to-violet-500 active:scale-[0.99]"
          >
            <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>New Chat</span>
          </button>

          {/* Search history */}
          <div className="relative mt-3">
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Search conversations..."
              className="w-full rounded-xl border border-white/5 bg-slate-950/60 px-3 py-1.5 pl-8 text-[11px] text-slate-300 placeholder:text-slate-500 outline-none focus:border-indigo-500"
            />
            <svg viewBox="0 0 24 24" fill="none" className="absolute left-2.5 top-2 size-3.5 text-slate-500" aria-hidden="true">
              <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
              <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
        </div>

        {/* Chat Sessions List */}
        <div className="flex-1 overflow-y-auto px-2 space-y-1">
          <div className="flex items-center justify-between px-2 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            <span>Conversations</span>
            <span className="rounded-full bg-slate-800 px-1.5 py-0.5 text-[9px] text-slate-300">{filteredSessions.length}</span>
          </div>

          <nav aria-label="Recent chats" className="mt-2 space-y-1">
            {filteredSessions.map((session) => {
              const isActive = activeSessionId === session.id;
              return (
                <div key={session.id} className="group relative flex items-stretch">
                  <button
                    type="button"
                    onClick={() => void selectSession(session.id)}
                    className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs transition ${
                      isActive
                        ? "bg-indigo-600/20 text-indigo-300 font-semibold border border-indigo-500/30"
                        : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                    }`}
                  >
                    <svg viewBox="0 0 24 24" fill="none" className={`size-3.5 shrink-0 ${isActive ? "text-indigo-400" : "text-slate-500"}`} aria-hidden="true">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                    </svg>
                    <div className="min-w-0 flex-1 truncate">
                      <div className="flex items-center gap-1.5 truncate">
                        {session.pinned ? (
                          <svg viewBox="0 0 24 24" fill="none" className="size-3 shrink-0 text-amber-400" aria-label="Pinned">
                            <path d="M12 17v5M9 2h6M8 6h8M7 10h10M6 14h12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                          </svg>
                        ) : null}
                        <span className="truncate">{session.title}</span>
                      </div>
                      <span className="block text-[9px] text-slate-500">{formatDate(session.created_at)}</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setMenuSessionId((curr) => curr === session.id ? null : session.id)}
                    className="mr-1 self-center rounded-lg p-1.5 text-slate-500 opacity-0 transition hover:bg-slate-800 hover:text-slate-300 group-hover:opacity-100"
                    aria-label="Conversation options"
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor" className="size-3.5" aria-hidden="true">
                      <circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" />
                    </svg>
                  </button>

                  {menuSessionId === session.id ? (
                    <div className="absolute right-2 top-8 z-30 w-36 rounded-xl border border-white/10 bg-slate-900 p-1 shadow-xl">
                      <button
                        type="button"
                        onClick={() => void togglePinned(session)}
                        className="w-full rounded-lg px-2.5 py-1.5 text-left text-[11px] text-slate-300 hover:bg-white/5"
                      >
                        {session.pinned ? "Unpin chat" : "Pin chat"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void removeSession(session)}
                        className="w-full rounded-lg px-2.5 py-1.5 text-left text-[11px] text-red-400 hover:bg-red-500/10"
                      >
                        Delete chat
                      </button>
                    </div>
                  ) : null}
                </div>
              );
            })}
            {!loading && filteredSessions.length === 0 ? (
              <p className="px-3 py-6 text-center text-[11px] text-slate-500">No conversations found.</p>
            ) : null}
          </nav>
        </div>

        {/* User Footer */}
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center justify-between rounded-xl bg-slate-950/40 p-2 border border-white/5">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-indigo-600/30 text-[10px] font-bold text-indigo-300 ring-1 ring-indigo-500/30">
                {userRole === "admin" ? "AD" : "EM"}
              </div>
              <div className="min-w-0 truncate">
                <p className="truncate text-xs font-semibold text-slate-200">{userEmail ?? "User"}</p>
                <p className="text-[10px] text-slate-400 capitalize">{userRole ?? "Employee"}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleSignOut}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-red-500/10 hover:text-red-400"
              title="Sign out"
            >
              <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                <path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <section className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-[#0a0e17]">
        {/* Chat Header */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 bg-[#0f1422]/80 px-6 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsSidebarOpen((v) => !v)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-white/5 hover:text-white md:hidden"
              aria-label="Toggle sidebar"
            >
              <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden="true">
                <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
            <div>
              <p className="text-sm font-bold text-white">Company Knowledge Assistant</p>
              <p className="text-[11px] text-slate-400">Verifiable answers directly grounded in internal documents</p>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-semibold text-emerald-300">
            <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Knowledge Base Active
          </div>
        </header>

        {/* Chat Body & Source Sidebar */}
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex-1 overflow-y-auto px-4 py-8 sm:px-8">
              <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col">
                {!hasConversation && !loading ? (
                  /* Hero / Suggestion Prompts */
                  <div className="flex flex-1 flex-col items-center justify-center text-center">
                    <div className="mb-5 flex size-16 items-center justify-center rounded-3xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-xl shadow-indigo-500/25 ring-1 ring-white/20">
                      <svg viewBox="0 0 24 24" fill="none" className="size-8" aria-hidden="true">
                        <path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.64 5.64l1.42 1.42m9.88 9.88 1.42 1.42m0-12.72-1.42 1.42m-9.88 9.88-1.42 1.42" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                        <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.8" />
                      </svg>
                    </div>
                    <span className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-indigo-300">
                      Internal Policy & Guide AI
                    </span>
                    <h2 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">
                      How can I help you today?
                    </h2>
                    <p className="mt-2 max-w-md text-xs leading-5 text-slate-400">
                      Ask any question about company policies, leave protocols, deployment SOPs, or benefits.
                    </p>

                    {/* Quick suggestion cards */}
                    <div className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-2">
                      {[
                        { title: "Annual Leave & Vacations", query: "What is the policy regarding leave, vacations, and annual holidays?" },
                        { title: "Deployment & CI/CD", query: "What is the standard procedure for deploying engineering services?" },
                        { title: "Expense & Travel Policies", query: "Where can I find the expense claim and travel policy details?" },
                        { title: "Employee Benefits & Health", query: "What health insurance and employee benefits does the company provide?" },
                      ].map((item, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setQuestion(item.query)}
                          className="group flex flex-col items-start rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-left transition hover:border-indigo-500/50 hover:bg-slate-800/80 active:scale-[0.99]"
                        >
                          <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 group-hover:text-indigo-300">
                            <span>{item.title}</span>
                            <span className="text-xs transition-transform group-hover:translate-x-0.5">↗</span>
                          </div>
                          <p className="mt-1 text-xs text-slate-400 line-clamp-2">{item.query}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  /* Conversation Messages */
                  <div className="flex-1 space-y-6">
                    {messages.map((message) => {
                      const isUser = message.role === "user";
                      return (
                        <article
                          key={message.id}
                          className={`flex gap-3.5 ${isUser ? "justify-end" : "justify-start"}`}
                        >
                          {!isUser ? (
                            <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-md shadow-indigo-500/20">
                              <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                                <path d="M12 3v2m0 14v2M3 12h2m14 0h2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
                              </svg>
                            </div>
                          ) : null}

                          <div className={`max-w-[85%] ${isUser ? "order-first" : ""}`}>
                            <div
                              className={`rounded-3xl p-4 sm:p-5 text-xs sm:text-sm leading-relaxed ${
                                isUser
                                  ? "rounded-br-md bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-600/20"
                                  : message.content === NOT_FOUND_ANSWER
                                    ? "rounded-bl-md border border-amber-500/30 bg-amber-500/10 text-amber-200"
                                    : "rounded-bl-md border border-white/10 bg-slate-900/90 text-slate-200 shadow-xl backdrop-blur"
                              }`}
                            >
                              <div className="whitespace-pre-wrap">{message.content}</div>

                              {/* Assistant toolbar (Copy answer) */}
                              {!isUser ? (
                                <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5">
                                  <span className="text-[10px] text-slate-500">Grounded AI Response</span>
                                  <button
                                    type="button"
                                    onClick={() => handleCopyAnswer(message.content, message.id)}
                                    className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-950/40 px-2 py-1 text-[10px] text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
                                  >
                                    {copiedMessageId === message.id ? (
                                      <>
                                        <svg viewBox="0 0 24 24" fill="none" className="size-3 text-emerald-400" aria-hidden="true">
                                          <path d="m5 13 4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                        </svg>
                                        <span className="text-emerald-400">Copied!</span>
                                      </>
                                    ) : (
                                      <>
                                        <svg viewBox="0 0 24 24" fill="none" className="size-3" aria-hidden="true">
                                          <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" strokeWidth="2" />
                                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="2" />
                                        </svg>
                                        <span>Copy Answer</span>
                                      </>
                                    )}
                                  </button>
                                </div>
                              ) : null}
                            </div>

                            {/* Source citations */}
                            {!isUser && message.citations.length > 0 ? (
                              <div className="mt-3 space-y-2">
                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                  Cited Document Sources ({message.citations.length})
                                </p>
                                <div className="flex flex-wrap gap-2">
                                  {message.citations.map((cit, cIdx) => (
                                    <button
                                      key={`${cit.filename}-${cit.page}-${cIdx}`}
                                      type="button"
                                      onClick={() => setSelectedCitation(cit)}
                                      className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-[11px] font-semibold text-indigo-300 transition hover:border-indigo-400 hover:bg-indigo-500/20"
                                    >
                                      <svg viewBox="0 0 24 24" fill="none" className="size-3 text-indigo-400" aria-hidden="true">
                                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                                        <path d="M14 2v6h6M16 13H8M16 17H8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                                      </svg>
                                      <span className="truncate max-w-[140px]">{cit.filename}</span>
                                      <span className="text-slate-500">·</span>
                                      <span>p.{cit.page}</span>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </div>

                          {isUser ? (
                            <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-[10px] font-bold text-slate-300 ring-1 ring-white/10">
                              ME
                            </div>
                          ) : null}
                        </article>
                      );
                    })}

                    {/* Thinking status */}
                    {sending ? (
                      <div className="flex items-center gap-3">
                        <div className="flex size-8 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/20">
                          <span className="size-2 rounded-full bg-white animate-ping" />
                        </div>
                        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-900 px-4 py-3">
                          <span className="size-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.3s]" />
                          <span className="size-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.15s]" />
                          <span className="size-1.5 animate-bounce rounded-full bg-indigo-400" />
                          <span className="ml-2 text-xs text-slate-400">Consulting company documents...</span>
                        </div>
                      </div>
                    ) : null}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>
            </div>

            {/* Input Composer */}
            <div className="shrink-0 p-4 sm:p-6 bg-gradient-to-t from-[#0a0e17] via-[#0a0e17] to-transparent">
              <div className="mx-auto max-w-3xl">
                {error ? (
                  <div role="alert" className="mb-3 flex items-center justify-between rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-300">
                    <span>{error}</span>
                    <button type="button" onClick={() => setError(null)} className="text-red-400 hover:text-white">✕</button>
                  </div>
                ) : null}

                <form
                  onSubmit={handleSubmit}
                  className="relative rounded-3xl border border-white/15 bg-slate-900/90 p-2 shadow-2xl backdrop-blur-xl focus-within:border-indigo-500/80 focus-within:ring-2 focus-within:ring-indigo-500/20"
                >
                  <label htmlFor="chat-composer" className="sr-only">Ask a policy question</label>
                  <textarea
                    id="chat-composer"
                    ref={textareaRef}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={handleComposerKeyDown}
                    placeholder="Ask anything about company policies, SOPs, or guides..."
                    rows={2}
                    className="max-h-40 min-h-12 w-full resize-none bg-transparent px-4 py-2.5 text-xs sm:text-sm text-white placeholder:text-slate-500 outline-none"
                    disabled={sending || loading}
                  />
                  <div className="flex items-center justify-between px-3 pb-1 pt-1">
                    <p className="text-[10px] text-slate-500">Press <kbd className="rounded border border-white/10 bg-slate-800 px-1 py-0.5 font-mono text-[9px] text-slate-400">Enter</kbd> to ask</p>
                    <button
                      type="submit"
                      disabled={sending || loading || !question.trim()}
                      className="flex size-9 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-600/30 transition hover:from-indigo-500 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95"
                      aria-label="Send query"
                    >
                      <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                        <path d="m5 12 14-7-4.5 14-2.6-5.4L5 12Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="m12 13.6 3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>

          {/* Citation Source Inspector Drawer */}
          {selectedCitation ? (
            <aside className="w-80 shrink-0 border-l border-white/10 bg-[#0f1422] flex flex-col p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
                    <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                  </div>
                  <h3 className="text-xs font-bold text-white">Source Passage</h3>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedCitation(null)}
                  className="text-slate-400 hover:text-white"
                  aria-label="Close panel"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-1 text-xs">
                <p className="font-semibold text-white">{selectedCitation.filename}</p>
                <p className="text-[11px] text-indigo-400">
                  Page {selectedCitation.page} · {selectedCitation.section}
                </p>
              </div>

              <div className="flex-1 overflow-y-auto rounded-2xl border border-white/5 bg-slate-950/60 p-4 font-mono text-xs leading-relaxed text-slate-300 whitespace-pre-wrap">
                {selectedCitation.snippet}
              </div>

              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(selectedCitation.snippet);
                  alert("Excerpt snippet copied to clipboard!");
                }}
                className="w-full rounded-xl border border-white/10 bg-slate-900 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
              >
                Copy Passage
              </button>
            </aside>
          ) : null}
        </div>
      </section>
    </main>
  );
}
