-- =========================================
-- GOODFIND DATABASE SCHEMA
-- =========================================

-- USERS
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ITEMS
CREATE TABLE items (
    item_id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    item_type VARCHAR(10) NOT NULL
        CHECK (item_type IN ('LOST', 'FOUND')),

    item_name VARCHAR(200) NOT NULL,

    category VARCHAR(100) NOT NULL,

    description TEXT,

    brand VARCHAR(100),

    color VARCHAR(50),

    item_date DATE,

    location VARCHAR(255),

    image_path TEXT,
    image_content_type VARCHAR(30),
    image_size INTEGER,
    resolved_at TIMESTAMP,

    -- Detector labels only; uploaded image bytes are never stored by GOODFIND.
    detection_labels TEXT[] NOT NULL DEFAULT '{}'::TEXT[],

    status VARCHAR(30) DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'HANDOVER_IN_PROGRESS', 'RESOLVED', 'CLOSED')),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- MATCHES
CREATE TABLE matches (
    match_id SERIAL PRIMARY KEY,

    lost_item_id INTEGER NOT NULL
        REFERENCES items(item_id)
        ON DELETE CASCADE,

    found_item_id INTEGER NOT NULL
        REFERENCES items(item_id)
        ON DELETE CASCADE,

    similarity_score DECIMAL(5,4),

    status VARCHAR(30) DEFAULT 'PENDING',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (lost_item_id, found_item_id)
);
-- CLAIM REQUESTS
CREATE TABLE claims (
    claim_id SERIAL PRIMARY KEY,

    match_id INTEGER NOT NULL
        REFERENCES matches(match_id)
        ON DELETE CASCADE,

    claimant_user_id INTEGER NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    found_item_owner_id INTEGER NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    status VARCHAR(30) DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED')),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (match_id, claimant_user_id)
);

-- PRIVATE CHAT
-- A request is tied to a verified lost/found match.  Personal contact details
-- are deliberately not copied into any of these tables.
CREATE TABLE chat_requests (
    request_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    requester_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    recipient_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACCEPTED', 'DECLINED', 'CANCELLED')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    CHECK (requester_user_id <> recipient_user_id),
    UNIQUE (match_id, requester_user_id)
);

CREATE TABLE conversations (
    conversation_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL UNIQUE REFERENCES matches(match_id) ON DELETE CASCADE,
    request_id INTEGER NOT NULL UNIQUE REFERENCES chat_requests(request_id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'CLOSED')),
    closed_at TIMESTAMP,
    closed_by_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE conversation_participants (
    conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    display_alias VARCHAR(80) NOT NULL,
    blocked_at TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id),
    UNIQUE (conversation_id, display_alias)
);

CREATE TABLE messages (
    message_id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    sender_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    content VARCHAR(2000) NOT NULL CHECK (char_length(trim(content)) BETWEEN 1 AND 2000),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX messages_conversation_created_idx
    ON messages (conversation_id, created_at, message_id);

CREATE TABLE user_blocks (
    blocker_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    blocked_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (blocker_user_id, blocked_user_id),
    CHECK (blocker_user_id <> blocked_user_id)
);

CREATE TABLE user_reports (
    report_id SERIAL PRIMARY KEY,
    reporter_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reported_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(conversation_id) ON DELETE SET NULL,
    reason VARCHAR(500) NOT NULL CHECK (char_length(trim(reason)) BETWEEN 1 AND 500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (reporter_user_id <> reported_user_id)
);

-- In-app event feed. Payload contains non-sensitive display text only.
CREATE TABLE notifications (
    notification_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    kind VARCHAR(40) NOT NULL,
    message VARCHAR(500) NOT NULL,
    read_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX notifications_user_created_idx
    ON notifications (user_id, created_at DESC);

-- PostgreSQL treats NULL values as distinct in a normal UNIQUE constraint,
-- so use partial indexes to prevent duplicate reports both with and without a
-- conversation context.
CREATE UNIQUE INDEX user_reports_once_per_conversation_idx
    ON user_reports (reporter_user_id, reported_user_id, conversation_id)
    WHERE conversation_id IS NOT NULL;
CREATE UNIQUE INDEX user_reports_once_without_conversation_idx
    ON user_reports (reporter_user_id, reported_user_id)
    WHERE conversation_id IS NULL;
