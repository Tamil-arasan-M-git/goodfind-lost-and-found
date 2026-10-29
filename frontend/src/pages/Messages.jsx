import { useEffect, useState } from "react";
import { apiUrl } from "../api";

function Messages() {
  const [conversations, setConversations] = useState([]);
  const [requests, setRequests] = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [content, setContent] = useState("");
  const [reportReason, setReportReason] = useState("");
  const [error, setError] = useState("");
  const token = localStorage.getItem("goodfind_access_token");
  const user = JSON.parse(localStorage.getItem("goodfind_user") || "{}");
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  async function api(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: { ...headers, ...options.headers },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  }

  async function loadInbox() {
    try {
      const [conversationData, requestData, notificationData] = await Promise.all([
        api("/api/chat/conversations"), api("/api/chat/requests"), api("/api/notifications"),
      ]);
      setConversations(conversationData.conversations || []);
      setRequests(requestData.requests || []);
      setNotifications(notificationData.notifications || []);
    } catch (err) { setError(err.message); }
  }

  async function openConversation(conversation) {
    try {
      setSelected(conversation);
      const data = await api(`/api/chat/conversations/${conversation.conversation_id}/messages`);
      setMessages(data.messages || []);
    } catch (err) { setError(err.message); }
  }

  useEffect(() => {
    // Defer the initial external fetch so the effect subscribes after render.
    const timer = setTimeout(() => { void loadInbox(); }, 0);
    return () => clearTimeout(timer);
    // loadInbox intentionally runs once when the inbox opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected || selected.status !== "ACTIVE") return undefined;
    const timer = setInterval(() => openConversation(selected), 8000);
    return () => clearInterval(timer);
    // The interval is intentionally recreated only for the selected conversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.conversation_id, selected?.status]);

  async function respond(requestId, accept) {
    try {
      const data = await api(`/api/chat/requests/${requestId}`, {
        method: "PUT", body: JSON.stringify({ accept }),
      });
      await loadInbox();
      if (data.conversation) await openConversation(data.conversation);
    } catch (err) { setError(err.message); }
  }

  async function send(event) {
    event.preventDefault();
    try {
      const data = await api(`/api/chat/conversations/${selected.conversation_id}/messages`, {
        method: "POST", body: JSON.stringify({ content }),
      });
      setMessages((old) => [...old, data.message]);
      setContent("");
    } catch (err) { setError(err.message); }
  }

  async function close() {
    try {
      await api(`/api/chat/conversations/${selected.conversation_id}/close`, { method: "POST" });
      setSelected({ ...selected, status: "CLOSED" });
      await loadInbox();
    } catch (err) { setError(err.message); }
  }

  async function block() {
    try {
      await api(`/api/chat/conversations/${selected.conversation_id}/block`, { method: "POST" });
      setError("You blocked this member. Neither participant can send further messages in this conversation.");
    } catch (err) { setError(err.message); }
  }

  async function report(event) {
    event.preventDefault();
    try {
      await api(`/api/chat/conversations/${selected.conversation_id}/reports`, {
        method: "POST", body: JSON.stringify({ reason: reportReason }),
      });
      setReportReason("");
      setError("Report submitted. It is visible only to GoodFind moderators.");
    } catch (err) { setError(err.message); }
  }

  async function markRead(notificationId) {
    try {
      const data = await api(`/api/notifications/${notificationId}/read`, { method: "POST" });
      setNotifications((current) => current.map((notification) =>
        notification.notification_id === notificationId ? data.notification : notification));
    } catch (err) { setError(err.message); }
  }

  const incoming = requests.filter((request) => request.recipient_user_id === user.user_id && request.status === "PENDING");

  return <div className="report-page messages-page"><div className="report-container">
    <div className="report-header"><p className="section-label">PRIVATE MESSAGES</p><h1>GoodFind inbox</h1><p>Aliases protect identities. Arrange a safe handover here; do not share personal contact details.</p></div>
    {error && <p className="error-message">{error}</p>}
    {notifications.length > 0 && <section className="item-info inbox-card" aria-label="Notifications">
      <h2>Updates</h2>
      {notifications.map((notification) => <div className="notification-row" key={notification.notification_id}>
        <p>{notification.message}</p>
        {!notification.read_at && <button className="secondary-button compact-button" type="button" onClick={() => markRead(notification.notification_id)}>Mark read</button>}
      </div>)}
    </section>}
    {incoming.map((request) => <div key={request.request_id} className="item-info inbox-card">
      <p>A GoodFind member wants to discuss a possible match.</p>
      <button className="primary-button compact-button" onClick={() => respond(request.request_id, true)}>Accept</button>{" "}
      <button className="secondary-button compact-button" onClick={() => respond(request.request_id, false)}>Decline</button>
    </div>)}
    <div className="inbox-layout">
      <aside className="conversation-list">{conversations.length ? conversations.map((conversation) => <button className="conversation-button" key={conversation.conversation_id} onClick={() => openConversation(conversation)}>
        {conversation.item_name}<br /><small>{conversation.other_alias} · {conversation.status}</small>
      </button>) : <p>No accepted conversations yet.</p>}</aside>
      <section className="chat-panel">{selected ? <>
        <h2>{selected.item_name}</h2><p>Chatting with {selected.other_alias}. Status: {selected.status}</p>
        <div className="message-thread">
          {messages.map((message) => <p className={`message-bubble ${message.is_mine ? "mine" : ""}`} key={message.message_id}><strong>{message.sender_alias}:</strong> {message.content}</p>)}
        </div>
        {selected.status === "ACTIVE" ? <><form className="message-composer" onSubmit={send}><label className="visually-hidden" htmlFor="message-content">Message</label><textarea id="message-content" value={content} onChange={(event) => setContent(event.target.value)} maxLength="2000" required rows="3" /><div><button className="primary-button compact-button" type="submit">Send</button>{" "}<button className="secondary-button compact-button" type="button" onClick={close}>Confirm return & close</button>{" "}<button className="danger-button compact-button" type="button" onClick={block}>Block member</button></div></form>
        <form className="report-composer" onSubmit={report}><label htmlFor="report-reason">Report this member</label><textarea id="report-reason" value={reportReason} onChange={(event) => setReportReason(event.target.value)} maxLength="500" required rows="2" /><button className="text-button" type="submit">Submit confidential report</button></form></> : <p className="closed-note">This conversation is closed.</p>}
      </> : <p>Select a conversation to read messages.</p>}</section>
    </div>
  </div></div>;
}

export default Messages;
