ALTER TABLE restaurant_naver_verifications
    ADD COLUMN source_fingerprint VARCHAR(64) NULL AFTER verification_reason;

CREATE INDEX ix_naver_verifications_source_fingerprint
    ON restaurant_naver_verifications (provider, source_fingerprint);
