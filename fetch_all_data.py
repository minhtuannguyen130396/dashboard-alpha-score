import os
import json
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import requests

# ------ Cấu hình chung ------
BEARER_TOKEN      = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoyMDUxMjk1NTI4LCJuYmYiOjE3NTEyOTU1MjgsImNsaWVudF9pZCI6ImZpcmVhbnQud2ViIiwic2NvcGUiOlsib3BlbmlkIiwicHJvZmlsZSIsInJvbGVzIiwiZW1haWwiLCJhY2NvdW50cy1yZWFkIiwiYWNjb3VudHMtd3JpdGUiLCJvcmRlcnMtcmVhZCIsIm9yZGVycy13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImZpbmFuY2UtcmVhZCIsInBvc3RzLXdyaXRlIiwicG9zdHMtcmVhZCIsInN5bWJvbHMtcmVhZCIsInVzZXItZGF0YS1yZWFkIiwidXNlci1kYXRhLXdyaXRlIiwidXNlcnMtcmVhZCIsInNlYXJjaCIsImFjYWRlbXktcmVhZCIsImFjYWRlbXktd3JpdGUiLCJibG9nLXJlYWQiLCJpbnZlc3RvcGVkaWEtcmVhZCJdLCJzdWIiOiI4OWNmNTRiMy1kN2RkLTQyN2QtODI1NC0wZWU5MTE3ZDc2YjQiLCJhdXRoX3RpbWUiOjE3NTEyOTU1MjgsImlkcCI6Ikdvb2dsZSIsIm5hbWUiOiJtaW5odHVhbi5uZ3V5ZW4xMzAzOTZAZ21haWwuY29tIiwic2VjdXJpdHlfc3RhbXAiOiI2OTgyMDEzMy0xNTkwLTQwZDEtYjQyNC1hNDQ5Y2I3Mzk1OWIiLCJqdGkiOiI1OTlmZDA0ZmQ1OTVhMmU5YjBiYzhlZjhhNjY2YjY4NyIsImFtciI6WyJleHRlcm5hbCJdfQ.kjkBVCtjOD_4DEpSWVl7mwlCslG4-g275KaLBMTHfDhRumyNQx2wwkvWRH4DsWQWEpJohTHbxdlNRAXzCViGFg0tvAeOWyg408Ho27BGgD5CXYHLJFuPhq7sPP_TYplGQ5wnglxd35VfaVBllQr69hD7dC1omAPjBLLo93MqDU8n5_Z_yCPbFasKceMUncGOLPpI4sgEVTlM_XJsxgpp5qsX1RnxMeLJRHNJrSpqKPzf1Pw-5qL37EBqXlH_sp5sshS-_oyH1fFiNjYHnKu3bAzQal7oVW5jRD5qocjkU2a2hfjaJW0AcDmfDGafenv-mT7koCo-kbaWC_JCCxuPfQ'
BASE_URL_TEMPLATE = 'https://restv2.fireant.vn/symbols/{share_code}/historical-quotes'
HEADERS           = {
    'Authorization': f'Bearer {BEARER_TOKEN}',
    'Accept'       : 'application/json'
}

def load_stocks_from_txt(path='stock_list.txt'):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        stocks = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                stocks.append({
                    'share_code': parts[0],
                    'ipo_date'  : parts[1]
                })
        return stocks

def end_of_month(d: date) -> date:
    """Trả về ngày cuối cùng của tháng chứa d."""
    first_next = d.replace(day=1) + relativedelta(months=1)
    return first_next - timedelta(days=1)

# Load danh sách
stocks = load_stocks_from_txt()
today  = date.today()

for stock in stocks:
    symbol     = stock['share_code']
    ipo        = datetime.strptime(stock['ipo_date'], '%Y-%m-%d').date()
    # bắt đầu từ IPO
    #current = ipo
    current = datetime.strptime('2024-01-01', '%Y-%m-%d').date()

    base_dir = os.path.join(os.getcwd(), 'data', symbol)
    os.makedirs(base_dir, exist_ok=True)

    while current <= today:
        # tính end_date = cuối tháng hoặc today nếu vượt
        eom       = end_of_month(current)
        end_date  = eom if eom <= today else today
        print(f"Fetching data for {symbol} from {current} to {end_date}")
        # nếu không còn ngày nào cần lấy → break
        if current > end_date:
            break

        # số ngày trong khoảng để làm limit
        days_count = (end_date - current).days + 1

        params = {
            'startDate': current.isoformat(),
            'endDate'  : end_date.isoformat(),
            'offset'   : 0,
            'limit'    : days_count
        }

        url  = BASE_URL_TEMPLATE.format(share_code=symbol)
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        # lưu file JSON
        year_dir = os.path.join(base_dir, str(current.year))
        os.makedirs(year_dir, exist_ok=True)
        filename = f"{current.isoformat()}.json"
        filepath = os.path.join(year_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

        now_str = datetime.now().isoformat(sep=' ', timespec='seconds')
        print(f"{symbol} done get data at {end_date}")

        # sang tháng tiếp theo: ngày 1 của tháng kế
        next_month_start = (current.replace(day=1) + relativedelta(months=1))
        current = next_month_start
