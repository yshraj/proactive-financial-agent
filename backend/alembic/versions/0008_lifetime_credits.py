"""Lifetime AI credit accounts, immutable ledger, reservations, and requests.

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


_UP = r"""
CREATE TABLE credit_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    principal_key text NOT NULL,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    total_granted integer NOT NULL DEFAULT 0 CHECK (total_granted >= 0),
    used integer NOT NULL DEFAULT 0 CHECK (used >= 0 AND used <= total_granted),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, principal_key)
);

CREATE TABLE credit_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL REFERENCES credit_accounts(id) ON DELETE RESTRICT,
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    feature text NOT NULL,
    cost integer NOT NULL CHECK (cost > 0),
    idempotency_key text NOT NULL,
    status text NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'committed', 'released')),
    created_at timestamptz NOT NULL DEFAULT now(),
    committed_at timestamptz,
    released_at timestamptz,
    UNIQUE (account_id, idempotency_key)
);

CREATE TABLE credit_ledger (
    id bigserial PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES credit_accounts(id) ON DELETE RESTRICT,
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    reservation_id uuid REFERENCES credit_reservations(id) ON DELETE RESTRICT,
    entry_type text NOT NULL CHECK (entry_type IN ('grant', 'usage')),
    amount integer NOT NULL CHECK (amount > 0),
    feature text,
    balance_after integer NOT NULL CHECK (balance_after >= 0),
    status text NOT NULL DEFAULT 'committed',
    description text NOT NULL,
    idempotency_key text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, idempotency_key, entry_type)
);

CREATE TABLE credit_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL REFERENCES credit_accounts(id) ON DELETE RESTRICT,
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    principal_key text NOT NULL,
    requested_by uuid REFERENCES users(id) ON DELETE SET NULL,
    message text,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'declined')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_credit_ledger_account_created
    ON credit_ledger(account_id, created_at DESC, id DESC);
CREATE INDEX idx_credit_requests_org_created
    ON credit_requests(org_id, created_at DESC);
CREATE INDEX idx_credit_reservations_active
    ON credit_reservations(account_id) WHERE status = 'reserved';

CREATE OR REPLACE FUNCTION prevent_credit_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'credit_ledger is append-only';
END;
$$;
CREATE TRIGGER credit_ledger_immutable
BEFORE UPDATE OR DELETE ON credit_ledger
FOR EACH ROW EXECUTE FUNCTION prevent_credit_ledger_mutation();

ALTER TABLE credit_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_isolation ON credit_accounts FOR ALL TO kritifin_app
    USING (org_id = app_org_id()) WITH CHECK (org_id = app_org_id());
CREATE POLICY org_isolation ON credit_reservations FOR ALL TO kritifin_app
    USING (org_id = app_org_id()) WITH CHECK (org_id = app_org_id());
CREATE POLICY credit_ledger_select ON credit_ledger FOR SELECT TO kritifin_app
    USING (org_id = app_org_id());
CREATE POLICY credit_requests_select ON credit_requests FOR SELECT TO kritifin_app
    USING (org_id = app_org_id());

GRANT SELECT ON credit_accounts, credit_reservations, credit_ledger, credit_requests
    TO kritifin_app;
GRANT USAGE, SELECT ON SEQUENCE credit_ledger_id_seq TO kritifin_app;

