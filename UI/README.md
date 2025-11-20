# PulseLive Chat UI (Streamlit)

A minimal chat interface for querying the existing PulseFastAPI backend via the `/api/query` endpoint.

## What this UI does

- Renders a simple, professional chat interface in the browser.
- Sends user questions to your backend:
  - `POST {PULSE_API_BASE_URL}/api/query`
  - Request body: `{ "question": "..." }`
  - Required header: `x-org-name`
- Displays the model response in a chat-style conversation.

## Environment variables

The UI reads configuration from your project `.env` file using `python-dotenv`:

- `PULSE_API_BASE_URL`  
  Base URL for your FastAPI app (e.g. `http://127.0.0.1:8000`).

- `X_ORG_NAME`  
  Organization name used by the backend middleware (e.g. `pulse-dev`). This is sent as the `x-org-name` header.

Add these additional variables in `.env` (in the project root):

```env
PULSE_API_BASE_URL=http://127.0.0.1:8000
X_ORG_NAME=pulse-dev
GEMINI_API_KEY=your_gemini_key_here
```

> Note: `GEMINI_API_KEY` is used by the backend, not the UI, but is required for end‑to‑end queries to work.

## Install dependencies

From the project root (one level above `UI/`):

```bash
pip install -r requirements.txt
```

This includes `streamlit` and `requests` which the UI uses.

## Run the backend

Start your FastAPI app from the project root:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Confirm that `http://127.0.0.1:8000/docs` is reachable and that the `POST /api/query` endpoint works.

## Run the Streamlit UI

From the `UI` directory:

```bash
cd UI
streamlit run app.py
```

Then open the URL shown in the terminal (usually `http://localhost:8501`).

## How to use

1. Type a question into the input box at the bottom of the chat.
2. Click **Send**.
3. The UI will:
   - Append your message on the right side.
   - Call the FastAPI `/api/query` endpoint with the configured headers.
   - Show the assistant response on the left in a chat bubble.

If you see errors like `Error contacting backend: ...`, check that:

- The backend is running on the same host/port as `PULSE_API_BASE_URL`.
- `X_ORG_NAME` matches a valid org in your backend.
- `GEMINI_API_KEY` is set and the backend can reach the Gemini API.
