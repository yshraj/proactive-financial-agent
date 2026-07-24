"""LLM gateway quota counters: per-provider/model RPM+RPD tracking.

The free-tier model gateway (services/model_gateway.py) enforces each
provider's published requests-per-minute and requests-per-day caps *before*
sending a request, so the app degrades by falling down its routing chain
instead of burning provider goodwill on 429s. Counters are global platform
state (not org data), so access goes through the SECURITY DEFINER
``bump_llm_quota()`` — the table itself grants the runtime role nothing.

``bump_llm_quota`` atomically increments the minute + UTC-day windows and
returns FALSE (after undoing the increment) when either would exceed its
limit. Expired windows are cleaned up opportunistically (~1% of calls).

Revision ID: 0012
Revises: 0011
"""
from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE IF NOT EXISTS llm_quota_counters (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    window_kind TEXT NOT NULL CHECK (window_kind IN ('minute', 'day')),
    window_start TIMESTAMPTZ NOT NULL,
    request_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, model, window_kind, window_start)
);

CREATE OR REPLACE FUNCTION bump_llm_quota(
    p_provider TEXT,
    p_model TEXT,
    p_minute_limit INT,
    p_day_limit INT
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_minute_start TIMESTAMPTZ := date_trunc('minute', NOW());
    v_day_start TIMESTAMPTZ := (date_trunc('day', NOW() AT TIME ZONE 'UTC')) AT TIME ZONE 'UTC';
    v_minute_count INT;
    v_day_count INT;
BEGIN
    -- Opportunistic cleanup of expired windows (tiny table; ~1% of calls).
    IF random() < 0.01 THEN
        DELETE FROM llm_quota_counters WHERE window_start < NOW() - INTERVAL '2 days';
    END IF;

    INSERT INTO llm_quota_counters (provider, model, window_kind, window_start, request_count)
    VALUES (p_provider, p_model, 'minute', v_minute_start, 1)
    ON CONFLICT (provider, model, window_kind, window_start)
    DO UPDATE SET request_count = llm_quota_counters.request_count + 1
    RETURNING request_count INTO v_minute_count;

    INSERT INTO llm_quota_counters (provider, model, window_kind, window_start, request_count)
    VALUES (p_provider, p_model, 'day', v_day_start, 1)
    ON CONFLICT (provider, model, window_kind, window_start)
    DO UPDATE SET request_count = llm_quota_counters.request_count + 1
    RETURNING request_count INTO v_day_count;

    IF (p_minute_limit > 0 AND v_minute_count > p_minute_limit)
       OR (p_day_limit > 0 AND v_day_count > p_day_limit) THEN
        UPDATE llm_quota_counters SET request_count = GREATEST(request_count - 1, 0)
         WHERE provider = p_provider AND model = p_model
           AND window_kind = 'minute' AND window_start = v_minute_start;
        UPDATE llm_quota_counters SET request_count = GREATEST(request_count - 1, 0)
         WHERE provider = p_provider AND model = p_model
           AND window_kind = 'day' AND window_start = v_day_start;
        RETURN FALSE;
    END IF;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION bump_llm_quota(TEXT, TEXT, INT, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION bump_llm_quota(TEXT, TEXT, INT, INT) TO kritifin_app;
"""

_DOWN = """
DROP FUNCTION IF EXISTS bump_llm_quota(TEXT, TEXT, INT, INT);
DROP TABLE IF EXISTS llm_quota_counters;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
