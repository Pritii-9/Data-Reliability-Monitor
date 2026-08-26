@echo off
cd /d "%~dp0backend"
call .\venv\Scripts\activate
python scripts/run_reconciliation.py --legacy sample_data/test_legacy_transactions.csv --new sample_data/test_new_system_transactions.csv
pause
