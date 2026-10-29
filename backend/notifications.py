from database import get_connection


def insert_notification(cursor, user_id: int, kind: str, message: str):
    """Insert inside an existing transaction owned by the calling workflow."""
    cursor.execute("""
        INSERT INTO notifications (user_id, kind, message)
        VALUES (%s, %s, %s)
        RETURNING notification_id, kind, message, read_at, created_at
    """, (user_id, kind, message))
    row = cursor.fetchone()
    return {"notification_id": row[0], "kind": row[1], "message": row[2],
            "read_at": row[3], "created_at": row[4]}


def create_notification(user_id: int, kind: str, message: str):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            notification = insert_notification(cursor, user_id, kind, message)
        connection.commit()
        return notification
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_notifications(user_id: int, limit=30):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT notification_id, kind, message, read_at, created_at
                FROM notifications WHERE user_id = %s
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, limit))
            rows = cursor.fetchall()
        return [{"notification_id": row[0], "kind": row[1], "message": row[2],
                 "read_at": row[3], "created_at": row[4]} for row in rows]
    finally:
        connection.close()


def mark_notification_read(notification_id: int, user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
                WHERE notification_id = %s AND user_id = %s
                RETURNING notification_id, kind, message, read_at, created_at
            """, (notification_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise PermissionError("Notification not found")
        connection.commit()
        return {"notification_id": row[0], "kind": row[1], "message": row[2],
                "read_at": row[3], "created_at": row[4]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
