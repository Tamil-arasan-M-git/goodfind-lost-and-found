import uuid

from database import get_connection
from notifications import insert_notification


def _alias() -> str:
    return f"GoodFind member {uuid.uuid4().hex[:8]}"


def _request_row(row):
    return {
        "request_id": row[0], "match_id": row[1], "requester_user_id": row[2],
        "recipient_user_id": row[3], "status": row[4], "created_at": row[5],
        "responded_at": row[6],
    }


def create_chat_request(match_id: int, requester_user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT l.user_id, f.user_id, l.item_name FROM matches m
                JOIN items l ON l.item_id = m.lost_item_id
                JOIN items f ON f.item_id = m.found_item_id
                WHERE m.match_id = %s
                  AND m.status = 'PENDING'
                  AND l.status = 'ACTIVE'
                  AND f.status = 'ACTIVE'
                FOR UPDATE OF m, l, f
            """, (match_id,))
            match = cursor.fetchone()
            if not match:
                raise ValueError("Match not found")
            if match[0] != requester_user_id:
                raise PermissionError("Only the lost-item owner can request a conversation")
            if match[0] == match[1]:
                raise ValueError("A conversation cannot be created with yourself")
            cursor.execute("""
                SELECT 1 FROM user_blocks WHERE
                (blocker_user_id = %s AND blocked_user_id = %s) OR
                (blocker_user_id = %s AND blocked_user_id = %s)
            """, (requester_user_id, match[1], match[1], requester_user_id))
            if cursor.fetchone():
                raise PermissionError("A participant has blocked this conversation")
            cursor.execute("""
                SELECT status FROM chat_requests
                WHERE match_id = %s AND requester_user_id = %s FOR UPDATE
            """, (match_id, requester_user_id))
            existing = cursor.fetchone()
            should_notify = existing is None or existing[0] in ("DECLINED", "CANCELLED")
            cursor.execute("""
                INSERT INTO chat_requests (match_id, requester_user_id, recipient_user_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (match_id, requester_user_id) DO UPDATE SET
                    status = CASE WHEN chat_requests.status IN ('DECLINED', 'CANCELLED')
                        THEN 'PENDING' ELSE chat_requests.status END,
                    created_at = CASE WHEN chat_requests.status IN ('DECLINED', 'CANCELLED')
                        THEN CURRENT_TIMESTAMP ELSE chat_requests.created_at END,
                    responded_at = CASE WHEN chat_requests.status IN ('DECLINED', 'CANCELLED')
                        THEN NULL ELSE chat_requests.responded_at END
                RETURNING request_id, match_id, requester_user_id, recipient_user_id,
                          status, created_at, responded_at
            """, (match_id, requester_user_id, match[1]))
            request = _request_row(cursor.fetchone())
            request["_notify_recipient"] = should_notify
            request["_email_item_name"] = match[2]
            if should_notify:
                insert_notification(
                    cursor, request["recipient_user_id"], "chat_request",
                    "You have a new private chat request for a possible item match."
                )
        connection.commit()
        return request
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def respond_to_chat_request(request_id: int, recipient_user_id: int, accept: bool):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT request_id, match_id, requester_user_id, recipient_user_id, status,
                       created_at, responded_at
                FROM chat_requests WHERE request_id = %s FOR UPDATE
            """, (request_id,))
            request = cursor.fetchone()
            if not request:
                raise ValueError("Chat request not found")
            if request[3] != recipient_user_id:
                raise PermissionError("Only the request recipient can respond")
            if request[4] != "PENDING":
                raise ValueError("This chat request has already been handled")
            cursor.execute("""
                SELECT m.status, l.status, f.status
                FROM matches m
                JOIN items l ON l.item_id = m.lost_item_id
                JOIN items f ON f.item_id = m.found_item_id
                WHERE m.match_id = %s
                FOR UPDATE OF m, l, f
            """, (request[1],))
            lifecycle = cursor.fetchone()
            if not lifecycle:
                raise ValueError("This chat request is no longer eligible")
            if accept and (lifecycle[0] != "PENDING" or lifecycle[1] != "ACTIVE" or lifecycle[2] != "ACTIVE"):
                raise ValueError("This chat request is no longer eligible")
            status = "ACCEPTED" if accept else "DECLINED"
            cursor.execute("""
                UPDATE chat_requests SET status = %s, responded_at = CURRENT_TIMESTAMP
                WHERE request_id = %s
                RETURNING request_id, match_id, requester_user_id, recipient_user_id,
                          status, created_at, responded_at
            """, (status, request_id))
            response = _request_row(cursor.fetchone())
            conversation = None
            if accept:
                cursor.execute("""
                    INSERT INTO conversations (match_id, request_id)
                    VALUES (%s, %s)
                    RETURNING conversation_id, status, created_at
                """, (request[1], request_id))
                row = cursor.fetchone()
                conversation = {"conversation_id": row[0], "status": row[1], "created_at": row[2]}
                cursor.executemany("""
                    INSERT INTO conversation_participants
                        (conversation_id, user_id, display_alias)
                    VALUES (%s, %s, %s)
                """, [(row[0], request[2], _alias()), (row[0], request[3], _alias())])
                insert_notification(
                    cursor, request[2], "chat_accepted",
                    "Your private chat request was accepted."
                )
        connection.commit()
        return response, conversation
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _participant(cursor, conversation_id, user_id, lock=False):
    cursor.execute(f"""
        SELECT c.status, p.display_alias, p.blocked_at
        FROM conversations c JOIN conversation_participants p
        ON p.conversation_id = c.conversation_id
        WHERE c.conversation_id = %s AND p.user_id = %s{' FOR UPDATE' if lock else ''}
    """, (conversation_id, user_id))
    row = cursor.fetchone()
    if not row:
        raise PermissionError("You are not a participant in this conversation")
    return row


def list_conversations(user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.conversation_id, c.status, c.created_at, p.display_alias, p.blocked_at,
                       i.item_name, other.display_alias, latest.content, latest.created_at
                FROM conversations c
                JOIN conversation_participants p ON p.conversation_id = c.conversation_id
                JOIN conversation_participants other ON other.conversation_id = c.conversation_id
                    AND other.user_id <> p.user_id
                JOIN matches mt ON mt.match_id = c.match_id
                JOIN items i ON i.item_id = mt.lost_item_id
                LEFT JOIN LATERAL (
                    SELECT content, created_at FROM messages m
                    WHERE m.conversation_id = c.conversation_id
                    ORDER BY m.created_at DESC, m.message_id DESC LIMIT 1
                ) latest ON TRUE
                WHERE p.user_id = %s
                ORDER BY COALESCE(latest.created_at, c.created_at) DESC, c.conversation_id DESC
            """, (user_id,))
            return [{"conversation_id": r[0], "status": r[1], "created_at": r[2],
                     "your_alias": r[3], "is_blocked": r[4] is not None,
                     "item_name": r[5], "other_alias": r[6],
                     "last_message": r[7], "last_message_at": r[8]} for r in cursor.fetchall()]
    finally:
        connection.close()


def list_chat_requests(user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT r.request_id, r.match_id, r.requester_user_id, r.recipient_user_id,
                       r.status, r.created_at, r.responded_at, i.item_name
                FROM chat_requests r
                JOIN matches m ON m.match_id = r.match_id
                JOIN items i ON i.item_id = m.lost_item_id
                WHERE r.requester_user_id = %s OR r.recipient_user_id = %s
                ORDER BY r.created_at DESC, r.request_id DESC
            """, (user_id, user_id))
            return [{**_request_row(row), "item_name": row[7],
                     "other_alias": "GoodFind member",
                     "is_incoming": row[3] == user_id}
                    for row in cursor.fetchall()]
    finally:
        connection.close()


def get_messages(conversation_id: int, user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            _participant(cursor, conversation_id, user_id)
            cursor.execute("""
                SELECT m.message_id, m.content, m.created_at, p.display_alias
                FROM messages m JOIN conversation_participants p
                  ON p.conversation_id = m.conversation_id AND p.user_id = m.sender_user_id
                WHERE m.conversation_id = %s ORDER BY m.created_at, m.message_id
            """, (conversation_id,))
            return [{"message_id": r[0], "content": r[1], "created_at": r[2],
                     "sender_alias": r[3], "is_mine": r[3] == _participant(cursor, conversation_id, user_id)[1]}
                    for r in cursor.fetchall()]
    finally:
        connection.close()


def send_message(conversation_id: int, user_id: int, content: str):
    content = content.strip()
    if not content or len(content) > 2000:
        raise ValueError("Message must be between 1 and 2000 characters")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            status, alias, blocked_at = _participant(cursor, conversation_id, user_id, lock=True)
            if status != "ACTIVE":
                raise ValueError("This conversation is closed")
            if blocked_at:
                raise PermissionError("You have blocked this conversation")
            cursor.execute("""
                SELECT 1 FROM conversation_participants p
                JOIN user_blocks b ON b.blocker_user_id = p.user_id AND b.blocked_user_id = %s
                WHERE p.conversation_id = %s
            """, (user_id, conversation_id))
            if cursor.fetchone():
                raise PermissionError("You cannot message a participant who blocked you")
            cursor.execute("""
                SELECT user_id FROM conversation_participants
                WHERE conversation_id = %s AND user_id <> %s
            """, (conversation_id, user_id))
            recipient = cursor.fetchone()
            if not recipient:
                raise ValueError("Conversation participant not found")
            cursor.execute("""
                INSERT INTO messages (conversation_id, sender_user_id, content)
                VALUES (%s, %s, %s) RETURNING message_id, content, created_at
            """, (conversation_id, user_id, content))
            row = cursor.fetchone()
        connection.commit()
        return {"message_id": row[0], "content": row[1], "created_at": row[2], "sender_alias": alias,
                "is_mine": True, "_notify_recipient_user_id": recipient[0]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def close_conversation(conversation_id: int, user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            _participant(cursor, conversation_id, user_id, lock=True)
            cursor.execute("""
                UPDATE conversations SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP,
                closed_by_user_id = %s WHERE conversation_id = %s AND status = 'ACTIVE'
                RETURNING conversation_id, status, closed_at
            """, (user_id, conversation_id))
            row = cursor.fetchone()
            if not row:
                cursor.execute("""
                    SELECT conversation_id, status, closed_at FROM conversations
                    WHERE conversation_id = %s
                """, (conversation_id,))
                row = cursor.fetchone()
        connection.commit()
        return {"conversation_id": row[0], "status": row[1], "closed_at": row[2]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def block_conversation_participant(conversation_id: int, blocker_user_id: int):
    """Block the other participant and stop either side from sending further messages."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            _participant(cursor, conversation_id, blocker_user_id, lock=True)
            cursor.execute("""
                SELECT user_id FROM conversation_participants
                WHERE conversation_id = %s AND user_id <> %s
            """, (conversation_id, blocker_user_id))
            other = cursor.fetchone()
            if not other:
                raise ValueError("Conversation participant not found")
            cursor.execute("""
                INSERT INTO user_blocks (blocker_user_id, blocked_user_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                RETURNING blocked_user_id
            """, (blocker_user_id, other[0]))
            inserted = cursor.fetchone()
            cursor.execute("""
                UPDATE conversation_participants SET blocked_at = CURRENT_TIMESTAMP
                WHERE conversation_id = %s AND user_id = %s
                RETURNING blocked_at
            """, (conversation_id, blocker_user_id))
            blocked_at = cursor.fetchone()[0]
        connection.commit()
        return {"conversation_id": conversation_id, "blocked": True,
                "already_blocked": inserted is None, "blocked_at": blocked_at}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def report_conversation_participant(conversation_id: int, reporter_user_id: int, reason: str):
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValueError("Report reason must be between 1 and 500 characters")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            _participant(cursor, conversation_id, reporter_user_id)
            cursor.execute("""
                SELECT user_id FROM conversation_participants
                WHERE conversation_id = %s AND user_id <> %s
            """, (conversation_id, reporter_user_id))
            other = cursor.fetchone()
            if not other:
                raise ValueError("Conversation participant not found")
            cursor.execute("""
                SELECT 1 FROM user_reports WHERE reporter_user_id = %s
                  AND reported_user_id = %s AND conversation_id = %s
            """, (reporter_user_id, other[0], conversation_id))
            if cursor.fetchone():
                raise ValueError("You have already reported this participant in this conversation")
            cursor.execute("""
                INSERT INTO user_reports
                    (reporter_user_id, reported_user_id, conversation_id, reason)
                VALUES (%s, %s, %s, %s)
                RETURNING report_id, created_at
            """, (reporter_user_id, other[0], conversation_id, reason))
            report = cursor.fetchone()
        connection.commit()
        return {"report_id": report[0], "conversation_id": conversation_id,
                "created_at": report[1]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
