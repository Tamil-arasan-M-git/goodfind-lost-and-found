# GOODFIND

GOODFIND is a privacy-first lost-and-found application built with React, FastAPI, and PostgreSQL.

## Architecture and feature inventory

- React/Vite client for public discovery, authenticated reporting, claims, and private messaging.
- FastAPI API with signed bearer tokens, ownership checks, PostgreSQL queries, and parameterized SQL.
- PostgreSQL stores reports, matches, claims, conversations, moderation actions, detector labels, and notifications. Report photographs, when attached, are stored separately using opaque server-generated names.
- GoodFind's custom YOLOv8n model supplies optional labels for `mobile_phone`, `backpack_bag`, `keys`, `wallet_purse`, and `water_bottle`. It does not identify exact possessions or decide ownership.

## Setup

1. Create a PostgreSQL database, then apply [`database/schema.sql`](database/schema.sql) only for a new empty database. Existing deployments must use the ordered, idempotent files in [`database/migrations`](database/migrations) instead; do not rerun the baseline schema against populated data.
2. Set the following environment variables before running FastAPI:

   - `DATABASE_URL`: a Psycopg/PostgreSQL connection string, for example `postgresql://goodfind_app:password@localhost:5432/goodfind`.
   - `AUTH_SECRET`: a long random secret used to sign 24-hour bearer tokens. Never commit it.
   - `YOLO_MODEL_PATH` (optional): local path to the custom GoodFind model. By default the API loads `backend/goodfind_best.pt`; it does not download or fall back to pretrained weights. If the file is missing or its labels do not match the supported mapping, detection returns a clear `503` response.
   - `VITE_API_BASE_URL` (optional, frontend build-time): browser API origin. Leave it unset for the local default (`http://127.0.0.1:8000`); set it to the deployed API origin before building a deployed frontend.
   - `CORS_ORIGINS` (optional): comma-separated browser origins. The default permits only the local Vite origins.
   - `RATE_LIMIT_WINDOW_SECONDS` and `RATE_LIMIT_MAX_REQUESTS` (optional): in-process limits for registration, login, and image analysis. Defaults are 60 seconds and 20 requests. The API also rejects JSON bodies over 64 KiB and multipart bodies over 8 MiB before FastAPI parsing; these application limits are not environment-configurable.
   - `ITEM_IMAGE_STORAGE_DIR` (optional): persistent local directory for validated report photographs; defaults to `item-images` under the backend working directory.
   - `EMAIL_NOTIFICATIONS_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_APP_PASSWORD`, `EMAIL_FROM`, and `FRONTEND_BASE_URL` (optional): Gmail SMTP settings. Email stays disabled until explicitly enabled and completely configured; in-app notifications always continue independently.

3. Install backend dependencies: `..\\venv\\Scripts\\python -m pip install -r requirements.txt`.
4. For an existing database, create and verify a backup before applying migrations. On
   Windows PowerShell, with `DATABASE_URL` already set in the process environment:

   ```powershell
   New-Item -ItemType Directory -Force database/backups | Out-Null
   $backup = "database/backups/goodfind-pre-migration-$(Get-Date -Format yyyyMMdd-HHmmss).dump"
   pg_dump --format=custom --file $backup --dbname=$env:DATABASE_URL
   pg_restore --list $backup
   ```

   `database/backups/` is ignored by Git. Never overwrite a backup or run the
   baseline schema against a populated database.

5. Apply the ordered migrations with fail-fast error handling:

   ```powershell
   psql --set ON_ERROR_STOP=1 --dbname=$env:DATABASE_URL --file database/migrations/001_detection_labels.sql
   psql --set ON_ERROR_STOP=1 --dbname=$env:DATABASE_URL --file database/migrations/002_private_chat.sql
   psql --set ON_ERROR_STOP=1 --dbname=$env:DATABASE_URL --file database/migrations/003_notifications.sql
   psql --set ON_ERROR_STOP=1 --dbname=$env:DATABASE_URL --file database/migrations/004_item_images_and_resolution.sql
   ```

   The project currently has no migration-history table. The scripts are safe to
   re-run only when their objects already exactly match the expected definitions;
   `IF NOT EXISTS` does not repair partially created tables or missing constraints.
   Keep an operational record of applied migrations and inspect the schema before
   retrying a failed migration.

6. Start the API from `backend` using the project virtual environment: `..\\venv\\Scripts\\python -m uvicorn main:app --reload`.
6. Start the frontend from `frontend`: `npm run dev`.

## Object detection

Authenticated reporters can submit a JPEG, PNG, or WebP image up to 5 MB to `POST /api/detections` as the `image` multipart field. Images are decoded and analyzed only in memory, then discarded. The cached custom GoodFind model returns labels, confidence scores, and pixel bounding boxes only for `mobile_phone`, `backpack_bag`, `keys`, `wallet_purse`, and `water_bottle`. Suggestions are optional and may be incomplete or incorrect; a returned suggestion is never proof of ownership.

When a reporter keeps a suggested label, only that label is stored as report metadata. Label overlap contributes at most 5% of the existing matching score. It never rejects a report, proves that items are identical, or authorizes a claim.

## Discovery and notifications

