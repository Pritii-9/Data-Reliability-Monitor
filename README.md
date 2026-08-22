# Data Reliability Monitor

A portfolio project demonstrating core Data Engineering concepts: data pipeline monitoring, validation, incident management, and basic cloud storage interactions. Built for a Junior Data Engineer job application.

## 🏗️ Architecture

```text
[ Data Generator ] --> (Uploads CSV) --> [ AWS S3 (MinIO) ]
                                                |
                                                v
[ Pipeline Monitor ] <--- (Validates Data) ---- |
       |
       |--(Logs Results)--> [ PostgreSQL / SQLite DB ]
       |
       |--(On Failure)----> [ Ticketing System ]
                                      |
                                      |--> [ Email Alerts (SMTP) ]
                                      |
[ Streamlit Dashboard ] <----------------------
```

## 🛠️ Tech Stack
- **Python 3.11+**
- **MinIO**: For simulating cloud object storage locally via Docker.
- **SQLAlchemy & SQLite/Postgres**: For data models and storage.
- **Streamlit**: For building the data quality dashboard.
- **smtplib**: For automated email alerting.

## 🚀 Setup & Execution (Local)

### 1. Environment Setup
Copy the `.env.example` file to a new file named `.env`:
```bash
cp .env.example .env
```

### 2. Email Alerting Setup (Gmail)
To enable email alerts, you must use a Gmail App Password:
1. Go to your Google Account -> Security.
2. Enable **2-Step Verification**.
3. Go to **App passwords**.
4. Create a new app password (e.g., call it "Python Data Monitor").
5. Paste the 16-character password into `SMTP_APP_PASSWORD` in your `.env` file.
6. Set `SMTP_EMAIL` to your Gmail address and `ALERT_RECIPIENT` to the destination email.

### 3. Run with Docker Compose
To spin up MinIO (mock S3) and Postgres:
```bash
docker-compose up -d
```
*(You can access the MinIO console at http://localhost:9001 using `minioadmin` / `minioadmin`)*

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```
*(You will need `boto3`, `pandas`, `sqlalchemy`, `streamlit`, `python-dotenv`)*

### 5. Running the Pipeline (Automated)
Instead of running scripts manually, you can start the automated scheduler. This script will run in the background, simulating data ingestion and auditing it continuously every 1 minute.
```bash
python scheduler.py
```

### 6. Start the Dashboard
```bash
streamlit run dashboard.py
```

## 📖 Runbooks
In the `runbooks/` directory, you will find Standard Operating Procedures (SOPs) for handling common pipeline failures. These represent how a real engineering team handles incident tickets.
