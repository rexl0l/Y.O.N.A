# Schedule nightly spreadsheet clear

The script `clear_sheet_nightly.py` clears all order data from the spreadsheet. Run it once per night.

## Option 1: Windows Task Scheduler (your machine)

1. Open **Task Scheduler** → Create Basic Task
2. Name: `Clear Order Sheet`
3. Trigger: **Daily** at midnight (or your preferred time)
4. Action: **Start a program**
   - Program: `python` (or full path to `python.exe`)
   - Arguments: `clear_sheet_nightly.py`
   - Start in: `C:\Users\yonad\IdeaProjects\yourordernumberassistant`

## Option 2: GitHub Actions (runs in the cloud)

1. Push the repo to GitHub (if not already)
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Add secret `GSHEETS_SERVICE_ACCOUNT_JSON`:
   - Create a JSON file from your Google service account (from Google Cloud Console)
   - Paste the entire JSON as the secret value
4. The workflow runs every night at midnight UTC

To run manually: **Actions** → **Clear Sheet Nightly** → **Run workflow**

## Test the script

```powershell
cd C:\Users\yonad\IdeaProjects\yourordernumberassistant
python clear_sheet_nightly.py
```

This clears the sheet immediately. Use with care.