Public lost and found listings support `search`, `category`, `location`, `status`, `page`, and `page_size` query parameters. Their responses deliberately omit owner IDs. Authenticated users receive persisted in-app notifications for chat requests, accepted chat requests, claim requests, and claim decisions. Notifications can be marked read only by their owner.

## Matching

GoodFind compares active reports in both directions: submitting a lost report refreshes eligible found reports, and submitting a found report refreshes eligible lost reports. An owner can explicitly refresh either report with `POST /api/items/{item_id}/matches/refresh`; `GET /api/items/{item_id}/matches` only retrieves already persisted active suggestions and does not calculate or write matches.

The deterministic score is a ranking heuristic, not a probability or proof of ownership. Before penalties, its weights sum to 1.0: category equality 19%, normalized name similarity 43%, normalized description similarity 14%, normalized location similarity 9.5%, date proximity 9.5%, and detection-label Jaccard overlap 5%. Text comparison lowercases, normalizes punctuation and repeated whitespace, then blends character and token overlap. Missing values contribute zero, never a positive match. Explicit conflicting item types, conflicting colours, and very low name similarity apply documented penalties. Only scores of at least 40 are suggested.

Each result includes a safe `explanation` describing the computed components, missing information, and conflicting evidence. Results never include owner identities, emails, phone numbers, storage keys, or private messages. Active suggestions exclude pairs where either participant has blocked the other. Detection labels remain optional metadata; GoodFind does not compare image pixels, bounding boxes, or image embeddings.

Run the synthetic, non-production comparison set from `backend` with `..\\venv\\Scripts\\python matching_evaluation.py`. It compares the pre-upgrade formula with the current heuristic for representative positives and hard negatives; it is not real-world accuracy validation.

## Testing and troubleshooting

Run backend tests from `backend`: `..\\venv\\Scripts\\python -m unittest discover -v`. Run frontend checks from `frontend`: `npm run lint` and `npm run build`.

If a database script reports `DATABASE_URL environment variable is required`, set it in the process environment before starting FastAPI; the application intentionally has no development default credential. If detection returns `503`, verify that `backend/goodfind_best.pt` exists and that `YOLO_MODEL_PATH`, when set, points to compatible custom weights. Production deployments should use HTTPS, a non-default CORS origin list, a strong `AUTH_SECRET`, managed PostgreSQL backups, an upstream request-body limit for JSON and multipart traffic, and edge/proxy rate limiting for login and upload endpoints. The built-in body and rate limiters are deliberately not a replacement for gateway controls in multi-worker deployments.

## Private chat

Only the owner of a lost item can request a chat for an existing match. The found-item owner can accept or decline. Acceptance creates a two-person conversation with generated GoodFind aliases; messages are delivered using polling every eight seconds in this initial implementation. The service does not claim end-to-end encryption.

Every item creation, item mutation, match generation, claim operation, conversation, message, and close operation uses the signed bearer token rather than a client-supplied user ID. Public item lists do not require login.

Participants can block or report the other participant from a conversation. Blocking prevents either participant from sending further messages in that conversation and prevents the blocked pair from creating a new chat request. Reports are participant-only, require a 1–500 character reason, are deduplicated per conversation, and are not exposed through the public API. Closing a conversation is idempotent and permanently rejects new messages.

## Gmail email notifications

GoodFind can send best-effort transactional emails for a new chat request, a newly persisted private message, and claim decisions. Email is optional; a delivery failure never rolls back a chat, message, claim decision, or the corresponding in-app notification.

1. Enable two-step verification on the Gmail account that will send GoodFind notifications.
2. Create a Google App Password in that account's Google Account security settings, using a name such as `GoodFind SMTP`. Google shows the generated value only once.
3. Set the following values in the backend process environment (or a local, ignored `.env` file only if the process manager loads it):

   ```text
   EMAIL_NOTIFICATIONS_ENABLED=true
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-gmail-address@example.com
   SMTP_APP_PASSWORD=your-google-app-password
   EMAIL_FROM=GoodFind <your-gmail-address@example.com>
   FRONTEND_BASE_URL=http://127.0.0.1:5173
   EMAIL_MESSAGE_COOLDOWN_SECONDS=300
   ```

4. Restart the FastAPI backend. Do not put these values in Vite variables, commit a `.env` file, or use the Gmail account password.

Emails contain only a generic workflow notice and a navigation link—never message text, contact details, tokens, or claim evidence. Requests are emailed only when a new request is created, and messages have a configurable, process-local cooldown per recipient and conversation. The current schema has no durable email-delivery event ledger, so cooldown/deduplication does not survive backend restarts or coordinate across multiple workers. A migration would be required for that stronger guarantee.

## Claims

Potential-match cards keep two separate actions: **Submit claim** records an ownership claim for the matched lost/found reports, while **Start chat** creates a private-chat request. A claimant must own the matched lost report; they cannot claim their own found report. Claims are allowed only while the match and both reports are active. Repeating a pending claim is idempotent and does not send another notification; accepted and rejected claims cannot be reopened.

Only the found-item owner can accept or reject a pending claim. Accepting a claim does not mark an item recovered: the existing explicit handover-resolution action remains the only recovery confirmation. Acceptance rejects pending competing claims for the same found item and enables the claimant to request private chat through the existing anonymous chat workflow.
