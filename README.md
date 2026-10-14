# Employee Attendance & Analytics API

A backend application for employee attendance management and analytics built using **Python, FastAPI, and MongoDB**.

## Features

- Create and list employees with pagination and department filtering.
- Record employee attendance through punch-in and punch-out endpoints.
- Calculate work hours, late minutes, overtime, and half-day status.
- Correct attendance records with an audit history.
- Generate monthly employee attendance summaries.
- Generate department-wise attendance summaries.
- Rank employees by late arrivals, including tie handling.
- Generate department attendance trends with a seven-day moving average.
- Create MongoDB indexes for efficient queries.
- Inspect query execution plans using the explain endpoint.

## Tech Stack

- **Language:** Python 3.11+
- **Backend Framework:** FastAPI
- **Database:** MongoDB
- **Database Driver:** PyMongo
- **Validation:** Pydantic
- **ASGI Server:** Uvicorn

## Project Structure

```text
attendance_api_submission/
├── app/
│   ├── __init__.py
│   └── main.py
├── requirements.txt
├── README.md
├── REVIEW.md
└── DECISIONS.md
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/Zohaib724/Employee-Attendance-Analytics.git
cd Employee-Attendance-Analytics
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure MongoDB

Set the following environment variables with your MongoDB connection details:

- `MONGO_URI` — MongoDB connection URI.
- `MONGO_DB` — Database name.

Ensure that MongoDB is running and accessible before starting the application.

### 4. Start the application

```bash
uvicorn app.main:app --port 8000
```

### 5. Access the API

Once the server is running, visit:

- **Interactive API documentation:** http://127.0.0.1:8000/docs
- **Health check:** http://127.0.0.1:8000/health

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check database connectivity |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List and filter employees |
| POST | `/attendance/punch-in` | Record employee punch-in |
| GET | `/attendance` | List attendance records |
| POST | `/attendance/punch-out` | Record punch-out and calculate work hours |
| PATCH | `/attendance/{emp_code}/{date}` | Regularize an attendance record |
| GET | `/analytics/employees/{emp_code}/monthly` | Monthly employee summary |
| GET | `/analytics/departments/summary` | Department attendance summary |
| GET | `/analytics/leaderboard/late` | Late-comer leaderboard |
| GET | `/analytics/departments/{department}/trend` | Department attendance trend |
| GET | `/admin/explain/{endpoint}` | Inspect MongoDB query execution plans |

## Documentation

- `REVIEW.md` — Code review findings and fixes.
- `DECISIONS.md` — Technical decisions and design explanations.

## Notes

The API is designed to follow the engineering assignment's attendance rules, validation requirements, and MongoDB data model. Configure the database before running the application and verify the endpoints with the supplied sample data.
