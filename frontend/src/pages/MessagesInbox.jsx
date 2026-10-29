import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../api";

const POLL_INTERVAL_MS = 8000;

function formatTime(value) {
  if (!value) return "No messages yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function requestLabel(status) {
  return ({ PENDING: "Waiting for a response", ACCEPTED: "Request accepted", DECLINED: "Request declined", CANCELLED: "Request cancelled" })[status] || "Request updated";
}

export default function MessagesInbox() {
  const [conversations, setConversations] = useState([]);
  const [requests, setRequests] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [tab, setTab] = useState("conversations");
  const [content, setContent] = useState("");
  const [reportReason, setReportReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [respondingId, setRespondingId] = useState(null);
  const [sending, setSending] = useState(false);
  const [action, setAction] = useState("");
  const [failedMessage, setFailedMessage] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const threadRef = useRef(null);
  const formRef = useRef(null);
  const stickToBottom = useRef(true);
  const fetchSequence = useRef(0);
  const token = localStorage.getItem("goodfind_access_token");

  async function api(path, options = {}) {
    const response = await fetch(apiUrl(path), { ...options, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers } });
    const text = await response.text();
    let data = {};
    if (text) {
      try { data = JSON.parse(text); } catch { throw new Error("GoodFind returned an unexpected response. Please try again."); }
    }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed. Please try again.");
    return data;
  }

  async function loadInbox(quiet = false) {
    if (!quiet) setLoading(true);
    setError("");
    try {
      const [conversationData, requestData, notificationData] = await Promise.all([api("/api/chat/conversations"), api("/api/chat/requests"), api("/api/notifications")]);
      if (![conversationData.conversations, requestData.requests, notificationData.notifications].every(Array.isArray)) throw new Error("GoodFind returned incomplete inbox data. Please try again.");
      setConversations(conversationData.conversations);
      setRequests(requestData.requests);
      setNotifications(notificationData.notifications);
      setSelected((current) => current ? conversationData.conversations.find((entry) => entry.conversation_id === current.conversation_id) || current : null);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load your inbox."); }
    finally { if (!quiet) setLoading(false); }
  }

  async function openConversation(conversation, quiet = false) {
    const sequence = ++fetchSequence.current;
    setSelected(conversation);
    if (!quiet) { setLoadingMessages(true); setMessages([]); stickToBottom.current = true; }
    setError("");
    try {
      const data = await api(`/api/chat/conversations/${conversation.conversation_id}/messages`);
      if (!Array.isArray(data.messages)) throw new Error("GoodFind returned incomplete message data. Please try again.");
      if (sequence === fetchSequence.current) setMessages(data.messages);
    } catch (err) {
      if (sequence === fetchSequence.current) setError(err instanceof Error ? err.message : "Unable to load this conversation.");
    } finally { if (!quiet && sequence === fetchSequence.current) setLoadingMessages(false); }
  }

  useEffect(() => {
    const timer = setTimeout(() => { void loadInbox(); }, 0);
    return () => clearTimeout(timer);
    // Loaded once on entry; actions explicitly refresh it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!selected || selected.status !== "ACTIVE") return undefined;
    const timer = setInterval(() => { void openConversation(selected, true); }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.conversation_id, selected?.status]); // Polling is the existing delivery mechanism.
  useEffect(() => { if (stickToBottom.current && threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight; }, [messages, selected?.conversation_id]);

  function onThreadScroll() {
    const thread = threadRef.current;
    if (thread) stickToBottom.current = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 40;
  }

  async function respond(requestId, accept) {
    setRespondingId(requestId); setError(""); setNotice("");
    try {
      const data = await api(`/api/chat/requests/${requestId}`, { method: "PUT", body: JSON.stringify({ accept }) });
      await loadInbox(true);
      if (accept && data.conversation) { setTab("conversations"); setNotice("Request accepted. You can now coordinate a safe handover privately."); await openConversation(data.conversation); }
      else setNotice("Request declined. No conversation was opened.");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to update the request."); }
    finally { setRespondingId(null); }
  }

  async function sendMessage(value = content) {
    const trimmed = value.trim();
    if (!selected || !trimmed || sending) return;
    setSending(true); setError(""); setFailedMessage(null);
    try {
      const data = await api(`/api/chat/conversations/${selected.conversation_id}/messages`, { method: "POST", body: JSON.stringify({ content: trimmed }) });
      if (!data.message || typeof data.message.message_id !== "number") throw new Error("GoodFind did not confirm that the message was sent.");
      setMessages((current) => current.some((message) => message.message_id === data.message.message_id) ? current : [...current, data.message]);
      setContent(""); stickToBottom.current = true;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Message was not sent.";
      setFailedMessage({ content: trimmed, error: message }); setError(message);
    } finally { setSending(false); }
  }

  async function closeConversation() {
    if (!selected || !window.confirm("Close this conversation? New messages will no longer be allowed.")) return;
    setAction("close"); setError("");
    try {
      const data = await api(`/api/chat/conversations/${selected.conversation_id}/close`, { method: "POST" });
      setSelected((current) => ({ ...current, ...data.conversation })); setNotice("Conversation closed. New messages are disabled."); await loadInbox(true);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to close this conversation."); }
    finally { setAction(""); }
  }

  async function blockParticipant() {
    if (!selected || !window.confirm("Block this member? Neither participant will be able to send further messages here.")) return;
    setAction("block"); setError("");
    try { await api(`/api/chat/conversations/${selected.conversation_id}/block`, { method: "POST" }); setSelected((current) => ({ ...current, is_blocked: true })); setNotice("Member blocked. Messaging is disabled."); await loadInbox(true); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to block this member."); }
    finally { setAction(""); }
  }

  async function report(event) {
    event.preventDefault(); if (!selected) return;
    setAction("report"); setError("");
    try { await api(`/api/chat/conversations/${selected.conversation_id}/reports`, { method: "POST", body: JSON.stringify({ reason: reportReason.trim() }) }); setReportReason(""); setNotice("Report submitted confidentially to GoodFind moderators."); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to submit this report."); }
    finally { setAction(""); }
  }

  async function markRead(notificationId) {
    try { const data = await api(`/api/notifications/${notificationId}/read`, { method: "POST" }); setNotifications((current) => current.map((entry) => entry.notification_id === notificationId ? data.notification : entry)); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to mark the update as read."); }
  }

  const incoming = requests.filter((request) => request.is_incoming && request.status === "PENDING");
  const outgoing = requests.filter((request) => !request.is_incoming);
  const unreadCount = notifications.filter((entry) => !entry.read_at).length;
  const messagingDisabled = !selected || selected.status !== "ACTIVE" || selected.is_blocked;

  return <div className="report-page messages-page"><div className="report-container messages-shell">
    <div className="report-header"><p className="section-label">PRIVATE MESSAGES</p><h1>GoodFind inbox</h1><p>Aliases protect identities. Keep handover details here and avoid sharing personal contact information.</p></div>
    {error && <div className="error-state" role="alert"><p>{error}</p><button type="button" className="secondary-button compact-button" onClick={() => void loadInbox()}>Try again</button></div>}
    {notice && <p className="success-message" role="status">{notice}</p>}
    {notifications.length > 0 && <section className="item-info inbox-card updates-card" aria-label="Inbox updates"><div className="inbox-section-heading"><h2>Updates {unreadCount > 0 && <span className="unread-count">{unreadCount} unread</span>}</h2></div>{notifications.map((notification) => <div className="notification-row" key={notification.notification_id}><div><p>{notification.message}</p><small>{formatTime(notification.created_at)}</small></div>{!notification.read_at && <button className="secondary-button compact-button" type="button" onClick={() => void markRead(notification.notification_id)}>Mark read</button>}</div>)}</section>}
    <div className="messages-tabs" role="tablist" aria-label="Inbox sections"><button type="button" role="tab" aria-selected={tab === "conversations"} className={tab === "conversations" ? "active" : ""} onClick={() => setTab("conversations")}>Conversations ({conversations.length})</button><button type="button" role="tab" aria-selected={tab === "requests"} className={tab === "requests" ? "active" : ""} onClick={() => setTab("requests")}>Requests {incoming.length > 0 && <span className="tab-badge">{incoming.length}</span>}</button></div>
    {loading ? <p className="loading-state" role="status">Loading your private inbox…</p> : tab === "requests" ? <section className="requests-panel" role="tabpanel"><h2>Chat requests</h2>{incoming.length > 0 && <div className="request-list">{incoming.map((request) => <article className="request-card" key={request.request_id}><p className="request-kicker">Incoming request</p><h3>{request.item_name || "Possible item match"}</h3><p><strong>{request.other_alias || "GoodFind member"}</strong> would like to discuss this possible match.</p><small>{formatTime(request.created_at)}</small><div className="request-actions"><button className="primary-button compact-button" type="button" disabled={respondingId === request.request_id} onClick={() => void respond(request.request_id, true)}>{respondingId === request.request_id ? "Updating…" : "Accept"}</button><button className="secondary-button compact-button" type="button" disabled={respondingId === request.request_id} onClick={() => void respond(request.request_id, false)}>Decline</button></div></article>)}</div>}{outgoing.length > 0 && <div className="outgoing-requests"><h3>Your requests</h3>{outgoing.map((request) => <article className="request-row" key={request.request_id}><div><strong>{request.item_name || "Possible item match"}</strong><p>{requestLabel(request.status)}</p></div><small>{formatTime(request.responded_at || request.created_at)}</small></article>)}</div>}{incoming.length === 0 && outgoing.length === 0 && <div className="empty-inbox"><h3>No chat requests</h3><p>New private chat requests about possible matches will appear here.</p></div>}</section> : <div className="inbox-layout">
      <aside className="conversation-list" aria-label="Accepted conversations"><div className="inbox-section-heading"><h2>Conversations</h2><button type="button" className="text-link-button refresh-button" onClick={() => void loadInbox()}>Refresh</button></div>{conversations.length ? conversations.map((conversation) => <button type="button" aria-current={selected?.conversation_id === conversation.conversation_id ? "page" : undefined} className={`conversation-button ${selected?.conversation_id === conversation.conversation_id ? "selected" : ""}`} key={conversation.conversation_id} onClick={() => void openConversation(conversation)}><strong>{conversation.item_name || "Possible item match"}</strong><span>{conversation.other_alias}</span><small>{conversation.last_message || "No messages yet"}</small><time>{formatTime(conversation.last_message_at || conversation.created_at)}</time></button>) : <div className="empty-inbox"><h3>No conversations yet</h3><p>Accept a chat request to begin a private handover conversation.</p></div>}</aside>
      <section className="chat-panel" aria-live="polite">{selected ? <><div className="conversation-header"><button type="button" className="text-link-button back-to-inbox" onClick={() => setSelected(null)}>← Inbox</button><p className="request-kicker">Related item</p><h2>{selected.item_name || "Possible item match"}</h2><p>Chatting with <strong>{selected.other_alias}</strong> · {selected.status === "ACTIVE" ? "Active conversation" : "Conversation closed"}</p></div>{loadingMessages ? <p className="loading-state" role="status">Loading messages…</p> : <div className="message-thread" ref={threadRef} onScroll={onThreadScroll} aria-label="Message history">{messages.length ? messages.map((message) => <article className={`message-bubble ${message.is_mine ? "mine" : ""}`} key={message.message_id}><span className="message-author">{message.is_mine ? "You" : message.sender_alias}</span><p>{message.content}</p><time>{formatTime(message.created_at)}</time></article>) : <p className="empty-thread">No messages yet. Start with a safe handover question.</p>}</div>}{selected.status !== "ACTIVE" ? <p className="closed-note">This conversation is closed. New messages are permanently disabled.</p> : selected.is_blocked ? <p className="closed-note">You blocked this member. Messaging is disabled.</p> : <form ref={formRef} className="message-composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}><label htmlFor="message-content">Message <span>Enter sends · Shift+Enter adds a line</span></label><textarea id="message-content" value={content} onChange={(event) => setContent(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); formRef.current?.requestSubmit(); } }} maxLength="2000" disabled={messagingDisabled || sending} rows="3" placeholder="Write a message without sharing personal contact details" /><div className="composer-footer"><small>{content.trim().length}/2000</small><button className="primary-button compact-button" type="submit" disabled={messagingDisabled || sending || !content.trim()}>{sending ? "Sending…" : "Send"}</button></div></form>}{failedMessage && <div className="message-failure" role="alert"><p>Message not sent: {failedMessage.error}</p><button type="button" className="secondary-button compact-button" disabled={sending || messagingDisabled} onClick={() => void sendMessage(failedMessage.content)}>Retry message</button></div>}<div className="conversation-safety"><button className="secondary-button compact-button" type="button" disabled={action === "close" || selected.status !== "ACTIVE"} onClick={() => void closeConversation()}>{action === "close" ? "Closing…" : "Confirm return & close"}</button><button className="danger-button compact-button" type="button" disabled={action === "block" || selected.is_blocked} onClick={() => void blockParticipant()}>{selected.is_blocked ? "Member blocked" : action === "block" ? "Blocking…" : "Block member"}</button></div><form className="report-composer" onSubmit={report}><label htmlFor="report-reason">Report this member confidentially</label><textarea id="report-reason" value={reportReason} onChange={(event) => setReportReason(event.target.value)} maxLength="500" required rows="2" disabled={action === "report"} placeholder="Explain the concerning behavior (1–500 characters)" /><button className="text-button" type="submit" disabled={action === "report" || !reportReason.trim()}>{action === "report" ? "Submitting…" : "Submit confidential report"}</button></form></> : <div className="empty-inbox chat-empty"><h2>Select a conversation</h2><p>Choose an accepted conversation to view messages and coordinate a safe handover.</p></div>}</section>
    </div>}
  </div></div>;
}
