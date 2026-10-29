from database import get_connection


ITEM_STATUSES = frozenset({"ACTIVE", "HANDOVER_IN_PROGRESS", "RESOLVED", "CLOSED"})


def _clean_filter(value):
    """Treat absent and whitespace-only query values identically."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _literal_like_pattern(value):
    """Build a parameter value for literal PostgreSQL ILIKE substring matching."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def normalize_status_filter(status):
    status = _clean_filter(status)
    if status is None:
        return None
    normalized = status.upper()
    if normalized not in ITEM_STATUSES:
        raise ValueError("Invalid item status")
    return normalized


def normalize_detection_labels(labels):
    if not isinstance(labels, list):
        raise ValueError("Detection labels must be a list")
    cleaned = []
    for label in labels[:20]:
        value = str(label).strip().lower()
        if value and len(value) <= 80 and value not in cleaned:
            cleaned.append(value)
    return cleaned


def create_lost_item(
    user_id: int,
    item_name: str,
    category: str,
    description: str,
    item_date: str,
    location: str,
    detection_labels=None,
):
    detection_labels = normalize_detection_labels(detection_labels or [])
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO items (
                    user_id,
                    item_type,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    detection_labels
                )
                VALUES (
                    %s,
                    'LOST',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING
                    item_id,
                    user_id,
                    item_type,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    detection_labels,
                    status,
                    created_at;
                """,
                (
                    user_id,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    detection_labels,
                ),
            )

            item = cursor.fetchone()

        connection.commit()

        return {
            "item_id": item[0],
            "user_id": item[1],
            "item_type": item[2],
            "item_name": item[3],
            "category": item[4],
            "description": item[5],
            "item_date": item[6],
            "location": item[7],
            "detection_labels": item[8],
            "status": item[9],
            "created_at": item[10],
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
def create_found_item(
    user_id: int,
    item_name: str,
    category: str,
    description: str,
    item_date: str,
    location: str,
    detection_labels=None,
):
    detection_labels = normalize_detection_labels(detection_labels or [])
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO items (
                    user_id,
                    item_type,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    detection_labels
                )
                VALUES (%s, 'FOUND', %s, %s, %s, %s, %s, %s)
                RETURNING
                    item_id,
                    user_id,
                    item_type,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    detection_labels,
                    status,
                    created_at;
                """,
                (
                    user_id,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    detection_labels,
                ),
            )

            item = cursor.fetchone()

        connection.commit()

        return {
            "item_id": item[0],
            "user_id": item[1],
            "item_type": item[2],
            "item_name": item[3],
            "category": item[4],
            "description": item[5],
            "item_date": item[6],
            "location": item[7],
            "detection_labels": item[8],
            "status": item[9],
            "created_at": item[10],
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
def get_items(item_type, search=None, category=None, location=None, status=None,
              limit=20, offset=0):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            filters = ["item_type = %s"]
            parameters = [item_type]
            search = _clean_filter(search)
            category = _clean_filter(category)
            location = _clean_filter(location)
            status = normalize_status_filter(status)
            if search:
                filters.append("(item_name ILIKE %s ESCAPE '\\' OR description ILIKE %s ESCAPE '\\')")
                pattern = _literal_like_pattern(search)
                parameters.extend([pattern, pattern])
            if category:
                filters.append("category ILIKE %s ESCAPE '\\'")
                parameters.append(_literal_like_pattern(category)[1:-1])
            if location:
                filters.append("location ILIKE %s ESCAPE '\\'")
                parameters.append(_literal_like_pattern(location))
            if status:
                filters.append("status = %s")
                parameters.append(status)
            where_clause = " AND ".join(filters)
            cursor.execute(f"""
                SELECT
                    item_id,
                    item_type,
                    item_name,
                    category,
                    description,
                    item_date,
                    location,
                    image_path,
                    status,
                    created_at
                FROM items
                WHERE {where_clause}
                ORDER BY created_at DESC, item_id DESC
                LIMIT %s OFFSET %s
            """, parameters + [limit, offset])
            rows = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) FROM items WHERE {where_clause}", parameters)
            total = cursor.fetchone()[0]
        results = []
        for row in rows:
            # Keep compatibility with older test fixtures/database projections while
            # exposing only the safe image endpoint, never the storage key.
            has_image_column = len(row) >= 10
            image_key = row[7] if has_image_column else None
            status_index = 8 if has_image_column else 7
            results.append({"item_id": row[0], "item_type": row[1], "item_name": row[2],
                            "category": row[3], "description": row[4], "item_date": row[5],
                            "location": row[6], "image_url": f"/api/items/{row[0]}/image" if image_key else None,
                            "status": row[status_index], "created_at": row[status_index + 1]})
        return results, total

    finally:
        connection.close()


