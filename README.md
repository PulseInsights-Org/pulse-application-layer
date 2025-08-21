# Intake to Ingest MVP

A FastAPI-based API for managing document intake and processing workflows.

## Quick Start

### 1. Setup Environment

Create a `.env` file in the project root:

```bash
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
SUPABASE_ANON_KEY=your_supabase_anon_key_here
DEFAULT_ORG_ID=your_org_id_here
PULSE_API_BASE_URL=http://localhost:8001
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the API Server

```bash
# Run directly
python -m app.main

# or start development mode with auto-reload
python -m uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8001`

## API Endpoints

### Initialize Intake
```bash
curl -X POST "http://localhost:8001/api/intakes/init" \
  -H "x-org-id: pulse-dev" \
  -H "x-idempotency-key: 550e8400-e29b-41d4-a716-446655440001"
```
**Note**: 
- Ideally `x-idempotency-key` will be generated on the client side. For the sake for testing the API we are hardcoding this.
- assuming x-org-id as `pulse-dev` change if required
### Upload File (supports .txt and .md files)
```bash
curl -X POST "http://localhost:8001/api/upload/file/{intake_id}" \
  -H "x-org-id: pulse-dev" \
  -F "file=@meeting-notes.txt"
```

### Upload Text (uploading copy pasted text via UI)
```bash
curl -X POST "http://localhost:8001/api/upload/text/{intake_id}" \
  -H "x-org-id: pulse-dev" \
  -F "text_content=Meeting summary: Discussed Q4 goals..."
```

### Get Intake Status
```bash
curl -X GET "http://localhost:8001/api/intakes/{intake_id}" \
  -H "x-org-id: pulse-dev"
```

### Finalize Intake (validates file exists, calculates checksum and size, then marks as ready)
```bash
curl -X POST "http://localhost:8001/api/intakes/{intake_id}/finalize" \
  -H "x-org-id: pulse-dev"
```

## Database Schema

### Intakes Table
- `id`: UUID primary key
- `org_id`: Organization identifier
- `status`: Current status (initialized, ready, processing, done)
- `storage_path`: File storage path
- `idempotency_key`: Idempotency key
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

### Memories Table
- `id`: UUID primary key
- `intake_id`: Reference to the source intake
- `org_id`: Organization identifier with foreign key constraint
- `title`: Extracted title of the memory
- `summary`: Processed summary content
- `metadata`: Additional JSONB data for extensibility
- `created_at`: Creation timestamp

## Background Workers

The application includes a background worker system that automatically processes intakes when they are finalized. Workers operate on a polling mechanism and start automatically with the server.

### How Workers Work

1. **Auto-start**: Workers automatically start when the FastAPI server starts up
2. **Polling mechanism**: Workers continuously poll the database for intakes with `ready` status
3. **Processing pipeline**: When an intake is found, workers:
   - Download the file from Supabase storage
   - Send content to the pulse project's extraction API for AI-powered processing
   - Process the API response and create memory records
   - Store results in the memories table
   - Update intake status to `done`

**Note**: The extraction logic has been moved to the pulse project. Workers now call the pulse API instead of performing local extraction.

## Supabase Storage Bucket folder structure

```
intakes-raw/org/pulse-dev/intake/{intake_id}/filename.txt
```


## Architecture

### New Architecture (Current)
The application has been refactored to use a microservices approach:

- **pulse-application-layer**: Handles intake management, file storage, and worker orchestration
- **pulse project**: Provides the extraction API with AI-powered content processing
- **Workers**: Poll for ready intakes and call the pulse API for extraction

### Worker Flow
1. Worker polls Supabase for intakes with `ready` status
2. Downloads content from Supabase storage
3. Calls pulse extraction API with content
4. Processes API response and creates memory records
5. Updates intake status to `done`

## Tech Stack

- **Backend**: FastAPI, Pydantic
- **Database**: Supabase (PostgreSQL)
- **Storage**: Supabase Storage
- **Server**: Uvicorn (ASGI)
- **Extraction**: Pulse project API (external service)

## Development

The API automatically loads environment variables from `.env` file and initializes the Supabase client on first use.

For API documentation, visit `http://localhost:8001/docs` when the server is running.
