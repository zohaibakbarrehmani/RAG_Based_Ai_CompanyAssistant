"use client";

import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CompanyDocument,
  DebugRetrieveResponse,
  deleteDocument,
  listDocuments,
  reindexDocument,
  debugRetrieve,
  ApiError,
} from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BUCKETS = ["general", "hr", "engineering", "product", "sop", "faq"] as const;

const BUCKET_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  hr: { bg: "bg-pink-500/10", text: "text-pink-400", border: "border-pink-500/30" },
  engineering: { bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/30" },
  product: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/30" },
  sop: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/30" },
  faq: { bg: "bg-purple-500/10", text: "text-purple-400", border: "border-purple-500/30" },
  general: { bg: "bg-indigo-500/10", text: "text-indigo-400", border: "border-indigo-500/30" },
};

export default function AdminPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [documents, setDocuments] = useState<CompanyDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [bucket, setBucket] = useState<(typeof BUCKETS)[number]>("general");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [actionInProgressId, setActionInProgressId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFilterBucket, setSelectedFilterBucket] = useState<string>("all");
  const [selectedFilterStatus, setSelectedFilterStatus] = useState<string>("all");
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedDocError, setSelectedDocError] = useState<CompanyDocument | null>(null);

  // Live Debugger state
  const [debugQuestion, setDebugQuestion] = useState("");
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugResult, setDebugResult] = useState<DebugRetrieveResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"documents" | "debugger">("documents");

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    const role = localStorage.getItem("user_role");
    if (!storedToken || role !== "admin") {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
  }, [router]);

  const fetchDocs = useCallback(async (authToken: string) => {
    try {
      const data = await listDocuments(authToken);
      setDocuments(data);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        localStorage.removeItem("token");
        localStorage.removeItem("user_role");
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (token) {
      void fetchDocs(token);
      // Auto-poll document list if any document is currently in 'indexing' or 'uploaded' status
      const interval = setInterval(() => {
        setDocuments((current) => {
          const hasPending = current.some((d) => d.status === "indexing" || d.status === "uploaded");
          if (hasPending && token) {
            void listDocuments(token).then(setDocuments).catch(() => {});
          }
          return current;
        });
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [token, fetchDocs]);

  async function handleUpload(event?: FormEvent<HTMLFormElement>) {
    if (event) event.preventDefault();
    if (!token || !file || uploading) return;

    setError(null);
    setNotice(null);
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("bucket", bucket);

    try {
      const response = await fetch(`${API_BASE_URL}/admin/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        let msg = `Upload failed (${response.status})`;
        try {
          const resJson = await response.json();
          if (resJson.detail) msg = resJson.detail;
        } catch {}
        throw new Error(msg);
      }

      const uploaded = (await response.json()) as CompanyDocument;
      setFile(null);
      setBucket("general");
      await fetchDocs(token);
      setNotice(`"${uploaded.filename}" uploaded successfully. Indexing started in background.`);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Unable to upload document.");
    } finally {
      setUploading(false);
    }
  }

  async function handleReindex(doc: CompanyDocument) {
    if (!token || actionInProgressId !== null) return;
    setActionInProgressId(doc.id);
    setError(null);
    setNotice(null);

    try {
      await reindexDocument(token, doc.id);
      setNotice(`Re-indexing started for "${doc.filename}".`);
      await fetchDocs(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reindex document.");
    } finally {
      setActionInProgressId(null);
    }
  }

  async function handleDelete(doc: CompanyDocument) {
    if (!token || actionInProgressId !== null) return;
    if (!window.confirm(`Are you sure you want to permanently delete "${doc.filename}" and its indexed knowledge?`)) {
      return;
    }

    setActionInProgressId(doc.id);
    setError(null);
    setNotice(null);

    try {
      await deleteDocument(token, doc.id);
      setNotice(`"${doc.filename}" removed from knowledge base.`);
      setDocuments((current) => current.filter((d) => d.id !== doc.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document.");
    } finally {
      setActionInProgressId(null);
    }
  }

  async function handleDebugSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !debugQuestion.trim() || debugLoading) return;
    setDebugLoading(true);
    setDebugResult(null);
    setError(null);

    try {
      const res = await debugRetrieve(token, debugQuestion.trim());
      setDebugResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Debug retrieval failed.");
    } finally {
      setDebugLoading(false);
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFile = e.dataTransfer.files[0];
      const ext = droppedFile.name.split(".").pop()?.toLowerCase();
      if (["pdf", "docx", "txt", "md"].includes(ext ?? "")) {
        setFile(droppedFile);
      } else {
        setError("Only PDF, DOCX, TXT, and MD files are supported.");
      }
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  function handleSignOut() {
    localStorage.removeItem("token");
    localStorage.removeItem("user_role");
    router.replace("/login");
  }

  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const matchSearch = doc.filename.toLowerCase().includes(searchQuery.toLowerCase());
      const matchBucket = selectedFilterBucket === "all" || doc.bucket === selectedFilterBucket;
      const matchStatus = selectedFilterStatus === "all" || doc.status === selectedFilterStatus;
      return matchSearch && matchBucket && matchStatus;
    });
  }, [documents, searchQuery, selectedFilterBucket, selectedFilterStatus]);

  const stats = useMemo(() => {
    const total = documents.length;
    const indexed = documents.filter((d) => d.status === "indexed").length;
    const failed = documents.filter((d) => d.status === "failed").length;
    const indexing = documents.filter((d) => d.status === "indexing" || d.status === "uploaded").length;
    const totalPages = documents.reduce((acc, d) => acc + (d.page_count || 0), 0);
    return { total, indexed, failed, indexing, totalPages };
  }, [documents]);

  return (
    <main className="min-h-screen bg-[#0a0e17] text-slate-100 selection:bg-indigo-500">
      {/* Top Header */}
      <header className="sticky top-0 z-30 border-b border-white/10 bg-[#0f1422]/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 text-white shadow-lg shadow-indigo-500/20">
              <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden="true">
                <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                <path d="M6 6h10M6 10h10M6 14h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-white">Company Knowledge Admin</h1>
                <span className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-indigo-300 uppercase tracking-wider">
                  Admin Portal
                </span>
              </div>
              <p className="text-xs text-slate-400">Manage internal policies, indexing pipelines, and RAG retrieval</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => router.push("/chat")}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/60 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-indigo-500/50 hover:bg-slate-800"
            >
              <svg viewBox="0 0 24 24" fill="none" className="size-4 text-indigo-400" aria-hidden="true">
                <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 0 1-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>Employee Chat</span>
            </button>
            <button
              type="button"
              onClick={handleSignOut}
              className="rounded-xl border border-white/10 px-3.5 py-2 text-xs font-semibold text-slate-400 transition hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/30"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        {/* Alerts */}
        {error ? (
          <div role="alert" className="flex items-start justify-between gap-3 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            <div className="flex items-start gap-3">
              <svg viewBox="0 0 24 24" fill="none" className="size-5 shrink-0 text-red-400 mt-0.5" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
                <path d="M12 8v4m0 4h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span>{error}</span>
            </div>
            <button type="button" onClick={() => setError(null)} className="text-red-400 hover:text-white">✕</button>
          </div>
        ) : null}

        {notice ? (
          <div role="status" className="flex items-start justify-between gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-300">
            <div className="flex items-start gap-3">
              <svg viewBox="0 0 24 24" fill="none" className="size-5 shrink-0 text-emerald-400 mt-0.5" aria-hidden="true">
                <path d="m5 13 4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>{notice}</span>
            </div>
            <button type="button" onClick={() => setNotice(null)} className="text-emerald-400 hover:text-white">✕</button>
          </div>
        ) : null}

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur">
            <p className="text-xs font-semibold text-slate-400">Total Documents</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">{stats.total}</span>
              <span className="text-xs text-slate-500">{stats.totalPages} pages</span>
            </div>
          </div>
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5 backdrop-blur">
            <p className="text-xs font-semibold text-emerald-400">Indexed & Active</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-emerald-300">{stats.indexed}</span>
              <span className="text-xs text-emerald-500/80">Ready for Q&A</span>
            </div>
          </div>
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 backdrop-blur">
            <p className="text-xs font-semibold text-amber-400">Processing</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-amber-300">{stats.indexing}</span>
              <span className="text-xs text-amber-500/80">Indexing</span>
            </div>
          </div>
          <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-5 backdrop-blur">
            <p className="text-xs font-semibold text-red-400">Failed</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-red-300">{stats.failed}</span>
              <span className="text-xs text-red-500/80">Needs retry</span>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-white/10">
          <button
            type="button"
            onClick={() => setActiveTab("documents")}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${
              activeTab === "documents"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>Document Management</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("debugger")}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 text-sm font-semibold transition ${
              activeTab === "debugger"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
              <path d="m15 15-2-2m0 0-2-2m2 2 2-2m-2 2-2 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>RAG Retrieval Debugger</span>
          </button>
        </div>

        {activeTab === "documents" ? (
          <>
            {/* Upload Zone */}
            <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-7 shadow-xl backdrop-blur">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-white">Upload New Company Document</h2>
                  <p className="text-xs text-slate-400">
                    Upload policy handbooks, SOPs, engineering docs, or product guides. PDF, Word (.docx), TXT, and Markdown supported.
                  </p>
                </div>
              </div>

              <form onSubmit={handleUpload} className="space-y-4">
                <div
                  onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={handleDrop}
                  className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition ${
                    isDragOver
                      ? "border-indigo-500 bg-indigo-500/10"
                      : "border-white/10 bg-slate-950/40 hover:border-white/20"
                  }`}
                >
                  <input
                    type="file"
                    accept=".pdf,.docx,.txt,.md"
                    onChange={handleFileChange}
                    className="absolute inset-0 cursor-pointer opacity-0"
                    id="admin-file-upload"
                  />
                  <div className="flex size-14 items-center justify-center rounded-2xl bg-indigo-600/20 text-indigo-400 ring-1 ring-indigo-500/30">
                    <svg viewBox="0 0 24 24" fill="none" className="size-7" aria-hidden="true">
                      <path d="M12 16.5v-9m0 0 3.5 3.5M12 7.5 8.5 11M20 16.5a4.5 4.5 0 0 0-1.5-8.74 5.5 5.5 0 0 0-10.84 1.48A4.5 4.5 0 0 0 4 16.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                  <p className="mt-3 text-sm font-semibold text-white">
                    {file ? file.name : "Choose a file or drag & drop here"}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready to upload` : "PDF, DOCX, TXT, or MD up to 20 MB"}
                  </p>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold text-slate-400">Target Category:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {BUCKETS.map((b) => (
                        <button
                          key={b}
                          type="button"
                          onClick={() => setBucket(b)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                            bucket === b
                              ? "bg-indigo-600 text-white shadow-sm"
                              : "border border-white/10 bg-slate-950/60 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          {b === "hr" ? "HR" : b.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={!file || uploading}
                    className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-600/25 transition hover:from-indigo-500 hover:to-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {uploading ? (
                      <>
                        <span className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                        <span>Uploading & Indexing...</span>
                      </>
                    ) : (
                      <>
                        <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                          <path d="M12 4v16m-8-8h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                        <span>Upload Document</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </section>

            {/* Document List Table */}
            <section className="overflow-hidden rounded-3xl border border-white/10 bg-slate-900/80 shadow-xl backdrop-blur">
              {/* Filter & Search Bar */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 p-5 sm:px-6">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative min-w-[240px]">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search documents..."
                      className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3.5 py-2 pl-9 text-xs text-white placeholder:text-slate-500 outline-none focus:border-indigo-500"
                    />
                    <svg viewBox="0 0 24 24" fill="none" className="absolute left-3 top-2.5 size-4 text-slate-500" aria-hidden="true">
                      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
                      <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </div>

                  <select
                    value={selectedFilterBucket}
                    onChange={(e) => setSelectedFilterBucket(e.target.value)}
                    className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 outline-none focus:border-indigo-500"
                  >
                    <option value="all">All Categories</option>
                    {BUCKETS.map((b) => (
                      <option key={b} value={b}>{b === "hr" ? "HR" : b.toUpperCase()}</option>
                    ))}
                  </select>

                  <select
                    value={selectedFilterStatus}
                    onChange={(e) => setSelectedFilterStatus(e.target.value)}
                    className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 outline-none focus:border-indigo-500"
                  >
                    <option value="all">All Statuses</option>
                    <option value="indexed">Indexed</option>
                    <option value="indexing">Indexing</option>
                    <option value="failed">Failed</option>
                  </select>
                </div>

                <button
                  type="button"
                  onClick={() => token && void fetchDocs(token)}
                  className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
                >
                  <svg viewBox="0 0 24 24" fill="none" className="size-3.5" aria-hidden="true">
                    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <path d="M3 3v5h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <path d="M16 16h5v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Refresh</span>
                </button>
              </div>

              {/* Table */}
              {loading ? (
                <div className="py-16 text-center text-xs text-slate-400">
                  <span className="inline-block size-6 animate-spin rounded-full border-2 border-indigo-500/30 border-t-indigo-500" />
                  <p className="mt-3">Loading knowledge base documents...</p>
                </div>
              ) : filteredDocuments.length === 0 ? (
                <div className="py-16 text-center">
                  <p className="text-sm font-semibold text-slate-300">No documents match your filter</p>
                  <p className="mt-1 text-xs text-slate-500">Upload documents above or reset filters to see existing documents.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-white/10 bg-slate-950/40 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        <th className="px-6 py-3.5">Document</th>
                        <th className="px-6 py-3.5">Category</th>
                        <th className="px-6 py-3.5">Pages</th>
                        <th className="px-6 py-3.5">Status</th>
                        <th className="px-6 py-3.5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {filteredDocuments.map((doc) => {
                        const catStyle = BUCKET_COLORS[doc.bucket] ?? BUCKET_COLORS.general;
                        const isActionBusy = actionInProgressId === doc.id;
                        return (
                          <tr key={doc.id} className="transition hover:bg-white/[0.02]">
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-indigo-400 ring-1 ring-white/10">
                                  <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden="true">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
                                    <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                                  </svg>
                                </div>
                                <div className="min-w-0">
                                  <p className="font-semibold text-white truncate max-w-sm">{doc.filename}</p>
                                  <p className="font-mono text-[10px] text-slate-500">Hash: {doc.file_hash.slice(0, 12)}...</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <span className={`inline-flex items-center rounded-md border px-2.5 py-1 text-[11px] font-semibold ${catStyle.bg} ${catStyle.text} ${catStyle.border}`}>
                                {doc.bucket === "hr" ? "HR" : doc.bucket.toUpperCase()}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-slate-300 font-medium">
                              {doc.page_count} {doc.page_count === 1 ? "page" : "pages"}
                            </td>
                            <td className="px-6 py-4">
                              {doc.status === "indexed" ? (
                                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-400">
                                  <span className="size-1.5 rounded-full bg-emerald-400" />
                                  Indexed
                                </span>
                              ) : doc.status === "failed" ? (
                                <button
                                  type="button"
                                  onClick={() => setSelectedDocError(doc)}
                                  className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] font-semibold text-red-400 hover:bg-red-500/20"
                                  title="Click to inspect failure reason"
                                >
                                  <span className="size-1.5 rounded-full bg-red-400" />
                                  Failed (View Error)
                                </button>
                              ) : (
                                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-400">
                                  <span className="size-1.5 animate-spin rounded-full border border-amber-400 border-t-transparent" />
                                  {doc.status === "indexing" ? "Indexing..." : "Uploaded"}
                                </span>
                              )}
                            </td>
                            <td className="px-6 py-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  type="button"
                                  disabled={isActionBusy}
                                  onClick={() => void handleReindex(doc)}
                                  className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-950/60 px-2.5 py-1.5 text-[11px] font-semibold text-slate-300 hover:border-indigo-500/50 hover:bg-slate-800 disabled:opacity-50"
                                  title="Re-run parsing and vector embedding"
                                >
                                  <svg viewBox="0 0 24 24" fill="none" className={`size-3.5 ${isActionBusy ? "animate-spin" : ""}`} aria-hidden="true">
                                    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                    <path d="M3 3v5h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                    <path d="M16 16h5v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                  </svg>
                                  <span>Re-index</span>
                                </button>
                                <button
                                  type="button"
                                  disabled={isActionBusy}
                                  onClick={() => void handleDelete(doc)}
                                  className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-950/60 p-1.5 text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                                  title="Delete document and vector embeddings"
                                >
                                  <svg viewBox="0 0 24 24" fill="none" className="size-3.5" aria-hidden="true">
                                    <path d="M3 6h18m-2 0v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6m3 0V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        ) : (
          /* Live RAG Debugger & Retrieval Inspector */
          <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-7 shadow-xl backdrop-blur">
            <div>
              <h2 className="text-lg font-bold text-white">Interactive RAG Retrieval Playground</h2>
              <p className="text-xs text-slate-400">
                Test question routing, inspect chunk cosine similarities, and verify retrieved context grounding before it hits the LLM.
              </p>
            </div>

            <form onSubmit={handleDebugSubmit} className="mt-5 flex gap-3">
              <input
                type="text"
                value={debugQuestion}
                onChange={(e) => setDebugQuestion(e.target.value)}
                placeholder="Type a policy question (e.g., 'What is the leave policy for vacations?')"
                className="flex-1 rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-indigo-500"
              />
              <button
                type="submit"
                disabled={!debugQuestion.trim() || debugLoading}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-3 text-xs font-semibold text-white shadow-lg shadow-indigo-600/25 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50"
              >
                {debugLoading ? (
                  <>
                    <span className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    <span>Searching...</span>
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" fill="none" className="size-4" aria-hidden="true">
                      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
                      <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    <span>Test Retrieval</span>
                  </>
                )}
              </button>
            </form>

            {debugResult ? (
              <div className="mt-7 space-y-5">
                {/* Routing summary */}
                <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4 text-xs">
                  <div>
                    <span className="text-slate-400">Routed Buckets: </span>
                    <span className="font-bold text-indigo-400">
                      {debugResult.buckets.map((b) => (b === "hr" ? "HR" : b.toUpperCase())).join(", ")}
                    </span>
                  </div>
                  <div className="h-4 w-px bg-white/10" />
                  <div>
                    <span className="text-slate-400">Router Source: </span>
                    <span className="rounded-md border border-white/10 bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-amber-300">
                      {debugResult.route_source}
                    </span>
                  </div>
                  <div className="h-4 w-px bg-white/10" />
                  <div>
                    <span className="text-slate-400">Chunks Found: </span>
                    <span className="font-bold text-emerald-400">{debugResult.results.length}</span>
                  </div>
                </div>

                {/* Chunks List */}
                <div className="space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Retrieved Chunks & Similarity Breakdown</h3>
                  {debugResult.results.length === 0 ? (
                    <div className="rounded-2xl border border-white/5 bg-slate-950/40 p-6 text-center text-xs text-slate-400">
                      No matching chunks found above minimum similarity threshold (0.55).
                    </div>
                  ) : (
                    debugResult.results.map((chunk, idx) => (
                      <div key={idx} className="rounded-2xl border border-white/10 bg-slate-950/50 p-5 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-3">
                          <div className="flex items-center gap-2">
                            <span className="flex size-6 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">
                              C{idx + 1}
                            </span>
                            <span className="font-semibold text-white text-xs">{chunk.filename}</span>
                            <span className="text-slate-500">·</span>
                            <span className="text-xs text-slate-400">Page {chunk.page}</span>
                            <span className="text-slate-500">·</span>
                            <span className="text-xs text-slate-400">{chunk.section}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-[11px] text-slate-400">Tokens: ~{chunk.token_estimate}</span>
                            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-mono font-bold text-emerald-300">
                              {(chunk.score * 100).toFixed(1)}% match
                            </span>
                          </div>
                        </div>
                        <p className="whitespace-pre-wrap font-mono text-xs leading-6 text-slate-300 bg-slate-900/60 p-3 rounded-xl border border-white/5">
                          {chunk.text}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}
          </section>
        )}
      </div>

      {/* Error Details Modal */}
      {selectedDocError ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-3xl border border-red-500/30 bg-slate-900 p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div className="flex items-center gap-2 text-red-400">
                <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
                  <path d="M12 8v4m0 4h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <h3 className="font-bold text-sm text-white">Document Processing Details</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDocError(null)}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>
            <div className="mt-4 space-y-3 text-xs">
              <div>
                <span className="text-slate-400">File: </span>
                <span className="font-semibold text-white">{selectedDocError.filename}</span>
              </div>
              <div>
                <span className="text-slate-400">Category: </span>
                <span className="text-indigo-300 uppercase">{selectedDocError.bucket}</span>
              </div>
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4">
                <p className="font-semibold text-red-300 mb-1">Reason for failure:</p>
                <p className="font-mono text-red-200 whitespace-pre-wrap leading-5">
                  {selectedDocError.error_message || "An error occurred during vector generation or file parsing."}
                </p>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSelectedDocError(null)}
                className="rounded-xl border border-white/10 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => {
                  const doc = selectedDocError;
                  setSelectedDocError(null);
                  void handleReindex(doc);
                }}
                className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500"
              >
                Retry Re-indexing Now
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
