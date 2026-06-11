#!/usr/bin/env python3
"""
fetch_emerging_revenue.py
-------------------------
從公開資訊觀測站 MOPS 興櫃月營收總表爬取當月/上月/去年同月營收，
自行計算興櫃公司月營收 YoY%/MoM%，
補充 fetch_monthly_revenue.py（FinMind）未覆蓋的興櫃公司，
寫入 investment.db 的 monthly_revenue_summary 表。

資料來源：https://mopsov.twse.com.tw/nas/t21/rotc/
URL 規則：t21sc03_{民國年}_{月}_0.html
  例：https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_115_4_0.html
資料欄位：公司代號 | 公司名稱 | 當月營收 | 上月營收 | 去年當月營收 | ...

6 個月滾動邏輯：
  每次從 MOPS 往回找最新可用月份(P0)，並抓前一個月(P1)，
  與 DB 現有資料合併，保留最近 6 個月。
  若興櫃資料來源不足 6 個月，左側月份欄位保留 NULL，前端顯示「-」。
  執行方式：
    cd 台股投資資訊系統_完整專案/上市櫃公司徵人需求度
    ./venv/bin/python3 fetch_emerging_revenue.py
"""

import os
import re
import sys
import sqlite3
import logging
import subprocess
import argparse
import json
import urllib3
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── 路徑 ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get('HIRING_PROJECT_ROOT', BASE_DIR.parent)).resolve()
STAGE3_DIR = Path(os.environ.get('HIRING_STAGE3_DIR', BASE_DIR / 'stage3_web')).resolve()
DB_PATH = Path(os.environ.get('DB_PATH', STAGE3_DIR / 'investment.db'))
LOG_PATH = BASE_DIR / 'logs' / 'fetch_emerging_revenue.log'

MOPS_ROTC_URL_TEMPLATE = 'https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_{roc_year}_{month}_0.html'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://mopsov.twse.com.tw/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}
REVENUE_MONTH_COUNT = 6
LATEST_MONTH_LOOKBACK = 12


def iter_revenue_fields():
    for index in range(1, REVENUE_MONTH_COUNT + 1):
        yield f'm{index}_label', 'TEXT'
        yield f'm{index}_mom', 'REAL'
        yield f'm{index}_yoy', 'REAL'

# ── Logging ──────────────────────────────────────────────────────────────
LOG_PATH.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ── 解析頁面 ─────────────────────────────────────────────────────────────
def roc_year(year: int) -> int:
    return year - 1911


def build_mops_rotc_url(year: int, month: int) -> str:
    return MOPS_ROTC_URL_TEMPLATE.format(roc_year=roc_year(year), month=month)


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def iter_recent_month_candidates(anchor: datetime | None = None,
                                 lookback: int = LATEST_MONTH_LOOKBACK) -> list[tuple[int, int]]:
    current = anchor or datetime.now()
    return [add_months(current.year, current.month, -offset) for offset in range(lookback)]


def decode_mops_html(html: bytes | str) -> str:
    if isinstance(html, str):
        return html
    for encoding in ('big5', 'cp950', 'utf-8'):
        try:
            return html.decode(encoding)
        except UnicodeDecodeError:
            continue
    return html.decode('big5', errors='ignore')


