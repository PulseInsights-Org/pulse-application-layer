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
  -H "x-org-id: your-org-id" \
  -H "x-idempotency-key: 550e8400-e29b-41d4-a716-446655440001"
```

**Response:**
```json
{
  "intake_id": "generated-uuid",
  "storage_path": "org/your-org-id/intake/generated-uuid/raw.txt"
}
```

### Get Intake Status
```bash
curl -X GET "http://localhost:8000/api/intakes/{intake_id}" \
  -H "x-org-id: your-org-id"
```

**Response:**
```json
{
  "id": "intake-uuid",
  "org_id": "your-org-id",
  "status": "initialized",
  "storage_path": "org/your-org-id/intake/intake-uuid/raw.txt",
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440001",
  "created_at": "2024-01-01T00:00:00Z"
}
```

## Headers Required

- **`x-org-id`**: Organization identifier (required for all endpoints)
- **`x-idempotency-key`**: Unique key for idempotent operations (required for POST endpoints)

## Database Schema

### Intakes Table
- `id`: UUID primary key
- `org_id`: Organization identifier
- `status`: Current status (initialized, ready, processing, done)
- `storage_path`: File storage path
- `idempotency_key`: Idempotency key
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

## Tech Stack

- **Backend**: FastAPI, Pydantic
- **Database**: Supabase (PostgreSQL)
- **Storage**: Supabase Storage
- **Server**: Uvicorn (ASGI)

## Development

The API automatically loads environment variables from `.env` file and initializes the Supabase client on first use.

For API documentation, visit `http://localhost:8000/docs` when the server is running.