CREATE OR REPLACE FUNCTION credit_get_or_create_account(
    p_org_id uuid, p_principal_key text, p_user_id uuid, p_default_credits integer
) RETURNS credit_accounts
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_account credit_accounts;
BEGIN
    IF p_org_id IS NULL OR NULLIF(p_principal_key, '') IS NULL
       OR p_default_credits < 0 THEN
        RAISE EXCEPTION 'invalid credit account arguments';
    END IF;
    IF app_org_id() IS DISTINCT FROM p_org_id THEN
        RAISE EXCEPTION 'credit account tenant mismatch';
    END IF;

    INSERT INTO credit_accounts (
        org_id, principal_key, user_id, total_granted
    ) VALUES (
        p_org_id, p_principal_key, p_user_id, p_default_credits
    )
    ON CONFLICT (org_id, principal_key) DO NOTHING;

    SELECT * INTO v_account FROM credit_accounts
    WHERE org_id = p_org_id AND principal_key = p_principal_key
    FOR UPDATE;

    INSERT INTO credit_ledger (
        account_id, org_id, entry_type, amount, balance_after, status,
        description, idempotency_key, metadata
    )
    SELECT v_account.id, p_org_id, 'grant', p_default_credits,
           p_default_credits, 'committed', 'Initial lifetime credit allocation',
           'initial-allocation', '{"source":"initial_allocation"}'::jsonb
    WHERE p_default_credits > 0
    ON CONFLICT (account_id, idempotency_key, entry_type) DO NOTHING;
    RETURN v_account;
END;
$$;

