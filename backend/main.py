
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import logging
import os
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from database import get_connection
from auth import create_access_token, create_user, authenticate_user
from chat import (
    close_conversation,
    block_conversation_participant,
    create_chat_request,
    get_messages,
    list_chat_requests,
    list_conversations,
    respond_to_chat_request,
    report_conversation_participant,
    send_message,
)
from security import get_current_user_id
from detection import DEFAULT_CONFIDENCE, DetectionUnavailableError, InvalidImageError, detect_image, read_upload_limited
from notifications import get_notifications, mark_notification_read
from rate_limit import sensitive_rate_limit
from items import (
    create_lost_item,
    create_found_item,
    get_lost_items,
    get_found_items,
    get_item_owner,
    update_item,
    delete_item,
    attach_item_image,
    ensure_item_image_upload_allowed,
    image_storage_key_is_referenced,
    get_item_image,
    resolve_match_for_handover,
)
from matching import find_matches_for_lost_item, get_matches_for_item, refresh_matches_for_item
from claims import (
    ClaimConflictError,
    create_claim,
    create_claim_for_found_item,
    get_claims_for_user,
    update_claim_status,
)
from storage import get_report_image, save_report_image
from email_notifications import (
    send_chat_accepted_email,
    send_chat_request_email,
    send_claim_decision_email,
    send_new_message_email,
)

logger = logging.getLogger(__name__)


MAX_JSON_BODY_BYTES = 64 * 1024
MAX_MULTIPART_BODY_BYTES = 8 * 1024 * 1024


class RequestBodyLimitMiddleware:
    """Bound JSON and multipart bodies before Starlette parses them.

    The middleware buffers only valid bodies up to the selected limit, then
    replays the original ASGI request events to downstream handlers. An
    oversized body is rejected as soon as the received bytes cross the limit;
    Content-Length is deliberately treated as advisory and never trusted.
    """

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _limit_for(scope):
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_type = headers.get(b"content-type", b"").strip().lower()
        if content_type.startswith(b"application/json"):
            return MAX_JSON_BODY_BYTES
        if content_type.startswith(b"multipart/"):
            return MAX_MULTIPART_BODY_BYTES
        return None

    @staticmethod
    async def _reject(send):
        body = b'{"detail":"Request body is too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        buffered_events = []
        total = 0
        while True:
            event = await receive()
            if event.get("type") == "http.disconnect":
                return
            if event.get("type") != "http.request":
                buffered_events.append(event)
                if not event.get("more_body", False):
                    break
                continue
            body = event.get("body", b"")
            total += len(body)
            if total > limit:
                await self._reject(send)
                return
            buffered_events.append(event)
            if not event.get("more_body", False):
                break

        async def replay_receive():
            if buffered_events:
                return buffered_events.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


app = FastAPI(
    title="GoodFind API",
    description="Backend API for the GoodFind lost and found platform",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestBodyLimitMiddleware)


# ============================================================
# REQUEST MODELS
# ============================================================

class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(RequestModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)


class LostItemRequest(RequestModel):
    item_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    item_date: str = Field(min_length=1, max_length=10)
    location: str = Field(min_length=1, max_length=255)
    detection_labels: list[str] = Field(default_factory=list, max_length=20)


class FoundItemRequest(RequestModel):
    item_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    item_date: str = Field(min_length=1, max_length=10)
    location: str = Field(min_length=1, max_length=255)
    detection_labels: list[str] = Field(default_factory=list, max_length=20)


class ClaimStatusRequest(RequestModel):
    status: str = Field(min_length=1, max_length=20)


class ItemUpdateRequest(RequestModel):
    item_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    item_date: str = Field(min_length=1, max_length=10)
    location: str = Field(min_length=1, max_length=255)


class ChatRequestCreate(RequestModel):
    match_id: int


class ChatRequestResponse(RequestModel):
    accept: bool


class MessageCreate(RequestModel):
    content: str = Field(min_length=1, max_length=2000)


class AbuseReportCreate(RequestModel):
    reason: str = Field(min_length=1, max_length=500)


# ============================================================
# BASIC ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Welcome to GoodFind API",
        "status": "running",
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "GoodFind backend",
    }


@app.get("/api/database/health")
def database_health():
    connection = None

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

        return {
            "status": "connected",
            "database": "goodfind",
            "test": result[0],
        }

    except Exception as error:
        return {
            "status": "error",
            "message": "Database connection unavailable",
        }

    finally:
        if connection:
            connection.close()


# ============================================================
# AUTH
# ============================================================

