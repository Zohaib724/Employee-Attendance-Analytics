# Employee Attendance & Analytics API

FastAPI and MongoDB backend for employee attendance, manual regularization, and analytics. The implementation follows `openapi.yaml` and the storage conventions in `DATA_MODEL.md`.

## Requirements

- Python 3.11+
- MongoDB 6.0+

## Run locally

Install dependencies from the repository root:

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set the MongoDB connection settings in your shell (or an untracked local `.env` file). Environment variables take precedence over `.env` values.

Windows PowerShell:

```powershell
$env:MONGO_URI = "mongodb://localhost:27017"
$env:MONGO_DB = "attendance_db"
uvicorn app.main:app --port 8000
```

macOS/Linux:

```bash
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB="attendance_db"
uvicorn app.main:app --port 8000
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation. `GET /health` checks MongoDB connectivity. Required indexes are created at application startup.

## Repository notes

- Do not commit `.env`, MongoDB credentials, virtual environments, or database dumps.
- `REVIEW.md` records the starter-code review. `DECISIONS.md` summarizes the design choices.