def get_lost_items(**filters):
    return get_items("LOST", **filters)


def get_found_items(**filters):
    return get_items("FOUND", **filters)


def get_item_owner(item_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM items WHERE item_id = %s", (item_id,))
            row = cursor.fetchone()
            return row[0] if row else None
    finally:
        connection.close()


def attach_item_image(item_id: int, user_id: int, storage_key: str, content_type: str, size: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT image_path FROM items
                WHERE item_id = %s AND user_id = %s AND status = 'ACTIVE'
                FOR UPDATE
            """, (item_id, user_id))
            existing = cursor.fetchone()
            if not existing:
                raise PermissionError("Item not found, not owned by you, or no longer active")
            cursor.execute("""
                UPDATE items SET image_path = %s, image_content_type = %s, image_size = %s
                WHERE item_id = %s AND user_id = %s AND status = 'ACTIVE'
                RETURNING item_id, image_content_type, image_size
            """, (storage_key, content_type, size, item_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise PermissionError("Item not found, not owned by you, or no longer active")
        connection.commit()
        return {"item_id": row[0], "image_url": f"/api/items/{row[0]}/image", "content_type": row[1], "size": row[2],
                "_previous_storage_key": existing[0]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_item_image_upload_allowed(item_id: int, user_id: int):
    """Check ownership and lifecycle before writing an uploaded image to disk."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM items
                WHERE item_id = %s AND user_id = %s AND status = 'ACTIVE'
            """, (item_id, user_id))
            if not cursor.fetchone():
                raise PermissionError("Item not found, not owned by you, or no longer active")
    finally:
        connection.close()


def image_storage_key_is_referenced(storage_key: str) -> bool:
    """Return whether any item still points at this opaque storage key."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM items WHERE image_path = %s LIMIT 1", (storage_key,))
            return cursor.fetchone() is not None
    finally:
        connection.close()


def get_item_image(item_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            # Report photos are public only while their report is eligible for
            # public discovery. Resolved/closed records no longer expose media.
            cursor.execute("""
                SELECT image_path, image_content_type
                FROM items
                WHERE item_id = %s AND status IN ('ACTIVE', 'HANDOVER_IN_PROGRESS')
            """, (item_id,))
            row = cursor.fetchone()
            return {"storage_key": row[0], "content_type": row[1]} if row and row[0] else None
    finally:
        connection.close()


def resolve_match_for_handover(match_id: int, user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            # Lock shared lifecycle rows in match-then-item order, matching the
            # order used by chat acceptance.  The status check happens while
            # those locks are held, so resolution cannot race a stale read.
            cursor.execute("""
                SELECT m.match_id, m.lost_item_id, m.found_item_id,
                       m.status, l.status, f.status
                FROM matches m
                JOIN items l ON l.item_id = m.lost_item_id
                JOIN items f ON f.item_id = m.found_item_id
                WHERE m.match_id = %s AND (%s IN (l.user_id, f.user_id))
                FOR UPDATE OF m, l, f
            """, (match_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise PermissionError("Only a recovery participant can resolve this match")
            if row[3] != "PENDING" or row[4] not in ("ACTIVE", "HANDOVER_IN_PROGRESS") or row[5] not in ("ACTIVE", "HANDOVER_IN_PROGRESS"):
                raise ValueError("This match is no longer eligible for resolution")
            cursor.execute("UPDATE items SET status = 'RESOLVED', resolved_at = CURRENT_TIMESTAMP WHERE item_id IN (%s, %s)", (row[1], row[2]))
            cursor.execute("UPDATE matches SET status = 'RESOLVED' WHERE match_id = %s AND status = 'PENDING'", (match_id,))
        connection.commit()
        return {"match_id": match_id, "status": "RESOLVED"}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_item(item_id, user_id, item_name, category, description, item_date, location):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE items SET item_name = %s, category = %s, description = %s,
                    item_date = %s, location = %s
                WHERE item_id = %s AND user_id = %s
                RETURNING item_id, user_id, item_type, item_name, category, description,
                          item_date, location, status, created_at
            """, (item_name, category, description, item_date, location, item_id, user_id))
            item = cursor.fetchone()
            if not item:
                raise PermissionError("You do not own this item or it does not exist")
        connection.commit()
        return {"item_id": item[0], "user_id": item[1], "item_type": item[2],
                "item_name": item[3], "category": item[4], "description": item[5],
                "item_date": item[6], "location": item[7], "status": item[8],
                "created_at": item[9]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_item(item_id: int, user_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM items WHERE item_id = %s AND user_id = %s RETURNING item_id", (item_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise PermissionError("You do not own this item or it does not exist")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
