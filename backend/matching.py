
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

from database import get_connection


MATCH_WEIGHTS = {
    "category": 0.19,
    "name": 0.43,
    "description": 0.14,
    "location": 0.095,
    "date": 0.095,
    "detection_labels": 0.05,
}
MATCH_THRESHOLD = 40.0
SUPPORTED_CATEGORIES = frozenset({"electronics", "clothing", "documents", "accessories", "books", "other"})
CATEGORY_ALIASES = {"accessory": "accessories", "electronic": "electronics", "book": "books"}
TOKEN_ALIASES = {"purse": "wallet", "wallets": "wallet", "smartphone": "phone", "mobile": "phone", "mobiles": "phone", "phones": "phone", "backpacks": "backpack", "bags": "bag", "keys": "key"}
ITEM_TYPES = {"wallet": "wallet", "phone": "phone", "backpack": "backpack", "bag": "bag", "key": "keys", "bottle": "bottle"}
COLOURS = frozenset({"black", "white", "red", "blue", "green", "yellow", "orange", "purple", "pink", "brown", "grey", "gray", "silver", "gold"})


def normalize_text(value):
    """Normalize comparison inputs only; original database text is unchanged."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def normalize_category(value):
    category = CATEGORY_ALIASES.get(normalize_text(value), normalize_text(value))
    return category if category in SUPPORTED_CATEGORIES else category


def _tokens(value):
    return {TOKEN_ALIASES.get(token, token) for token in normalize_text(value).split()}


def text_similarity(text1, text2):
    """Blend lexical and token evidence without treating missing text as a match."""
    first, second = normalize_text(text1), normalize_text(text2)
    if not first or not second:
        return 0.0
    lexical = SequenceMatcher(None, first, second).ratio()
    first_tokens, second_tokens = _tokens(first), _tokens(second)
    token_score = len(first_tokens & second_tokens) / len(first_tokens | second_tokens)
    return 0.6 * lexical + 0.4 * token_score


def date_similarity(date1, date2):
    if not date1 or not date2:
        return 0.0

    try:
        if isinstance(date1, str):
            date1 = date.fromisoformat(date1)
        if isinstance(date2, str):
            date2 = date.fromisoformat(date2)
    except (TypeError, ValueError):
        return 0.0

    difference = abs((date1 - date2).days)

    if difference == 0:
        return 1.0
    elif difference == 1:
        return 0.8
    elif difference <= 3:
        return 0.5
    elif difference <= 7:
        return 0.2

    return 0.0


def _item_type(value):
    for token in _tokens(value):
        if token in ITEM_TYPES:
            return ITEM_TYPES[token]
    return None


def _colours(*values):
    return set().union(*(_tokens(value) & COLOURS for value in values))


def are_items_compatible(lost_item_name, found_item_name):
    """The score and documented penalties decide compatibility."""
    return True


def detection_label_similarity(lost_labels, found_labels):
    """A small positive hint only; labels never qualify or reject a match."""
    lost = {normalize_text(label) for label in (lost_labels or []) if normalize_text(label)}
    found = {normalize_text(label) for label in (found_labels or []) if normalize_text(label)}
    if not lost or not found:
        return 0.0
    return len(lost & found) / len(lost | found)


def calculate_match_details(lost_item, found_item):
    """Return a bounded heuristic score and the evidence used to calculate it."""
    lost_category = normalize_category(lost_item.get("category"))
    found_category = normalize_category(found_item.get("category"))
    category_score = 1.0 if lost_category and found_category and lost_category == found_category else 0.0

    name_score = text_similarity(
        lost_item.get("item_name"), found_item.get("item_name"),
    )

    description_score = text_similarity(
        lost_item.get("description"), found_item.get("description"),
    )

    location_score = text_similarity(
        lost_item.get("location"), found_item.get("location"),
    )

    date_score = date_similarity(
        lost_item.get("item_date"), found_item.get("item_date"),
    )

    label_score = detection_label_similarity(
        lost_item.get("detection_labels"), found_item.get("detection_labels")
    )

    components = {"category": category_score, "name": name_score, "description": description_score,
                  "location": location_score, "date": date_score, "detection_labels": label_score}
    score = sum(MATCH_WEIGHTS[name] * value for name, value in components.items())
    conflicts = []
    lost_type, found_type = _item_type(lost_item.get("item_name")), _item_type(found_item.get("item_name"))
    if lost_type and found_type and lost_type != found_type:
        score *= 0.55
        conflicts.append("The report names indicate different item types.")
    lost_colours = _colours(lost_item.get("item_name"), lost_item.get("description"))
    found_colours = _colours(found_item.get("item_name"), found_item.get("description"))
    if lost_colours and found_colours and not (lost_colours & found_colours):
        # Explicit, non-overlapping colours are strong contradictory evidence.
        score *= 0.45
        conflicts.append("The reports describe different colours.")
    if name_score < 0.25:
        score *= 0.50
        conflicts.append("The item names have very little similarity.")
    missing = [field for field in ("category", "item_name", "description", "location", "item_date")
               if not normalize_text(lost_item.get(field)) or not normalize_text(found_item.get(field))]
    if not lost_item.get("detection_labels") or not found_item.get("detection_labels"):
        missing.append("detection_labels")
    return {"score": round(max(0.0, min(1.0, score)) * 100, 2), "components": components,
            "explanation": {"disclaimer": "This is a potential match based on report details, not proof of ownership.",
                            "components": {name: round(value * 100, 2) for name, value in components.items()},
                            "category_match": bool(category_score), "date_proximity_score": round(date_score * 100, 2),
                            "label_overlap_score": round(label_score * 100, 2), "conflicts": conflicts,
                            "missing_information": sorted(set(missing))}}


def calculate_match_score(lost_item, found_item):
    return calculate_match_details(lost_item, found_item)["score"]


ITEM_COLUMNS = "item_id, user_id, item_type, item_name, category, description, item_date, location, detection_labels, image_path, status"


def _item_from_row(row, offset=0):
    return {"item_id": row[offset], "user_id": row[offset + 1], "item_type": row[offset + 2],
            "item_name": row[offset + 3], "category": row[offset + 4], "description": row[offset + 5],
            "item_date": row[offset + 6], "location": row[offset + 7], "detection_labels": row[offset + 8],
            "image_path": row[offset + 9], "status": row[offset + 10]}


def _safe_item(item):
    return {"item_name": item["item_name"], "category": item["category"], "description": item["description"],
            "item_date": item["item_date"], "location": item["location"], "detection_labels": item["detection_labels"],
            "image_url": f"/api/items/{item['item_id']}/image" if item["image_path"] else None, "status": item["status"]}


def _match_response(match_id, lost_item, found_item, details, source_type):
    counterpart = found_item if source_type == "LOST" else lost_item
    counterpart_key = "found_item" if source_type == "LOST" else "lost_item"
    return {"match_id": match_id, "lost_item_id": lost_item["item_id"], "found_item_id": found_item["item_id"],
            "similarity_score": details["score"], counterpart_key: _safe_item(counterpart),
            "explanation": details["explanation"]}


def _load_source(cursor, item_id):
    cursor.execute(f"SELECT {ITEM_COLUMNS} FROM items WHERE item_id = %s AND status = 'ACTIVE'", (item_id,))
    row = cursor.fetchone()
    return _item_from_row(row) if row else None


def _load_candidates(cursor, source):
    other_type = "FOUND" if source["item_type"] == "LOST" else "LOST"
    cursor.execute(f"""
        SELECT {ITEM_COLUMNS} FROM items candidate
        WHERE candidate.item_type = %s AND candidate.status = 'ACTIVE'
          AND NOT EXISTS (SELECT 1 FROM user_blocks block
              WHERE (block.blocker_user_id = %s AND block.blocked_user_id = candidate.user_id)
                 OR (block.blocker_user_id = candidate.user_id AND block.blocked_user_id = %s))
        ORDER BY candidate.created_at DESC, candidate.item_id DESC
    """, (other_type, source["user_id"], source["user_id"]))
    return [_item_from_row(row) for row in cursor.fetchall()]


def refresh_matches_for_item(item_id):
    """Calculate and persist eligible suggestions.  The pair uniqueness constraint makes repeats idempotent."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            source = _load_source(cursor, item_id)
            if source is None:
                return []
            matches = []
            for candidate in _load_candidates(cursor, source):
                lost_item, found_item = (source, candidate) if source["item_type"] == "LOST" else (candidate, source)
                details = calculate_match_details(lost_item, found_item)
                if details["score"] < MATCH_THRESHOLD:
                    continue
                cursor.execute("""
                    INSERT INTO matches (lost_item_id, found_item_id, similarity_score)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (lost_item_id, found_item_id)
                    DO UPDATE SET similarity_score = EXCLUDED.similarity_score
                    RETURNING match_id
                """, (lost_item["item_id"], found_item["item_id"], details["score"] / 100))
                matches.append(_match_response(cursor.fetchone()[0], lost_item, found_item, details, source["item_type"]))
        connection.commit()
        return sorted(matches, key=lambda match: (-match["similarity_score"], match["match_id"]))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_matches_for_item(item_id):
    """Read existing active suggestions without recalculating or writing them."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            source = _load_source(cursor, item_id)
            if source is None:
                return []
            column = "lost_item_id" if source["item_type"] == "LOST" else "found_item_id"
            cursor.execute(f"""
                SELECT m.match_id, l.item_id, l.user_id, l.item_type, l.item_name, l.category, l.description,
                       l.item_date, l.location, l.detection_labels, l.image_path, l.status,
                       f.item_id, f.user_id, f.item_type, f.item_name, f.category, f.description,
                       f.item_date, f.location, f.detection_labels, f.image_path, f.status
                FROM matches m JOIN items l ON l.item_id = m.lost_item_id JOIN items f ON f.item_id = m.found_item_id
                WHERE m.{column} = %s AND m.status = 'PENDING' AND l.status = 'ACTIVE' AND f.status = 'ACTIVE'
                  AND NOT EXISTS (SELECT 1 FROM user_blocks block
                      WHERE (block.blocker_user_id = %s AND block.blocked_user_id = CASE WHEN %s = 'LOST' THEN f.user_id ELSE l.user_id END)
                         OR (block.blocker_user_id = CASE WHEN %s = 'LOST' THEN f.user_id ELSE l.user_id END AND block.blocked_user_id = %s))
                ORDER BY m.similarity_score DESC, m.match_id ASC
            """, (item_id, source["user_id"], source["item_type"], source["item_type"], source["user_id"]))
            results = []
            for row in cursor.fetchall():
                lost_item, found_item = _item_from_row(row, 1), _item_from_row(row, 12)
                details = calculate_match_details(lost_item, found_item)
                if details["score"] >= MATCH_THRESHOLD:
                    results.append(_match_response(row[0], lost_item, found_item, details, source["item_type"]))
            return sorted(results, key=lambda match: (-match["similarity_score"], match["match_id"]))
    finally:
        connection.close()


def find_matches_for_lost_item(lost_item_id):
    """Compatibility wrapper retained for existing callers."""
    return refresh_matches_for_item(lost_item_id)
