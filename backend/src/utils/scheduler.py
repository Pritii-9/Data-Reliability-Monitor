import schedule
import time
from datetime import datetime
from src.utils.ingestion_simulator import run_simulation
from src.engine.pipeline_monitor import run_pipeline_monitor

def job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚙️ Waking up scheduler...")
    
    try:
        print("--> Step 1: Simulating Data Ingestion...")
        run_simulation()
    except Exception as e:
        print(f"Error during ingestion simulation: {e}")
        
    time.sleep(2)
    
    try:
        print("--> Step 2: Running Pipeline Monitor...")
        run_pipeline_monitor()
    except Exception as e:
        print(f"Error during pipeline monitoring: {e}")
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Job complete. Going back to sleep.\n")

if __name__ == "__main__":
    print("🚀 Starting Continuous Automation Scheduler...")
    print("Press Ctrl+C to stop.")
    
    job()
    schedule.every(1).minutes.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)
