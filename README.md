# \# Employee Attendance \& Analytics API

# 

# A backend application for employee attendance management and analytics, built using \*\*FastAPI\*\*, \*\*Python\*\*, and \*\*MongoDB\*\*.

# 

# \## Features

# 

# \- Employee creation and listing with pagination.

# \- Attendance punch-in and punch-out.

# \- Attendance record correction with audit history.

# \- Employee monthly attendance analytics.

# \- Department-wise attendance summaries.

# \- Late-comer leaderboard with ranking and tie handling.

# \- Department attendance trends with a seven-day moving average.

# \- MongoDB indexes and query explain endpoint.

# 

# \## Tech Stack

# 

# \- Python 3.11+

# \- FastAPI

# \- PyMongo

# \- MongoDB

# \- Pydantic

# \- Uvicorn

# 

# \## Setup and Run

# 

# 1\. Install dependencies:

# 

# &#x20;  ```bash

# &#x20;  pip install -r requirements.txt

# &#x20;  ```

# 

# 2\. Configure the environment variables `MONGO\_URI` and `MONGO\_DB` with your MongoDB connection details.

# 

# 3\. Start the application:

# 

# &#x20;  ```bash

# &#x20;  uvicorn app.main:app --port 8000

# &#x20;  ```

# 

# 4\. Open `http://127.0.0.1:8000/docs` to explore the API documentation.

# 

# \## Project Structure

# 

# ```text

# .

# ├── app/

# │   ├── \_\_init\_\_.py

# │   └── main.py

# ├── requirements.txt

# ├── README.md

# ├── REVIEW.md

# └── DECISIONS.md

# ```

# 

# \## Notes

# 

# The application follows the attendance rules and API contract provided in the engineering assignment. Configure MongoDB before running the application and test the endpoints against the supplied data.

