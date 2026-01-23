import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class SheetConfig:
    enabled: bool
    sheet_id: Optional[str]
    worksheet: Optional[str]
    mode: str
    credentials_json: Optional[str]


@dataclass
class PaginationConfig:
    next_button_selector: Optional[str]
    disabled_attribute: Optional[str]


@dataclass
class SelectorsConfig:
    username_input: str
    password_input: str
    submit_button: str
    rows_xpath: str
    columns: Dict[str, str]


@dataclass
class AppConfig:
    login_url: str
    players_url: str
    username: str
    password: str
    selectors: SelectorsConfig
    pagination: PaginationConfig
    sheet: SheetConfig
    output_csv: str


def load_config(path: Path) -> AppConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    selectors = raw.get("selectors", {})
    pagination = raw.get("pagination", {})
    sheet = raw.get("sheet", {})
    return AppConfig(
        login_url=raw["login_url"],
        players_url=raw["players_url"],
        username=raw["username"],
        password=raw["password"],
        selectors=SelectorsConfig(
            username_input=selectors["username_input"],
            password_input=selectors["password_input"],
            submit_button=selectors["submit_button"],
            rows_xpath=selectors.get(
                "rows_xpath", "//*[@id='kt_billing_months']/div/table/tbody/tr"
            ),
            columns=selectors["columns"],
        ),
        pagination=PaginationConfig(
            next_button_selector=pagination.get("next_button_selector"),
            disabled_attribute=pagination.get("disabled_attribute"),
        ),
        sheet=SheetConfig(
            enabled=sheet.get("enabled", False),
            sheet_id=_extract_sheet_id(sheet.get("sheet_id") or sheet.get("sheet_url")),
            worksheet=sheet.get("worksheet"),
            mode=sheet.get("mode", "replace"),
            credentials_json=sheet.get("credentials_json"),
        ),
        output_csv=raw.get("output_csv", "output/players.csv"),
    )


def _extract_sheet_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)
    return value


def _extract_text(locator) -> str:
    if locator.count() == 0:
        return ""
    return locator.first.inner_text().strip()


def scrape_rows(config: AppConfig, headless: bool) -> List[Dict[str, str]]:
    rows_data: List[Dict[str, str]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(config.login_url, wait_until="domcontentloaded")
        page.fill(config.selectors.username_input, config.username)
        page.fill(config.selectors.password_input, config.password)
        page.click(config.selectors.submit_button)
        page.wait_for_load_state("networkidle")

        page.goto(config.players_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        while True:
            row_locator = page.locator(f"xpath={config.selectors.rows_xpath}")
            row_count = row_locator.count()
            for index in range(row_count):
                row = row_locator.nth(index)
                record: Dict[str, str] = {}
                for column_name, selector in config.selectors.columns.items():
                    record[column_name] = _extract_text(row.locator(selector))
                rows_data.append(record)

            if not config.pagination.next_button_selector:
                break

            next_button = page.locator(config.pagination.next_button_selector)
            if next_button.count() == 0:
                break

            if config.pagination.disabled_attribute:
                is_disabled = next_button.first.get_attribute(
                    config.pagination.disabled_attribute
                )
                if is_disabled is not None and is_disabled != "false":
                    break

            try:
                next_button.first.click()
                page.wait_for_load_state("networkidle")
            except PlaywrightTimeoutError:
                break

        browser.close()
    return rows_data


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_sheet(config: SheetConfig, rows: List[Dict[str, str]]) -> None:
    if not config.sheet_id:
        raise ValueError("sheet_id or sheet_url is required when sheet is enabled.")
    if not config.credentials_json:
        raise ValueError("credentials_json is required when sheet is enabled.")

    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = Path(config.credentials_json)
    credentials = Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(config.sheet_id)
    worksheet = sheet.worksheet(config.worksheet) if config.worksheet else sheet.sheet1

    headers = list(rows[0].keys()) if rows else []
    values = [headers]
    for row in rows:
        values.append([row.get(header, "") for header in headers])

    if config.mode == "append":
        if values:
            worksheet.append_rows(values, value_input_option="RAW")
    else:
        worksheet.clear()
        if values:
            worksheet.update("A1", values, value_input_option="RAW")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape players and export to Sheets.")
    parser.add_argument(
        "--config", default="config.json", help="Path to config JSON file"
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser with UI (for debugging)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    data = scrape_rows(config, headless=not args.headful)

    if config.sheet.enabled:
        write_sheet(config.sheet, data)
    else:
        write_csv(Path(config.output_csv), data)


if __name__ == "__main__":
    main()
