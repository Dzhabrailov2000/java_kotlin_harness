BEGIN;
ALTER TABLE accounts ADD CONSTRAINT balance_nonnegative CHECK (balance >= 0) NOT VALID;
COMMIT;
BEGIN;
ALTER TABLE accounts VALIDATE CONSTRAINT balance_nonnegative;
COMMIT;
