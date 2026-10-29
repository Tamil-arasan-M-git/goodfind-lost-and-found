BEGIN;

CREATE TABLE IF NOT EXISTS chat_requests (
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

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL UNIQUE REFERENCES matches(match_id) ON DELETE CASCADE,
    request_id INTEGER NOT NULL UNIQUE REFERENCES chat_requests(request_id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CLOSED')),
    closed_at TIMESTAMP,
    closed_by_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_participants (
    conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    display_alias VARCHAR(80) NOT NULL,
    blocked_at TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id),
    UNIQUE (conversation_id, display_alias)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    sender_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    content VARCHAR(2000) NOT NULL CHECK (char_length(trim(content)) BETWEEN 1 AND 2000),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS messages_conversation_created_idx
    ON messages (conversation_id, created_at, message_id);

CREATE TABLE IF NOT EXISTS user_blocks (
    blocker_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    blocked_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (blocker_user_id, blocked_user_id),
    CHECK (blocker_user_id <> blocked_user_id)
);

CREATE TABLE IF NOT EXISTS user_reports (
    report_id SERIAL PRIMARY KEY,
    reporter_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reported_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(conversation_id) ON DELETE SET NULL,
    reason VARCHAR(500) NOT NULL CHECK (char_length(trim(reason)) BETWEEN 1 AND 500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (reporter_user_id <> reported_user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS user_reports_once_per_conversation_idx
    ON user_reports (reporter_user_id, reported_user_id, conversation_id)
    WHERE conversation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS user_reports_once_without_conversation_idx
    ON user_reports (reporter_user_id, reported_user_id)
    WHERE conversation_id IS NULL;

COMMIT;