def parse_amount(value: str) -> int | None:
    text = value.strip().replace(',', '').replace('\u3000', '')
    if text in ('', '--', 'N/A', '-', '－'):
        return None
    text = re.sub(r'[^\d\-.]', '', text)
    if text in ('', '-', '.', '-.'):
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def calculate_pct(current: int | None, base: int | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return round((current - base) / base * 100, 2)


def parse_mops_rotc_page(html: bytes | str) -> tuple[str | None, dict[str, dict]]:
    """
    回傳 (月份標籤, {stock_code: {'mom': float|None, 'yoy': float|None}})
    月份標籤格式：'YYYY/M'（如 '2026/3'）
    """
    soup = BeautifulSoup(decode_mops_html(html), 'html.parser')
    text = soup.get_text()

    m = re.search(r'興櫃公司\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月份', text)
    if not m:
        m = re.search(r'資料年月\s*(\d{2,3})/(\d{1,2})', text)
    if not m:
        return None, {}
    roc_y, month = int(m.group(1)), int(m.group(2))
    label = f'{roc_y + 1911}/{month}'

    data: dict[str, dict] = {}
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        code = cells[0].get_text(strip=True)
        if not re.fullmatch(r'\d{4}', code):
            continue
        # 欄位順序：公司代號, 公司名稱, 當月營收, 上月營收, 去年當月營收, ...
        current_revenue = parse_amount(cells[2].get_text(strip=True))
        previous_revenue = parse_amount(cells[3].get_text(strip=True))
        last_year_revenue = parse_amount(cells[4].get_text(strip=True))
        mom = calculate_pct(current_revenue, previous_revenue)
        yoy = calculate_pct(current_revenue, last_year_revenue)
        data[code] = {'mom': mom, 'yoy': yoy}

    return label, data


def parse_page(html: bytes) -> tuple[str | None, dict[str, dict]]:
    """Backward-compatible wrapper for older tests/imports."""
    return parse_mops_rotc_page(html)


def fetch_mops_rotc_month(year: int, month: int) -> tuple[str | None, dict[str, dict], str]:
    url = build_mops_rotc_url(year, month)
    resp = requests.get(url, headers=HEADERS, verify=False, timeout=45)
    resp.raise_for_status()
    label, data = parse_mops_rotc_page(resp.content)
    return label, data, url


# ── 爬取 MOPS 興櫃最新月份 ───────────────────────────────────────────────
def fetch_all_industries() -> dict[int, tuple[str | None, dict[str, dict]]]:
    """
    回傳 {period: (label, {code: {mom, yoy}})}
    period 0 = MOPS 最新可用月份, 1 = 前月
    """
    period_data: dict[int, tuple[str | None, dict[str, dict]]] = {0: (None, {}), 1: (None, {})}
    latest_month: tuple[int, int] | None = None

    for year, month in iter_recent_month_candidates():
        try:
            label, data, url = fetch_mops_rotc_month(year, month)
        except Exception as e:
            logger.warning(f'MOPS ROTC {year}/{month} 取得失敗: {e}')
            continue
        if label and data:
            period_data[0] = (label, data)
            latest_month = (year, month)
            logger.info(f'Period 0 ({label}): {len(data)} 家公司 source={url}')
            break
        logger.info(f'MOPS ROTC {year}/{month} 尚無可解析資料')

    if latest_month:
        prev_year, prev_month = add_months(latest_month[0], latest_month[1], -1)
        try:
            label, data, url = fetch_mops_rotc_month(prev_year, prev_month)
            if label and data:
                period_data[1] = (label, data)
            logger.info(f'Period 1 ({label}): {len(data)} 家公司 source={url}')
        except Exception as e:
            logger.warning(f'MOPS ROTC 前月 {prev_year}/{prev_month} 取得失敗: {e}')

    return period_data


# ── DB：讀取現有資料 ──────────────────────────────────────────────────────
def load_existing(conn: sqlite3.Connection) -> dict[str, dict]:
    """回傳 {stock_code: {m1_label, m1_mom, ..., m6_yoy}}"""
    try:
        rows = conn.execute('SELECT * FROM monthly_revenue_summary').fetchall()
        return {r['stock_code']: dict(r) for r in rows}
    except Exception:
        return {}


# ── 6 個月合併邏輯 ────────────────────────────────────────────────────────
def month_sort_key(label: str) -> tuple[int, int]:
    y, m = label.split('/')
    return (int(y), int(m))


def merge_6months(existing: dict | None,
                  new_data: dict[str, dict]) -> dict:
    """
    existing: DB 現有欄位 dict（或 None）
    new_data: {'2026/3': {mom, yoy}, '2026/2': {mom, yoy}, ...}
    回傳: {m1_label, m1_mom, ... m6_yoy}（由舊到新；不足六個月時左側補 NULL）
    """
    all_months: dict[str, dict] = {}

    # 先放現有資料
    if existing:
        for i in range(1, REVENUE_MONTH_COUNT + 1):
            lbl = existing.get(f'm{i}_label')
            if lbl:
                all_months[lbl] = {
                    'mom': existing.get(f'm{i}_mom'),
                    'yoy': existing.get(f'm{i}_yoy'),
                }

    # 新資料覆蓋（同月份取最新值）
    all_months.update(new_data)

    # 排序後取最近 6 個月（由新到舊取6，再反轉為舊到新）
    sorted_months = sorted(
        all_months.items(),
        key=lambda x: month_sort_key(x[0]),
        reverse=True
    )[:REVENUE_MONTH_COUNT]
    sorted_months.reverse()  # 由舊到新：m1 ... m6

    padded_months: list[tuple[str | None, dict]] = [(None, {})] * (REVENUE_MONTH_COUNT - len(sorted_months))
    padded_months.extend(sorted_months)

    result: dict = {}
    for i, (lbl, d) in enumerate(padded_months):
        result[f'm{i+1}_label'] = lbl
        result[f'm{i+1}_mom'] = d.get('mom')
        result[f'm{i+1}_yoy'] = d.get('yoy')
    return result


# ── 寫入 DB ──────────────────────────────────────────────────────────────
def ensure_table(conn: sqlite3.Connection):
    revenue_columns = ",\n            ".join(f"{field} {field_type}" for field, field_type in iter_revenue_fields())
    conn.execute('''
        CREATE TABLE IF NOT EXISTS monthly_revenue_summary (
            stock_code  TEXT PRIMARY KEY,
            ''' + revenue_columns + ''',
            updated_at  TEXT
        )
    ''')
    existing_columns = {row[1] for row in conn.execute('PRAGMA table_info(monthly_revenue_summary)')}
    for field, field_type in iter_revenue_fields():
        if field not in existing_columns:
            conn.execute(f'ALTER TABLE monthly_revenue_summary ADD COLUMN {field} {field_type}')
    conn.commit()


def save_emerging(conn: sqlite3.Connection,
                  period_data: dict[int, tuple],
                  existing: dict[str, dict],
                  updated_at: str) -> int:
    """
    只更新 monthly_revenue_summary 中尚未有資料、或資料來自興櫃的公司。
    回傳寫入筆數。
    """
    p0_label, p0_data = period_data[0]
    p1_label, p1_data = period_data[1]

    # 合併兩個期別的所有代碼
    all_codes = set(p0_data.keys()) | set(p1_data.keys())

    rows = []
    for code in all_codes:
        new_months: dict[str, dict] = {}
        if p0_label and code in p0_data:
            new_months[p0_label] = p0_data[code]
        if p1_label and code in p1_data:
            new_months[p1_label] = p1_data[code]

        merged = merge_6months(existing.get(code), new_months)
        values = [code]
        for index in range(1, REVENUE_MONTH_COUNT + 1):
            values.extend([
                merged[f'm{index}_label'],
                merged[f'm{index}_mom'],
                merged[f'm{index}_yoy'],
            ])
        values.append(updated_at)
        rows.append(tuple(values))

    revenue_field_names = [field for field, _ in iter_revenue_fields()]
    insert_columns = ['stock_code', *revenue_field_names, 'updated_at']
    placeholders = ', '.join('?' for _ in insert_columns)
    conn.executemany('''
        INSERT OR REPLACE INTO monthly_revenue_summary
            (''' + ', '.join(insert_columns) + ''')
        VALUES (''' + placeholders + ''')
    ''', rows)
    conn.commit()
    return len(rows)


# ── git commit + push ────────────────────────────────────────────────────
def git_commit_and_push(updated_at: str, *, skip_git: bool = False):
    if skip_git or os.environ.get('HIRING_REVENUE_SKIP_GIT', '').lower() in {'1', 'true', 'yes'}:
        logger.info('skip git enabled，略過 emerging revenue git commit/push')
        return
    if not (STAGE3_DIR / '.git').exists():
        logger.error(f'內部 stage3_web 尚未初始化 Git repo，停止 emerging revenue commit/push: {STAGE3_DIR}')
        return
    try:
        repo_dir = STAGE3_DIR
        subprocess.run(['git', 'add', 'investment.db'],
                       cwd=repo_dir, check=True, capture_output=True)
        msg = f'chore: 補充興櫃月營收 MoM%/YoY% {updated_at[:10]}'
        result = subprocess.run(
            ['git', 'commit', '-m', msg],
            cwd=repo_dir, capture_output=True, text=True
        )
        if result.returncode != 0 and 'nothing to commit' in result.stdout + result.stderr:
            logger.info('investment.db 無變更，跳過 commit')
            return
        result.check_returncode()
        subprocess.run(['git', 'push', 'origin', 'main'],
                       cwd=repo_dir, check=True, capture_output=True)
        logger.info('git commit + push 完成')
    except subprocess.CalledProcessError as e:
        logger.error(f'git 操作失敗: {e.stderr}')


def write_receipt(
    path: Path,
    *,
    started_at: str,
    updated_at: str,
    p0_label: str | None,
    p1_label: str | None,
    p0_count: int,
    p1_count: int,
    written: int,
    skip_git: bool,
    gate_result: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        'receipt_type': 'emerging_monthly_revenue_fetch_receipt',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'started_at': started_at,
        'updated_at': updated_at,
        'source': 'MOPS_ROTC',
        'period_0_label': p0_label,
        'period_1_label': p1_label,
        'period_0_company_count': p0_count,
        'period_1_company_count': p1_count,
        'written_count': written,
        'db_path': str(DB_PATH),
        'skip_git': skip_git,
        'gate_result': gate_result,
        'typed_blockers': [],
    }
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Fetch emerging monthly revenue summary into investment.db.')
    parser.add_argument('--skip-git', action='store_true', help='Do not git commit/push after updating investment.db.')
    parser.add_argument('--output-receipt', default='', help='Optional JSON receipt path.')
    return parser


# ── 主程式 ───────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None):
    from datetime import datetime
    args = build_parser().parse_args(argv)
    logger.info('=== fetch_emerging_revenue (MOPS_ROTC) 開始 ===')
    started_at = datetime.now().isoformat(timespec='seconds')

    period_data = fetch_all_industries()

    p0_label = period_data[0][0]
    p1_label = period_data[1][0]
    p0_count = len(period_data[0][1])
    p1_count = len(period_data[1][1])
    if p0_count == 0 and p1_count == 0:
        logger.error('未取得任何資料')
        sys.exit(1)

    updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_table(conn)
    existing = load_existing(conn)
    written = save_emerging(conn, period_data, existing, updated_at)
    conn.close()

    logger.info(f'已寫入 {written} 家興櫃公司至 monthly_revenue_summary')
    skip_git = bool(args.skip_git)
    git_commit_and_push(updated_at, skip_git=skip_git)
    if args.output_receipt:
        write_receipt(
            Path(args.output_receipt),
            started_at=started_at,
            updated_at=updated_at,
            p0_label=p0_label,
            p1_label=p1_label,
            p0_count=p0_count,
            p1_count=p1_count,
            written=written,
            skip_git=skip_git,
            gate_result='PASS',
        )
    logger.info('=== fetch_emerging_revenue 完成 ===')


if __name__ == '__main__':
    main()
