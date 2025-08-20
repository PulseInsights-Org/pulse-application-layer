# Intake to Ingest MVP

A FastAPI-based API for managing document intake and processing workflows.

## Quick Start

### 1. Setup Environment

Create a `.env` file in the project root:

```bash
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
SUPABASE_ANON_KEY=you_supabase_anon_key_here
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

The API will be available at `http://localhost:8000`

## API Endpoints

### Initialize Intake
```bash
curl -X POST "http://localhost:8000/api/intakes.init" \
  -H "x-org-id: pulse-dev" \
  -H "x-idempotency-key: 550e8400-e29b-41d4-a716-446655440001"
```

### Upload File (supports .txt and .md files)
```bash
curl -X POST "http://localhost:8000/api/upload/file/{intake_id}" \
  -H "x-org-id: pulse-dev" \
  -F "file=@meeting-notes.txt"
```

### Upload Text (uploading copy pasted text via UI)
```bash
curl -X POST "http://localhost:8000/api/upload/text/{intake_id}" \
  -H "x-org-id: pulse-dev" \
  -F "text_content=Meeting summary: Discussed Q4 goals..."
```

### Get Intake Status
```bash
curl -X GET "http://localhost:8000/api/intakes/{intake_id}" \
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

## Supabase Storage Bucket folder structure

```
intakes-raw/org/pulse-dev/intake/{intake_id}/filename.txt
```


## Tech Stack

- **Backend**: FastAPI, Pydantic
- **Database**: Supabase (PostgreSQL)
- **Storage**: Supabase Storage
- **Server**: Uvicorn (ASGI)

## Development

The API automatically loads environment variables from `.env` file and initializes the Supabase client on first use.

For API documentation, visit `http://localhost:8000/docs` when the server is running.
