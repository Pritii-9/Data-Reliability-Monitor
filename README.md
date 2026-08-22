# Data Reliability Monitor

A portfolio project built to show how I handle data quality, pipeline monitoring, and incident management. I built this to demonstrate core Data Engineering concepts for my job applications.

## 🏗️ Architecture

```text
[ Data Generator ] --> (Uploads CSV) --> [ Supabase Storage ]
                                                 |
                                                 v
[ Pipeline Monitor ] <--- (Validates Data) ---- |
       |
       |--(Pass)-------> Moves file to /processed
       |--(Fail)-------> Moves file to /quarantine
       |
       |--(Logs Results)--> [ PostgreSQL / SQLite DB ]
       |
       |--(On Failure)----> [ Ticketing System ]
                                       |
                                       |--> [ Email Alerts (Manual Trigger) ]
                                       |
[ Streamlit Dashboard ] <----------------------
```

## 🛠️ Tech Stack
- **Python 3.11+**
- **Supabase**: For cloud object storage (handling our CSV data lake).
- **SQLAlchemy & SQLite/Postgres**: For storing tickets and pipeline run metadata.
- **Streamlit**: For the monitoring dashboard and manual testing UI.
- **smtplib**: For sending HTML email alerts when bad data is caught.

## 🚀 Setup & Execution

### 1. Environment Setup
Copy `.env.example` to `.env` and fill in your credentials.
You will need to get your Supabase URL and Secret Key from your Supabase project settings.

### 2. Email Alerts
To enable email alerts, use a Gmail App Password:
1. Go to Google Account -> Security -> 2-Step Verification -> App passwords.
2. Create a new password and put it in `SMTP_APP_PASSWORD` in your `.env`.
3. Set `SMTP_EMAIL` and `ALERT_RECIPIENT`.
*(Note: To prevent spam, emails only send when you manually upload a file via the dashboard. The background scheduler creates tickets silently).*

### 3. Database
If you just want to run this locally, the code defaults to a local SQLite database (`monitor.db`). 
If you want to run Postgres, you can spin it up with `docker-compose up -d`.

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Running the Pipeline
I wrote a background scheduler that acts like a cron job. It generates mock data and audits it every 1 minute.
```bash
python scheduler.py
```
*(Check your Supabase storage bucket to watch files move into the `processed` and `quarantine` folders automatically!)*

### 6. Start the Dashboard
```bash
streamlit run dashboard.py
```
From the dashboard, you can view the incident queue, resolve tickets, and use the Manual Testing sidebar to upload your own broken CSVs and trigger real-time email alerts.

## 📖 Runbooks
In the `runbooks/` folder, I wrote Standard Operating Procedures (SOPs) for handling common data failures (nulls, schema mismatches, duplicates). This matches how a real on-call engineering team handles incident tickets.
