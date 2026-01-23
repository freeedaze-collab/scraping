# Player scraping tool

This tool logs into the affiliate dashboard, scrapes the players table, and exports the data to Google Sheets or a CSV file.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Copy the example configuration and update selectors/credentials:

```bash
cp config.example.json config.json
```

## Run

```bash
python src/scrape_players.py --config config.json
```

Use `--headful` when you want to watch the browser for debugging:

```bash
python src/scrape_players.py --config config.json --headful
```

## Google Sheets export

To write directly to Google Sheets:

1. Create a Google Cloud project and a **service account**.
2. Download the service account JSON key.
3. Share your target spreadsheet with the service account email.
4. Set `sheet.enabled` to `true` and point `credentials_json` to the key file.

If Sheets export is disabled, the script writes a CSV file to `output/players.csv`.

## Scheduling

For daily execution at 00:00, use your OS scheduler.

### macOS/Linux (cron)

```bash
crontab -e
```

Add:

```
0 0 * * * /path/to/.venv/bin/python /path/to/scraping/src/scrape_players.py --config /path/to/scraping/config.json
```

### Windows (Task Scheduler)

1. Create a new task.
2. Trigger: Daily at 00:00.
3. Action: Start a program
   - Program: `C:\path\to\python.exe`
   - Arguments: `C:\path\to\scraping\src\scrape_players.py --config C:\path\to\scraping\config.json`

## Notes

- The default selectors in `config.example.json` match the current Players table layout you shared.
- Pagination is handled by `pagination.next_button_selector`. Update it if the Next button differs.
