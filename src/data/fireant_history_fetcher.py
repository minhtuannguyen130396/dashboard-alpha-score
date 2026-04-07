import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import requests
from dateutil.relativedelta import relativedelta

TOKEN_ENV_VAR = "FIREANT_BEARER_TOKEN"
TOKEN_FILE = Path("access_token.txt")
BASE_URL_TEMPLATE = "https://restv2.fireant.vn/symbols/{share_code}/historical-quotes"
IS_FETCH_ALL_DATA = True
IS_WEEKLY_FETCH = True
DATE_START_FETCH = "2010-01-01"
LIST_VN_30 = "Stock_List\\stock_vn_30.json"
LIST_MID_CAB = "Stock_List\\stock_mid_cab.json"
LIST_LARGE_CAB = "Stock_List\\stock_large_cab.json"
LIST_OTHER = "Stock_List\\stock_other.json"
LIST_ALL_STOCK = "Stock_List\\list_all_stock.json"

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+")


def load_bearer_token() -> str:
    token = os.getenv(TOKEN_ENV_VAR, "").strip()
    if token:
        return token

    if TOKEN_FILE.exists():
        raw_text = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if raw_text:
            match = JWT_PATTERN.search(raw_text)
            if match:
                return match.group(0)
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            if len(lines) == 1:
                return lines[0]

    raise RuntimeError(
        f"Missing FireAnt token. Set {TOKEN_ENV_VAR} or provide {TOKEN_FILE}."
    )


def build_headers():
    return {
        "Authorization": f"Bearer {load_bearer_token()}",
        "Accept": "application/json",
    }


def load_stocks_from_txt(path=LIST_MID_CAB):
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read().strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        stocks = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 2:
                stocks.append({"share_code": parts[0], "ipo_date": parts[1]})
        return stocks


def end_of_month(value: date) -> date:
    first_next = value.replace(day=1) + relativedelta(months=1)
    return first_next - timedelta(days=1)


def _resolve_fetch_start_date(
    stock_ipo_date: date,
    update_mode: Literal["from_start", "previous_month"],
) -> date:
    if update_mode == "from_start":
        return max(datetime.strptime(DATE_START_FETCH, "%Y-%m-%d").date(), stock_ipo_date)
    if update_mode == "previous_month":
        first_day_current_month = date.today().replace(day=1)
        first_day_previous_month = first_day_current_month - relativedelta(months=1)
        return max(first_day_previous_month, stock_ipo_date)
    raise ValueError(f"Unsupported update_mode: {update_mode}")


def fetch_all_stock_history(update_mode: Literal["from_start", "previous_month"] = "from_start"):
    list_stock_name = []

    if IS_FETCH_ALL_DATA:
        for file_stock_name in [LIST_VN_30, LIST_MID_CAB, LIST_LARGE_CAB, LIST_OTHER]:
            for name in load_stocks_from_txt(file_stock_name):
                list_stock_name.append(name)
    else:
        for name in load_stocks_from_txt(LIST_ALL_STOCK):
            list_stock_name.append(name)

    print(f"Total stocks to fetch: {len(list_stock_name)}")
    today = date.today()

    for stock in list_stock_name:
        symbol = stock["share_code"]
        ipo = datetime.strptime(stock["ipo_date"], "%Y-%m-%d").date()
        current = _resolve_fetch_start_date(ipo, update_mode)

        base_dir = os.path.join(os.getcwd(), "data", symbol)
        os.makedirs(base_dir, exist_ok=True)

        while current <= today:
            eom = end_of_month(current)
            end_date = eom if eom <= today else today
            print(f"Fetching data for {symbol} from {current} to {end_date}")
            if current > end_date:
                break

            days_count = (end_date - current).days + 1
            params = {
                "startDate": current.isoformat(),
                "endDate": end_date.isoformat(),
                "offset": 0,
                "limit": days_count,
            }

            url = BASE_URL_TEMPLATE.format(share_code=symbol)
            response = requests.get(
                url,
                headers=build_headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            year_dir = os.path.join(base_dir, str(current.year))
            os.makedirs(year_dir, exist_ok=True)
            filepath = os.path.join(year_dir, f"{current.isoformat()}.json")
            with open(filepath, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)

            print(f"{symbol} done get data at {end_date}")
            current = current.replace(day=1) + relativedelta(months=1)

    print("All data fetched successfully.")


fetch_all_data = fetch_all_stock_history