@app.post("/api/auth/register", dependencies=[Depends(sensitive_rate_limit)])
def register_user(request: RegisterRequest):
    try:
        user = create_user(
            request.name,
            request.email,
            request.password,
        )

        return {
            "message": "Registration successful",
            "user": user,
            "access_token": create_access_token(user["user_id"]),
            "token_type": "bearer",
        }

    except Exception as error:
        error_message = str(error)

        if "duplicate key" in error_message.lower():
            raise HTTPException(
                status_code=409,
                detail="Email already registered",
            )

        raise HTTPException(
            status_code=500,
            detail="Registration failed",
        )


@app.post("/api/auth/login", dependencies=[Depends(sensitive_rate_limit)])
def login_user(request: LoginRequest):
    user = authenticate_user(
        request.email,
        request.password,
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return {
        "message": "Login successful",
        "user": user,
        "access_token": create_access_token(user["user_id"]),
        "token_type": "bearer",
    }


# ============================================================
# LOST ITEMS
# ============================================================

@app.post("/api/items/lost")
def report_lost_item(request: LostItemRequest, user_id: int = Depends(get_current_user_id)):
    try:
        item = create_lost_item(
            user_id,
            request.item_name,
            request.category,
            request.description,
            request.item_date,
            request.location,
            request.detection_labels,
        )

        return {
            "message": "Lost item reported successfully",
            "item": item,
        }

    except Exception as error:
        logger.error("Failed to create lost item", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to report lost item",
        )


@app.get("/api/items/lost")
def get_lost_items_api(
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    location: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    try:
        items, total = get_lost_items(search=search, category=category, location=location,
                                      status=status, limit=page_size, offset=(page - 1) * page_size)

        return {
            "count": len(items), "total": total, "page": page, "page_size": page_size,
            "items": items,
        }

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        logger.error("Failed to retrieve lost items", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve lost items",
        )


# ============================================================
# FOUND ITEMS
# ============================================================

@app.post("/api/items/found")
def report_found_item(request: FoundItemRequest, user_id: int = Depends(get_current_user_id)):
    try:
        item = create_found_item(
            user_id,
            request.item_name,
            request.category,
            request.description,
            request.item_date,
            request.location,
            request.detection_labels,
        )

        return {
            "message": "Found item reported successfully",
            "item": item,
        }

    except Exception as error:
        logger.error("Failed to create found item", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to report found item",
        )


@app.get("/api/items/found")
def get_found_items_api(
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    location: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    try:
        items, total = get_found_items(search=search, category=category, location=location,
                                       status=status, limit=page_size, offset=(page - 1) * page_size)

        return {
            "count": len(items), "total": total, "page": page, "page_size": page_size,
            "items": items,
        }

    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    except Exception as error:
        logger.error("Failed to retrieve found items", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve found items",
        )


@app.post("/api/items/{item_id}/image", status_code=201)
async def upload_item_image(item_id: int, image: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    """Persist a validated photo after its report is created; no client filename is stored."""
    saved = None
    attached_to_item = False
    previous_storage_key = None
    try:
        ensure_item_image_upload_allowed(item_id, user_id)
        image_bytes = await read_upload_limited(image)
        saved = save_report_image(image_bytes, image.content_type)
        attached = attach_item_image(item_id, user_id, **saved)
        previous_storage_key = attached.pop("_previous_storage_key", None)
        attached_to_item = True
        return {"image": attached}
    except InvalidImageError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    finally:
        if saved and not attached_to_item:
            # If attachment failed, remove only the file just created by this
            # request.  The opaque key and traversal-safe resolver prevent
            # cleanup from targeting an existing or unrelated file.
            try:
                get_report_image(saved["storage_key"]).unlink(missing_ok=True)
            except (FileNotFoundError, OSError):
                pass
        elif previous_storage_key and previous_storage_key != saved["storage_key"]:
            # attach_item_image commits before returning the previous key. Only
            # remove it when no item still references it.
            try:
                if not image_storage_key_is_referenced(previous_storage_key):
                    get_report_image(previous_storage_key).unlink(missing_ok=True)
            except (FileNotFoundError, OSError):
                pass
        await image.close()


@app.get("/api/items/{item_id}/image")
def get_item_image_api(item_id: int):
    """Serve only a server-resolved, opaque photo reference; storage paths are never exposed."""
    image = get_item_image(item_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        return FileResponse(get_report_image(image["storage_key"]), media_type=image["content_type"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")


# ============================================================
# MATCHING
# ============================================================

def require_item_owner(item_id: int, user_id: int):
    if get_item_owner(item_id) != user_id:
        raise HTTPException(status_code=403, detail="You do not own this item")


# ============================================================
# OBJECT DETECTION
# ============================================================

@app.post("/api/detections", dependencies=[Depends(sensitive_rate_limit)])
async def detect_objects_api(
    image: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """Run cached YOLO inference in memory; image bytes are never persisted."""
    try:
        image_bytes = await read_upload_limited(image)
        detections = detect_image(image_bytes, image.content_type)
        return {"detections": detections, "confidence_threshold": DEFAULT_CONFIDENCE}
    except InvalidImageError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except DetectionUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error))
    finally:
        await image.close()


@app.put("/api/items/{item_id}")
def update_item_api(item_id: int, request: ItemUpdateRequest, user_id: int = Depends(get_current_user_id)):
    try:
        return {"item": update_item(item_id, user_id, request.item_name, request.category,
                                     request.description, request.item_date, request.location)}
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))


@app.delete("/api/items/{item_id}", status_code=204)
def delete_item_api(item_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        delete_item(item_id, user_id)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))


@app.post("/api/matches/lost/{lost_item_id}")
def match_lost_item(lost_item_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        require_item_owner(lost_item_id, user_id)
        matches = find_matches_for_lost_item(lost_item_id)

        return {
            "lost_item_id": lost_item_id,
            "count": len(matches),
            "matches": matches,
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error("Failed to find matches", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to find matches",
        )


@app.post("/api/matches/found/{found_item_id}")
def match_found_item(found_item_id: int, user_id: int = Depends(get_current_user_id)):
    """Refresh suggestions for a found report without changing the legacy lost route."""
    try:
        require_item_owner(found_item_id, user_id)
        matches = refresh_matches_for_item(found_item_id)
        return {"found_item_id": found_item_id, "count": len(matches), "matches": matches}
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Failed to find matches", extra={"error_type": type(error).__name__})
        raise HTTPException(status_code=500, detail="Failed to find matches")


@app.post("/api/items/{item_id}/matches/refresh")
def refresh_item_matches(item_id: int, user_id: int = Depends(get_current_user_id)):
    """Explicit owner-only refresh for either kind of active report."""
    try:
        require_item_owner(item_id, user_id)
        matches = refresh_matches_for_item(item_id)
        return {"item_id": item_id, "count": len(matches), "matches": matches}
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Failed to refresh matches", extra={"error_type": type(error).__name__})
        raise HTTPException(status_code=500, detail="Failed to refresh matches")


@app.get("/api/items/{item_id}/matches")
def get_item_matches(item_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        require_item_owner(item_id, user_id)
        matches = get_matches_for_item(item_id)

        return {
            "item_id": item_id,
            # Retained for existing lost-report clients that used the original response shape.
            "lost_item_id": item_id,
            "count": len(matches),
            "matches": matches,
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error("Failed to retrieve matches", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve matches",
        )


@app.post("/api/matches/{match_id}/resolve")
def resolve_match_api(match_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return {"match": resolve_match_for_handover(match_id, user_id)}
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))


# ============================================================
# CLAIMS
# ============================================================

@app.post("/api/claims/{match_id}")
def create_claim_api(
    match_id: int,
    user_id: int = Depends(get_current_user_id),
):
    try:
        claim = create_claim(
            match_id,
            user_id,
        )

        return {
            "message": "Claim request submitted successfully" if claim.get("created") else "Your claim is already pending review",
            "claim": claim,
            "already_pending": claim.get("already_pending", False),
        }

    except ClaimConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))

    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        logger.error("Failed to create claim", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to create claim",
        )


@app.post("/api/claims/found/{found_item_id}")
def create_claim_for_found_item_api(
    found_item_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """Claim a public found listing using the caller's best persisted lost-item match."""
    try:
        claim = create_claim_for_found_item(found_item_id, user_id)
        return {
            "message": "Claim request submitted successfully" if claim.get("created") else "Your claim is already pending review",
            "claim": claim,
            "already_pending": claim.get("already_pending", False),
        }
    except ClaimConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        logger.error("Failed to create claim from found item", extra={"error_type": type(error).__name__})
        raise HTTPException(status_code=500, detail="Failed to create claim")


@app.get("/api/claims")
def get_user_claims_api(user_id: int = Depends(get_current_user_id)):
    try:
        claims = get_claims_for_user(user_id)

        return {
            "count": len(claims),
            "claims": claims,
        }

    except Exception as error:
        logger.error("Failed to retrieve claims", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve claims",
        )


@app.put("/api/claims/{claim_id}")
def update_claim_api(
    claim_id: int,
    request: ClaimStatusRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    try:
        claim = update_claim_status(
            claim_id,
            user_id,
            request.status,
        )
        queue_email(background_tasks, send_claim_decision_email, claim["claimant_user_id"], claim["status"])
        for competing_claimant_id in claim.pop("_email_rejected_claimant_ids", []):
            queue_email(background_tasks, send_claim_decision_email, competing_claimant_id, "REJECTED")

        return {
            "message": "Claim updated successfully",
            "claim": claim,
        }

    except ClaimConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))

    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        logger.error("Failed to update claim", extra={"error_type": type(error).__name__})

        raise HTTPException(
            status_code=500,
            detail="Failed to update claim",
        )


# ============================================================
# PRIVATE CHAT (polling-based real-time delivery)
# ============================================================

def chat_error(error: Exception):
    if isinstance(error, PermissionError):
        raise HTTPException(status_code=403, detail=str(error))
    if isinstance(error, ValueError):
        raise HTTPException(status_code=400, detail=str(error))
    raise HTTPException(status_code=500, detail="Chat operation failed")


def queue_email(background_tasks: BackgroundTasks, sender, *args):
    """Queue only post-commit, best-effort email work; never affect the API response."""
    background_tasks.add_task(sender, *args)


@app.post("/api/chat/requests", status_code=201)
def create_chat_request_api(
    request: ChatRequestCreate,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    try:
        chat_request = create_chat_request(request.match_id, user_id)
        should_notify = chat_request.pop("_notify_recipient", False)
        item_name = chat_request.pop("_email_item_name", None)
        if should_notify:
            queue_email(background_tasks, send_chat_request_email, chat_request["recipient_user_id"], item_name)
        return {"request": chat_request}
    except Exception as error:
        chat_error(error)


@app.put("/api/chat/requests/{request_id}")
def respond_to_chat_request_api(
    request_id: int,
    request: ChatRequestResponse,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    try:
        chat_request, conversation = respond_to_chat_request(
            request_id, user_id, request.accept
        )
        if request.accept:
            queue_email(background_tasks, send_chat_accepted_email, chat_request["requester_user_id"])
        return {"request": chat_request, "conversation": conversation}
    except Exception as error:
        chat_error(error)


@app.get("/api/chat/requests")
def list_chat_requests_api(user_id: int = Depends(get_current_user_id)):
    try:
        return {"requests": list_chat_requests(user_id)}
    except Exception as error:
        chat_error(error)


@app.get("/api/notifications")
def get_notifications_api(user_id: int = Depends(get_current_user_id)):
    return {"notifications": get_notifications(user_id)}


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read_api(notification_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return {"notification": mark_notification_read(notification_id, user_id)}
    except PermissionError as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.get("/api/chat/conversations")
def list_conversations_api(user_id: int = Depends(get_current_user_id)):
    try:
        return {"conversations": list_conversations(user_id)}
    except Exception as error:
        chat_error(error)


@app.get("/api/chat/conversations/{conversation_id}/messages")
def get_messages_api(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
):
    try:
        return {"messages": get_messages(conversation_id, user_id)}
    except Exception as error:
        chat_error(error)


@app.post("/api/chat/conversations/{conversation_id}/messages", status_code=201)
def send_message_api(
    conversation_id: int,
    request: MessageCreate,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    try:
        message = send_message(conversation_id, user_id, request.content)
        recipient_user_id = message.pop("_notify_recipient_user_id", None)
        if recipient_user_id is not None:
            queue_email(background_tasks, send_new_message_email, recipient_user_id, conversation_id)
        return {"message": message}
    except Exception as error:
        chat_error(error)


@app.post("/api/chat/conversations/{conversation_id}/close")
def close_conversation_api(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
):
    try:
        return {"conversation": close_conversation(conversation_id, user_id)}
    except Exception as error:
        chat_error(error)


@app.post("/api/chat/conversations/{conversation_id}/block")
def block_participant_api(conversation_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return {"block": block_conversation_participant(conversation_id, user_id)}
    except Exception as error:
        chat_error(error)


@app.post("/api/chat/conversations/{conversation_id}/reports", status_code=201)
def report_participant_api(
    conversation_id: int,
    request: AbuseReportCreate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        return {"report": report_conversation_participant(conversation_id, user_id, request.reason)}
    except Exception as error:
        chat_error(error)