CREATE OR REPLACE FUNCTION reserve_credits(
    p_org_id uuid, p_principal_key text, p_user_id uuid,
    p_feature text, p_cost integer, p_idempotency_key text,
    p_default_credits integer
) RETURNS TABLE (
    reservation_id uuid, reservation_status text, required integer,
    remaining integer, account_version bigint, is_replay boolean
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_account credit_accounts;
    v_res credit_reservations;
    v_reserved integer;
    v_remaining integer;
BEGIN
    IF p_cost <= 0 OR NULLIF(p_feature, '') IS NULL
       OR NULLIF(p_idempotency_key, '') IS NULL THEN
        RAISE EXCEPTION 'invalid credit reservation arguments';
    END IF;
    v_account := credit_get_or_create_account(
        p_org_id, p_principal_key, p_user_id, p_default_credits
    );

    SELECT * INTO v_res FROM credit_reservations
    WHERE account_id = v_account.id AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        SELECT COALESCE(sum(cost), 0) INTO v_reserved
        FROM credit_reservations
        WHERE account_id = v_account.id AND status = 'reserved' AND id <> v_res.id;
        RETURN QUERY SELECT v_res.id, v_res.status, v_res.cost,
            GREATEST(v_account.total_granted - v_account.used - v_reserved, 0),
            v_account.version, true;
        RETURN;
    END IF;

    SELECT COALESCE(sum(cost), 0) INTO v_reserved
    FROM credit_reservations
    WHERE account_id = v_account.id AND status = 'reserved';
    v_remaining := v_account.total_granted - v_account.used - v_reserved;
    IF v_remaining < p_cost THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'insufficient_credits',
            DETAIL = json_build_object(
                'required', p_cost, 'remaining', GREATEST(v_remaining, 0),
                'feature', p_feature
            )::text;
    END IF;

    INSERT INTO credit_reservations (
        account_id, org_id, feature, cost, idempotency_key
    ) VALUES (
        v_account.id, p_org_id, p_feature, p_cost, p_idempotency_key
    ) RETURNING * INTO v_res;
    RETURN QUERY SELECT v_res.id, v_res.status, v_res.cost,
        v_remaining - p_cost, v_account.version, false;
END;
$$;

CREATE OR REPLACE FUNCTION commit_credit_reservation(p_reservation_id uuid)
RETURNS credit_reservations
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_res credit_reservations;
    v_account credit_accounts;
BEGIN
    SELECT * INTO v_res FROM credit_reservations
    WHERE id = p_reservation_id FOR UPDATE;
    IF NOT FOUND OR app_org_id() IS DISTINCT FROM v_res.org_id THEN
        RAISE EXCEPTION 'credit reservation not found';
    END IF;
    IF v_res.status <> 'reserved' THEN RETURN v_res; END IF;

    SELECT * INTO v_account FROM credit_accounts
    WHERE id = v_res.account_id FOR UPDATE;
    IF v_account.used + v_res.cost > v_account.total_granted THEN
        RAISE EXCEPTION 'credit invariant violated';
    END IF;
    UPDATE credit_accounts SET
        used = used + v_res.cost, version = version + 1, updated_at = now()
    WHERE id = v_account.id RETURNING * INTO v_account;
    UPDATE credit_reservations SET status = 'committed', committed_at = now()
    WHERE id = v_res.id RETURNING * INTO v_res;
    INSERT INTO credit_ledger (
        account_id, org_id, reservation_id, entry_type, amount,
        feature, balance_after, status, description, idempotency_key, metadata
    ) VALUES (
        v_res.account_id, v_res.org_id, v_res.id, 'usage', v_res.cost,
        v_res.feature, v_account.total_granted - v_account.used, 'committed',
        initcap(replace(v_res.feature, '_', ' ')) || ' credit usage',
        v_res.idempotency_key, '{"source":"reservation"}'::jsonb
    ) ON CONFLICT (account_id, idempotency_key, entry_type) DO NOTHING;
    RETURN v_res;
END;
$$;

CREATE OR REPLACE FUNCTION release_credit_reservation(p_reservation_id uuid)
RETURNS credit_reservations
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_res credit_reservations;
BEGIN
    SELECT * INTO v_res FROM credit_reservations
    WHERE id = p_reservation_id FOR UPDATE;
    IF NOT FOUND OR app_org_id() IS DISTINCT FROM v_res.org_id THEN
        RAISE EXCEPTION 'credit reservation not found';
    END IF;
    IF v_res.status = 'reserved' THEN
        UPDATE credit_reservations SET status = 'released', released_at = now()
        WHERE id = v_res.id RETURNING * INTO v_res;
    END IF;
    RETURN v_res;
END;
$$;

CREATE OR REPLACE FUNCTION grant_credits(
    p_org_id uuid, p_principal_key text, p_user_id uuid,
    p_amount integer, p_idempotency_key text, p_default_credits integer,
    p_metadata jsonb DEFAULT '{}'::jsonb
) RETURNS credit_accounts
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_account credit_accounts;
BEGIN
    IF p_amount <= 0 OR NULLIF(p_idempotency_key, '') IS NULL THEN
        RAISE EXCEPTION 'invalid credit grant arguments';
    END IF;
    v_account := credit_get_or_create_account(
        p_org_id, p_principal_key, p_user_id, p_default_credits
    );
    INSERT INTO credit_ledger (
        account_id, org_id, entry_type, amount, balance_after, status,
        description, idempotency_key, metadata
    ) VALUES (
        v_account.id, p_org_id, 'grant', p_amount,
        v_account.total_granted - v_account.used + p_amount, 'committed',
        COALESCE(NULLIF(p_metadata->>'description', ''), 'Additional credits granted'),
        p_idempotency_key,
        COALESCE(p_metadata, '{}'::jsonb)
    ) ON CONFLICT (account_id, idempotency_key, entry_type) DO NOTHING;
    IF FOUND THEN
        UPDATE credit_accounts SET total_granted = total_granted + p_amount,
            version = version + 1, updated_at = now()
        WHERE id = v_account.id RETURNING * INTO v_account;
    ELSE
        SELECT * INTO v_account FROM credit_accounts WHERE id = v_account.id;
    END IF;
    RETURN v_account;
END;
$$;

REVOKE ALL ON FUNCTION credit_get_or_create_account(uuid, text, uuid, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION reserve_credits(uuid, text, uuid, text, integer, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION commit_credit_reservation(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION release_credit_reservation(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION grant_credits(uuid, text, uuid, integer, text, integer, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION credit_get_or_create_account(uuid, text, uuid, integer) TO kritifin_app;
GRANT EXECUTE ON FUNCTION reserve_credits(uuid, text, uuid, text, integer, text, integer) TO kritifin_app;
GRANT EXECUTE ON FUNCTION commit_credit_reservation(uuid) TO kritifin_app;
GRANT EXECUTE ON FUNCTION release_credit_reservation(uuid) TO kritifin_app;
GRANT EXECUTE ON FUNCTION grant_credits(uuid, text, uuid, integer, text, integer, jsonb) TO kritifin_app;

-- Requests are inserted through a narrow function; the runtime role never gets
-- direct INSERT access to account_id/principal/status fields.
CREATE OR REPLACE FUNCTION create_credit_request(
    p_org_id uuid, p_principal_key text, p_user_id uuid,
    p_default_credits integer, p_message text
) RETURNS credit_requests
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_account credit_accounts; v_request credit_requests;
BEGIN
    v_account := credit_get_or_create_account(
        p_org_id, p_principal_key, p_user_id, p_default_credits
    );
    INSERT INTO credit_requests (
        account_id, org_id, principal_key, requested_by, message
    ) VALUES (
        v_account.id, p_org_id, p_principal_key, p_user_id,
        NULLIF(left(COALESCE(p_message, ''), 2000), '')
    ) RETURNING * INTO v_request;
    RETURN v_request;
END;
$$;
REVOKE ALL ON FUNCTION create_credit_request(uuid, text, uuid, integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION create_credit_request(uuid, text, uuid, integer, text) TO kritifin_app;

-- The existing job sweeper now releases reservations for terminally exhausted
-- jobs. Active retries deliberately keep their reservation.
CREATE OR REPLACE FUNCTION fail_exhausted_jobs(p_stale_seconds int DEFAULT 600)
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_job record; v_count integer := 0; v_reservation_id uuid;
BEGIN
    FOR v_job IN
        UPDATE jobs
        SET status = 'ERROR',
            message = 'Failed',
            error = COALESCE(error, 'Worker retries exhausted (process restarted mid-job).')
        WHERE status = 'PROCESSING'
          AND locked_at < NOW() - make_interval(secs => p_stale_seconds)
          AND attempts >= max_attempts
        RETURNING org_id, payload
    LOOP
        v_count := v_count + 1;
        BEGIN
            v_reservation_id := NULLIF(
                v_job.payload->>'credit_reservation_id', ''
            )::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            v_reservation_id := NULL;
        END;
        IF v_reservation_id IS NOT NULL THEN
            UPDATE credit_reservations
            SET status = 'released', released_at = now()
            WHERE id = v_reservation_id
              AND org_id = v_job.org_id
              AND status = 'reserved';
        END IF;
    END LOOP;
    RETURN v_count;
END;
$$;
"""

_DOWN = r"""
DROP FUNCTION IF EXISTS create_credit_request(uuid, text, uuid, integer, text);
DROP FUNCTION IF EXISTS grant_credits(uuid, text, uuid, integer, text, integer, jsonb);
DROP FUNCTION IF EXISTS release_credit_reservation(uuid);
DROP FUNCTION IF EXISTS commit_credit_reservation(uuid);
DROP FUNCTION IF EXISTS reserve_credits(uuid, text, uuid, text, integer, text, integer);
DROP FUNCTION IF EXISTS credit_get_or_create_account(uuid, text, uuid, integer);
DROP TRIGGER IF EXISTS credit_ledger_immutable ON credit_ledger;
DROP FUNCTION IF EXISTS prevent_credit_ledger_mutation();
DROP TABLE IF EXISTS credit_requests;
DROP TABLE IF EXISTS credit_ledger;
DROP TABLE IF EXISTS credit_reservations;
DROP TABLE IF EXISTS credit_accounts;
CREATE OR REPLACE FUNCTION fail_exhausted_jobs(p_stale_seconds int DEFAULT 600)
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_count int;
BEGIN
    UPDATE jobs
    SET status = 'ERROR',
        message = 'Failed',
        error = COALESCE(error, 'Worker retries exhausted (process restarted mid-job).')
    WHERE status = 'PROCESSING'
      AND locked_at < NOW() - make_interval(secs => p_stale_seconds)
      AND attempts >= max_attempts;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
