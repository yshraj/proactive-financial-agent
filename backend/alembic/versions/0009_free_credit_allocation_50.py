"""Reduce the initial free lifetime allocation from 200 to 50 credits.

Manual grants remain intact. Existing usage is never made negative: if an
account has already used more than its reduced entitlement, its total is
clamped to the used amount (zero remaining).

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


_UP = r"""
ALTER TABLE credit_ledger DISABLE TRIGGER credit_ledger_immutable;

DO $$
DECLARE
    v_account record;
    v_new_total integer;
    v_reduction integer;
BEGIN
    FOR v_account IN
        SELECT a.id, a.total_granted, a.used
        FROM credit_accounts a
        JOIN credit_ledger initial
          ON initial.account_id = a.id
         AND initial.entry_type = 'grant'
         AND initial.idempotency_key = 'initial-allocation'
         AND initial.amount = 200
        FOR UPDATE OF a
    LOOP
        -- Remove only the 150-credit difference in the free allocation.
        -- Any later manual grants stay in total_granted.
        v_new_total := GREATEST(v_account.used, v_account.total_granted - 150);
        v_reduction := v_account.total_granted - v_new_total;

        UPDATE credit_accounts
        SET total_granted = v_new_total,
            version = version + 1,
            updated_at = now()
        WHERE id = v_account.id;

        UPDATE credit_ledger
        SET balance_after = GREATEST(balance_after - v_reduction, 0)
        WHERE account_id = v_account.id
          AND NOT (
              entry_type = 'grant'
              AND idempotency_key = 'initial-allocation'
          );

        UPDATE credit_ledger
        SET amount = amount - v_reduction,
            balance_after = amount - v_reduction,
            description = 'Initial free lifetime credit allocation',
            metadata = metadata || jsonb_build_object(
                'migration_0009_original_amount', amount
            )
        WHERE account_id = v_account.id
          AND entry_type = 'grant'
          AND idempotency_key = 'initial-allocation';
    END LOOP;
END;
$$;

ALTER TABLE credit_ledger ENABLE TRIGGER credit_ledger_immutable;
"""


_DOWN = r"""
ALTER TABLE credit_ledger DISABLE TRIGGER credit_ledger_immutable;

DO $$
DECLARE
    v_account record;
    v_original integer;
    v_increase integer;
BEGIN
    FOR v_account IN
        SELECT a.id, a.total_granted,
               (initial.metadata->>'migration_0009_original_amount')::integer
                   AS original_amount
        FROM credit_accounts a
        JOIN credit_ledger initial
          ON initial.account_id = a.id
         AND initial.entry_type = 'grant'
         AND initial.idempotency_key = 'initial-allocation'
        WHERE initial.metadata ? 'migration_0009_original_amount'
        FOR UPDATE OF a
    LOOP
        v_original := v_account.original_amount;
        SELECT v_original - amount INTO v_increase
        FROM credit_ledger
        WHERE account_id = v_account.id
          AND entry_type = 'grant'
          AND idempotency_key = 'initial-allocation';

        UPDATE credit_accounts
        SET total_granted = total_granted + v_increase,
            version = version + 1,
            updated_at = now()
        WHERE id = v_account.id;

        UPDATE credit_ledger
        SET balance_after = balance_after + v_increase
        WHERE account_id = v_account.id
          AND NOT (
              entry_type = 'grant'
              AND idempotency_key = 'initial-allocation'
          );

        UPDATE credit_ledger
        SET amount = v_original,
            balance_after = v_original,
            description = 'Initial lifetime credit allocation',
            metadata = metadata - 'migration_0009_original_amount'
        WHERE account_id = v_account.id
          AND entry_type = 'grant'
          AND idempotency_key = 'initial-allocation';
    END LOOP;
END;
$$;

ALTER TABLE credit_ledger ENABLE TRIGGER credit_ledger_immutable;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
