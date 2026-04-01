-- =====================================================
-- Migration: 003_research_rq_metrics
-- Purpose: RQ1–RQ5 research tables/columns (entropy, conflicts, flags)
-- Apply in Supabase SQL editor if tables already exist partially.
-- =====================================================

-- ----- research_metrics -----
CREATE TABLE IF NOT EXISTS research_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    condition VARCHAR(20),
    gini_coefficient DOUBLE PRECISION,
    participation_entropy DOUBLE PRECISION,
    max_share DOUBLE PRECISION,
    min_share DOUBLE PRECISION,
    dominance_gap DOUBLE PRECISION,
    total_messages INTEGER,
    total_words INTEGER,
    ranking_accuracy DOUBLE PRECISION,
    time_to_consensus INTEGER,
    conflict_count INTEGER,
    repair_count INTEGER,
    repair_rate DOUBLE PRECISION,
    mean_time_to_repair_seconds DOUBLE PRECISION,
    ranking_submitted BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_metrics_room_id ON research_metrics(room_id);

-- Additive columns for existing deployments
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS condition VARCHAR(20);
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS participation_entropy DOUBLE PRECISION;
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS conflict_count INTEGER;
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS repair_count INTEGER;
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS repair_rate DOUBLE PRECISION;
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS mean_time_to_repair_seconds DOUBLE PRECISION;
ALTER TABLE research_metrics ADD COLUMN IF NOT EXISTS ranking_submitted BOOLEAN;

-- ----- participant_metrics -----
CREATE TABLE IF NOT EXISTS participant_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    username VARCHAR(100) NOT NULL,
    message_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    share_of_talk DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_participant_metrics_room_id ON participant_metrics(room_id);

-- ----- moderator_interventions -----
CREATE TABLE IF NOT EXISTS moderator_interventions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    intervention_type VARCHAR(80) NOT NULL,
    target_user VARCHAR(100),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_moderator_interventions_room_id ON moderator_interventions(room_id);

-- ----- conflict_episodes (optional row-level RQ2) -----
CREATE TABLE IF NOT EXISTS conflict_episodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    conflict_message_id UUID,
    conflict_user VARCHAR(100),
    conflict_text TEXT,
    severity_score INTEGER,
    repair_message_id UUID,
    repair_user VARCHAR(100),
    time_to_repair INTEGER,
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conflict_episodes_room_id ON conflict_episodes(room_id);

-- ----- messages: allow toxicity row type -----
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_message_type_check;
ALTER TABLE messages
    ADD CONSTRAINT messages_message_type_check
    CHECK (
        message_type IN (
            'chat',
            'chat_flagged',
            'system',
            'story',
            'moderator',
            'task'
        )
    );

COMMENT ON COLUMN research_metrics.participation_entropy IS 'RQ1: normalized Shannon entropy of speaking shares (0–1)';
COMMENT ON COLUMN research_metrics.conflict_count IS 'RQ2: keyword-based conflict turns (research_metrics.detect_conflict_episodes)';
COMMENT ON COLUMN research_metrics.repair_count IS 'RQ2: repair messages paired with recent conflicts';
