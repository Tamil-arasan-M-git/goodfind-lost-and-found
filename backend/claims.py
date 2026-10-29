from database import get_connection
from notifications import insert_notification


class ClaimConflictError(ValueError):
    """The requested claim transition conflicts with an existing final state."""


def find_claim_match_for_found_item(found_item_id, claimant_user_id):
    """Return the highest-ranked active persisted match for this user's lost reports."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.match_id
                FROM matches m
                JOIN items l ON l.item_id = m.lost_item_id
                JOIN items f ON f.item_id = m.found_item_id
                WHERE m.found_item_id = %s
                  AND l.user_id = %s
                  AND m.status = 'PENDING'
                  AND l.status = 'ACTIVE'
                  AND f.status = 'ACTIVE'
                ORDER BY m.similarity_score DESC, m.match_id ASC
                LIMIT 1
                """,
                (found_item_id, claimant_user_id),
            )
            row = cursor.fetchone()
            return row[0] if row else None
    finally:
        connection.close()


def create_claim_for_found_item(found_item_id, claimant_user_id):
    match_id = find_claim_match_for_found_item(found_item_id, claimant_user_id)
    if match_id is None:
        raise ValueError("No eligible matching lost report was found for this item")
    return create_claim(match_id, claimant_user_id)


def _claim_payload(row, *, created=None, competing_claims_rejected=0):
    claim = {
        "claim_id": row[0], "match_id": row[1], "claimant_user_id": row[2],
        "found_item_owner_id": row[3], "status": row[4], "created_at": row[5],
    }
    if created is not None:
        claim["created"] = created
        claim["already_pending"] = not created
    if competing_claims_rejected:
        claim["competing_claims_rejected"] = competing_claims_rejected
    return claim


