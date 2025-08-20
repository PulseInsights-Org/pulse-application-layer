# Intake to Ingest MVP

## 1. Web app

- Simple page with two inputs: meeting link and notes or file

• On submit: call `POST /intakes.init`, then upload raw text or file to the exact storage path, then call `POST /intakes.finalize`

• Show states: uploading, processing, done

• Poll `GET /intakes.{id}` for status

## 2. API server (FastAPI)

- Endpoints

• `POST /intakes.init` → create intake row, return `intake_id` and `storage_path`

• `POST /upload.text.{intake_id}` → write pasted text to Supabase Storage

• `POST /intakes.{intake_id}.finalize` → record checksum and size, mark ready

• `GET /intakes.{intake_id}` → return status and `last_error`

• Stores: Supabase Postgres tables `intakes` and `memories`

• Storage: Supabase Storage bucket `intakes-raw` with path `org/{org_id}/intake/{intake_id}/raw.txt`

• Idempotency: `unique(org_id, idempotency_key)` on `intakes`

• Triggers ingest: set `status = ready` and `next_retry_at = now`

## 3. Ingest worker or service

- Pick ready intakes where `next_retry_at` is in the past

• Call Ingest API with `org_id`, `intake_id`, `storage_path`, `checksum`

• Ingest reads from storage and processes content

• Worker updates intake `status = done` when processing completes

• On failure: increment `attempts`, set `last_error`, schedule `next_retry_at` with simple backoff

## Minimal schema

```
intakes: id, org_id, status, storage_path, size_bytes, checksum,
         idempotency_key, attempts, next_retry_at, last_error,
         created_at, updated_at

memories: id, intake_id, org_id, title, summary, metadata, created_at
```

## Tech stack

- Frontend: Next.js TypeScript, Tailwind

• Backend: FastAPI, httpx, Pydantic

• DB and storage: Supabase Postgres and Storage

• Worker: asyncio loop in the same FastAPI container for MVP, split later if needed

## End to end flow

1. Web calls `intakes.init` and gets `intake_id` and `storage_path`
2. Web uploads raw text or file to `storage_path`
3. Web computes SHA256 and calls `intakes.finalize`
4. Worker sees ready intake and calls Ingest API by pointer
5. Worker marks done and Web shows complete

## Idempotency

- Purpose: safe retries without duplicates or data loss

• Client key: generate `idempotency_key` UUID per Save and Process and reuse it on any retry

• Init: `unique(org_id, idempotency_key)` returns the same `intake_id` on retry

• Upload: deterministic `storage_path` with `upsert = false` so reuploads do not overwrite completed data

• Finalize: setting checksum, size, and ready is safe to replay, reject if checksum changes

• Worker: guarded update from ready to ingesting so only one worker proceeds, pass `intake_id` and `idempotency_key` to ingest, ingest side dedupes on `intake_id`

• Common failures handled: double click replays the same intake, client crash during upload can resume to the same path, lost finalize response can be retried, ingest timeout schedules a retry while the raw content remains safe in storage