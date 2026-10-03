CREATE TABLE upload_jobs (
    upload_id text PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES tenants(tenant_id),
    uploader_role text NOT NULL,
    resource_type text NOT NULL CHECK (resource_type IN ('tracking_events', 'vendor_invoices', 'document')),
    file_format text NOT NULL CHECK (file_format IN ('csv', 'json', 'pdf')),
    original_filename text NOT NULL,
    media_type text NOT NULL,
    content_sha256 char(64) NOT NULL,
    byte_count integer NOT NULL CHECK (byte_count >= 0),
    status text NOT NULL CHECK (status IN ('validated', 'quarantined', 'committing', 'committed')),
    sensitivity text,
    title text,
    document_id text,
    record_count integer NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    preview jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
    normalized_records jsonb,
    raw_content bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    committed_at timestamptz,
    CHECK ((resource_type = 'document' AND file_format = 'pdf')
        OR (resource_type <> 'document' AND file_format IN ('csv', 'json'))),
    CHECK ((status = 'quarantined' AND jsonb_array_length(validation_errors) > 0)
        OR status <> 'quarantined')
);

CREATE INDEX idx_upload_jobs_tenant_created ON upload_jobs (tenant_id, created_at DESC);
CREATE INDEX idx_upload_jobs_tenant_status ON upload_jobs (tenant_id, status);