def create_claim(match_id, claimant_user_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    m.match_id,
                    m.lost_item_id,
                    m.found_item_id,
                    f.user_id,
                    m.status,
                    l.status,
                    f.status
                FROM matches m
                JOIN items l
                    ON l.item_id = m.lost_item_id
                JOIN items f
                    ON f.item_id = m.found_item_id
                WHERE m.match_id = %s
                FOR UPDATE OF m, l, f
                """,
                (match_id,),
            )

            match = cursor.fetchone()

            if match is None:
                raise ValueError("Match not found")

            found_item_owner_id = match[3]

            cursor.execute(
                """
                SELECT user_id
                FROM items
                WHERE item_id = %s
                  AND user_id = %s
                """,
                (
                    match[1],
                    claimant_user_id,
                ),
            )

            lost_item_owner = cursor.fetchone()

            if lost_item_owner is None:
                raise PermissionError(
                    "You are not the owner of this lost item"
                )

            if found_item_owner_id == claimant_user_id:
                raise ValueError("You cannot submit a claim for your own found item")

            if match[4] != "PENDING" or match[5] != "ACTIVE" or match[6] != "ACTIVE":
                raise ClaimConflictError("This match is no longer eligible for claims")

            cursor.execute(
                """
                SELECT claim_id, match_id, claimant_user_id, found_item_owner_id,
                       status, created_at
                FROM claims
                WHERE match_id = %s AND claimant_user_id = %s
                FOR UPDATE
                """,
                (match_id, claimant_user_id),
            )
            existing = cursor.fetchone()
            if existing:
                if existing[4] == "PENDING":
                    connection.commit()
                    return _claim_payload(existing, created=False)
                raise ClaimConflictError(
                    f"This claim has already been {existing[4].lower()} and cannot be reopened"
                )

            cursor.execute(
                """
                SELECT c.claim_id
                FROM claims c
                JOIN matches existing_match ON existing_match.match_id = c.match_id
                WHERE existing_match.found_item_id = %s AND c.status = 'ACCEPTED'
                LIMIT 1
                """,
                (match[2],),
            )
            if cursor.fetchone():
                raise ClaimConflictError("This found item already has an accepted claim")

            cursor.execute(
                """
                INSERT INTO claims
                (
                    match_id,
                    claimant_user_id,
                    found_item_owner_id
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (match_id, claimant_user_id)
                DO NOTHING
                RETURNING
                    claim_id,
                    match_id,
                    claimant_user_id,
                    found_item_owner_id,
                    status,
                    created_at
                """,
                (
                    match_id,
                    claimant_user_id,
                    found_item_owner_id,
                ),
            )

            claim = cursor.fetchone()
            if claim is None:
                # A concurrent insert can win after the earlier row-lock lookup.
                cursor.execute(
                    """
                    SELECT claim_id, match_id, claimant_user_id, found_item_owner_id,
                           status, created_at
                    FROM claims
                    WHERE match_id = %s AND claimant_user_id = %s
                    """,
                    (match_id, claimant_user_id),
                )
                existing = cursor.fetchone()
                if not existing:
                    raise RuntimeError("Claim creation did not return a claim")
                if existing[4] == "PENDING":
                    connection.commit()
                    return _claim_payload(existing, created=False)
                raise ClaimConflictError(
                    f"This claim has already been {existing[4].lower()} and cannot be reopened"
                )
            insert_notification(
                cursor, claim[3], "claim_request",
                "A user submitted a claim for an item you found."
            )

            connection.commit()
            return _claim_payload(claim, created=True)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_claims_for_user(user_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    c.claim_id,
                    c.match_id,
                    c.claimant_user_id,
                    c.found_item_owner_id,
                    c.status,
                    c.created_at,

                    l.item_id,
                    l.item_name,
                    l.category,

                    f.item_id,
                    f.item_name,
                    f.category

                FROM claims c

                JOIN matches m
                    ON m.match_id = c.match_id

                JOIN items l
                    ON l.item_id = m.lost_item_id

                JOIN items f
                    ON f.item_id = m.found_item_id

                WHERE
                    c.claimant_user_id = %s
                    OR c.found_item_owner_id = %s

                ORDER BY c.created_at DESC
                """,
                (
                    user_id,
                    user_id,
                ),
            )

            rows = cursor.fetchall()

            claims = []

            for row in rows:
                claims.append(
                    {
                        "claim_id": row[0],
                        "match_id": row[1],
                        "claimant_user_id": row[2],
                        "found_item_owner_id": row[3],
                        "status": row[4],
                        "created_at": row[5],
                        "lost_item": {
                            "item_id": row[6],
                            "item_name": row[7],
                            "category": row[8],
                        },
                        "found_item": {
                            "item_id": row[9],
                            "item_name": row[10],
                            "category": row[11],
                        },
                    }
                )

            return claims

    finally:
        connection.close()


def update_claim_status(claim_id, user_id, status):
    status = status.strip().upper()
    if status not in ("ACCEPTED", "REJECTED"):
        raise ValueError("Invalid claim status")
    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT c.claim_id, c.found_item_owner_id, c.status, m.found_item_id,
                       m.status, l.status, f.status
                FROM claims c
                JOIN matches m ON m.match_id = c.match_id
                JOIN items l ON l.item_id = m.lost_item_id
                JOIN items f ON f.item_id = m.found_item_id
                WHERE c.claim_id = %s
                FOR UPDATE OF c, m, l, f
                """,
                (claim_id,),
            )

            claim = cursor.fetchone()

            if claim is None:
                raise ValueError("Claim not found")

            if claim[1] != user_id:
                raise PermissionError(
                    "Only the found-item owner can respond to this claim"
                )

            if claim[2] != "PENDING":
                raise ClaimConflictError("This claim has already been reviewed")

            if claim[4] != "PENDING" or claim[5] != "ACTIVE" or claim[6] != "ACTIVE":
                raise ClaimConflictError("This claim is no longer eligible for review")

            cursor.execute(
                """
                UPDATE claims
                SET status = %s
                WHERE claim_id = %s AND status = 'PENDING'
                RETURNING
                    claim_id,
                    match_id,
                    claimant_user_id,
                    found_item_owner_id,
                    status,
                    created_at
                """,
                (
                    status,
                    claim_id,
                ),
            )

            row = cursor.fetchone()
            if not row:
                raise ClaimConflictError("This claim has already been reviewed")
            insert_notification(
                cursor, row[2], "claim_status",
                f"Your item claim was {row[4].lower()}."
            )

            competing_claimants = []
            if status == "ACCEPTED":
                cursor.execute(
                    """
                    UPDATE claims competing
                    SET status = 'REJECTED'
                    FROM matches competing_match
                    WHERE competing.match_id = competing_match.match_id
                      AND competing_match.found_item_id = %s
                      AND competing.claim_id <> %s
                      AND competing.status = 'PENDING'
                    RETURNING competing.claimant_user_id
                    """,
                    (claim[3], claim_id),
                )
                competing_claimants = [entry[0] for entry in cursor.fetchall()]
                for claimant_user_id in competing_claimants:
                    insert_notification(
                        cursor, claimant_user_id, "claim_status",
                        "Your item claim was rejected because another claim was accepted."
                    )

            connection.commit()
            payload = _claim_payload(row, competing_claims_rejected=len(competing_claimants))
            # Internal post-commit recipients; the API removes this before responding.
            payload["_email_rejected_claimant_ids"] = competing_claimants
            return payload

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
