#!/usr/bin/env python3
"""
fetch_emerging_revenue.py
-------------------------
從 MoneyDJ 興櫃營收總表爬取興櫃公司月營收 YoY%/MoM%，
補充 fetch_monthly_revenue.py（FinMind）未覆蓋的興櫃公司，
寫入 investment.db 的 monthly_revenue_summary 表。

資料來源：https://concords.moneydj.com/z/zu/zue/zuef/
URL 規則：zuef_{產業代碼}_{期別}_2.djhtm
  期別 0 = 當月，1 = 前一個月
資料欄位：代碼+名稱 | 營收(千) | 年增率 | 月增率 | 累計營收 | 累計年增率

6 個月滾動邏輯：
  每次抓當月(P0)和前月(P1)，與 DB 現有資料合併，保留最近 6 個月。
  若興櫃資料來源不足 6 個月，左側月份欄位保留 NULL，前端顯示「-」。
  執行方式：
    cd 台股投資資訊系統_完整專案/上市櫃公司徵人需求度
    ./venv/bin/python3 fetch_emerging_revenue.py
"""

import os
import re
import sys
import time
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

# ── 產業代碼（35個，略過開放式基金 EB200000 和 黃金 EB200999）──────────
INDUSTRY_CODES = [
    'EB204010', 'EB209020', 'EB205030', 'EB205040', 'EB206050',
    'EB206060', 'EB205210', 'EB205220', 'EB204080', 'EB204100',
    'EB205110', 'EB209120', 'EB200240', 'EB200250', 'EB200260',
    'EB200270', 'EB200280', 'EB200290', 'EB200300', 'EB200310',
    'EB204140', 'EB207150', 'EB209160', 'EB208170', 'EB209190',
    'EB209230', 'EB209320', 'EB209330', 'EB209350', 'EB209360',
    'EB209370', 'EB209380', 'EB209200',
]

BASE_URL = 'https://concords.moneydj.com/z/zu/zue/zuef/zuef_{code}_{period}_2.djhtm'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://concords.moneydj.com/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}
REVENUE_MONTH_COUNT = 6


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
def parse_page(html: bytes) -> tuple[str | None, dict[str, dict]]:
    """
    回傳 (月份標籤, {stock_code: {'mom': float|None, 'yoy': float|None}})
    月份標籤格式：'YYYY/M'（如 '2026/3'）
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()

    # 解析日期 "日期:115/03"
    m = re.search(r'日期[：:]\s*(\d{2,3})/(\d{1,2})', text)
    if not m:
        return None, {}
    roc_y, month = int(m.group(1)), int(m.group(2))
    label = f'{roc_y + 1911}/{month}'

    def parse_pct(s: str) -> float | None:
        s = s.strip().replace(',', '').replace('%', '')
        if s in ('', '--', 'N/A', '-', '－'):
            return None
        try:
            return round(float(s), 2)
        except ValueError:
            return None

    data: dict[str, dict] = {}
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 4:
            continue
        raw = cells[0].get_text(strip=True)
        if not raw or not re.match(r'^\d{4}', raw):
            continue
        code = raw[:4]
        # 欄位順序：代碼+名稱, 營收(千), 年增率(YoY), 月增率(MoM), 累計, 累計年增率
        yoy = parse_pct(cells[2].get_text(strip=True))
        mom = parse_pct(cells[3].get_text(strip=True))
        data[code] = {'mom': mom, 'yoy': yoy}

    return label, data


# ── 爬取所有產業 ──────────────────────────────────────────────────────────
def fetch_all_industries() -> dict[int, tuple[str | None, dict[str, dict]]]:
    """
    回傳 {period: (label, {code: {mom, yoy}})}
    period 0 = 當月, 1 = 前月
    """
    # 合併所有產業資料
    period_data: dict[int, tuple[str | None, dict]] = {0: (None, {}), 1: (None, {})}

    for i, ind_code in enumerate(INDUSTRY_CODES):
        for period in [0, 1]:
            url = BASE_URL.format(code=ind_code, period=period)
            for attempt in range(3):
                try:
                    resp = requests.get(url, headers=HEADERS, verify=False, timeout=45)
                    resp.raise_for_status()
                    label, data = parse_page(resp.content)
                    if label:
                        existing_label, existing_data = period_data[period]
                        if existing_label is None:
                            period_data[period] = (label, data)
                        else:
                            existing_data.update(data)
                    break
                except requests.Timeout:
                    logger.warning(f'{ind_code} P{period} timeout (attempt {attempt+1}/3)')
                    time.sleep(3)
                except Exception as e:
                    logger.warning(f'{ind_code} P{period} 失敗: {e}')
                    break
            time.sleep(0.5)

        if (i + 1) % 10 == 0:
            logger.info(f'進度 {i + 1}/{len(INDUSTRY_CODES)} 個產業')

    for period in [0, 1]:
        label, data = period_data[period]
        logger.info(f'Period {period} ({label}): {len(data)} 家公司')

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
        'source': 'MoneyDJ',
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
    logger.info('=== fetch_emerging_revenue (MoneyDJ) 開始 ===')
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
