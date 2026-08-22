import os
import csv
import random
import time
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "data-pipeline-bucket")

def ensure_bucket_exists():
    """Ensure the target bucket exists in Supabase."""
    try:
        buckets = supabase.storage.list_buckets()
        if BUCKET_NAME not in [b.name for b in buckets]:
            print(f"Bucket {BUCKET_NAME} does not exist. Creating it...")
            supabase.storage.create_bucket(BUCKET_NAME, options={"public": False})
            print(f"Bucket {BUCKET_NAME} created successfully.")
    except Exception as e:
        print(f"Error checking/creating bucket: {e}")

def generate_mock_data(scenario="clean"):
    """
    Generates mock CSV data based on a scenario.
    scenarios: 'clean', 'missing_columns', 'empty_file', 'null_values', 'duplicates'
    """
    headers = ["user_id", "email", "signup_date", "plan_type", "total_spent"]
    
    if scenario == "missing_columns":
        headers = ["user_id", "email", "total_spent"] # Missing signup_date and plan_type
    
    data = []
    
    if scenario == "empty_file":
        return headers, data

    num_rows = random.randint(50, 150)
    
    for i in range(1, num_rows + 1):
        user_id = i
        email = f"user{i}@example.com"
        signup_date = datetime.now().strftime("%Y-%m-%d")
        plan_type = random.choice(["Basic", "Pro", "Enterprise"])
        total_spent = round(random.uniform(10.0, 500.0), 2)
        
        if scenario == "null_values" and random.random() < 0.1:
            # 10% chance to have a null email or plan_type
            if random.random() < 0.5:
                email = ""
            else:
                plan_type = ""
        
        row = [user_id, email, signup_date, plan_type, total_spent]
        
        if scenario == "missing_columns":
            row = [user_id, email, total_spent]
            
        data.append(row)
        
    if scenario == "duplicates":
        # Duplicate the first 5 rows
        if len(data) >= 5:
            data.extend(data[:5])
            
    return headers, data

def upload_to_storage(filename, content_string):
    """Uploads a string content as a file to Supabase Storage."""
    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            file=content_string.encode('utf-8'),
            path=filename,
            file_options={"content-type": "text/csv"}
        )
        print(f"Successfully uploaded {filename} to Supabase Storage")
    except Exception as e:
        print(f"Failed to upload to Supabase: {e}")

def run_simulation():
    """Runs a single iteration of the simulation."""
    ensure_bucket_exists()
    
    # Randomly pick a scenario to simulate real-world data issues
    # 50% chance of clean data, 50% chance of some failure
    scenarios = ["clean", "clean", "clean", "clean", "clean", 
                 "missing_columns", "empty_file", "null_values", "duplicates", "wrong_naming"]
    
    scenario = random.choice(scenarios)
    print(f"Running simulation with scenario: {scenario}")
    
    headers, data = generate_mock_data(scenario)
    
    # Generate CSV string
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    if headers:
        writer.writerow(headers)
    writer.writerows(data)
    csv_content = output.getvalue()
    
    # Determine filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"daily_users_{timestamp}.csv"
    
    if scenario == "wrong_naming":
        filename = f"backup_data_{timestamp}.csv"
        
    upload_to_storage(filename, csv_content)

if __name__ == "__main__":
    print("Starting ingestion simulator...")
    # Run once immediately
    run_simulation()
    

