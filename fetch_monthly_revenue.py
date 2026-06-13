#!/usr/bin/env python3
"""
fetch_monthly_revenue.py
------------------------
從 FinMind 一次抓取全市場月營收，計算近六月 MoM% / YoY%，
存入 investment.db 的 monthly_revenue_summary 表。

執行方式：
  cd 台股投資資訊系統_完整專案/上市櫃公司徵人需求度
  ./venv/bin/python3 fetch_monthly_revenue.py

定時執行：launchd，目前每週一 11:30。
"""

import os
import sys
import sqlite3
import logging
import subprocess
import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

# ── 路徑 ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get('HIRING_PROJECT_ROOT', BASE_DIR.parent)).resolve()
STAGE3_DIR = Path(os.environ.get('HIRING_STAGE3_DIR', BASE_DIR / 'stage3_web')).resolve()
DB_PATH = Path(os.environ.get('DB_PATH', STAGE3_DIR / 'investment.db'))
LOG_PATH = BASE_DIR / 'logs' / 'fetch_monthly_revenue.log'
ENV_PATHS = [
    BASE_DIR / '.env',
    STAGE3_DIR / '.env',
    PROJECT_ROOT / '.env',
]

# ── FinMind ──────────────────────────────────────────────────────────────
FINMIND_API_URL = 'https://api.finmindtrade.com/api/v4/data'
REVENUE_MONTH_COUNT = 6


def iter_revenue_fields():
    for index in range(1, REVENUE_MONTH_COUNT + 1):
        yield f'm{index}_label', 'TEXT'
        yield f'm{index}_mom', 'REAL'
        yield f'm{index}_yoy', 'REAL'


def month_back(year: int, month: int, count: int) -> list[tuple[int, int]]:
    periods: list[tuple[int, int]] = []
    y, m = year, month
    for _ in range(count):
        periods.insert(0, (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return periods

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


# ── 讀取 FINMIND_TOKEN ───────────────────────────────────────────────────
def load_token() -> str:
    token = os.environ.get('FINMIND_TOKEN', '').strip()
    if token:
        return token
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('FINMIND_TOKEN='):
                token = line.split('=', 1)[1].strip().strip('"\'')
                if token:
                    return token
    return ''


# ── DB ───────────────────────────────────────────────────────────────────
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


# ── FinMind 逐一抓取 ─────────────────────────────────────────────────────
def parse_codes(value: str) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    codes: list[str] = []
    for raw_item in value.replace("\n", ",").split(","):
        code = raw_item.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def get_stock_codes_from_db() -> list[str]:
    """從 investment.db 取得 hiring_demand 中的所有股票代碼"""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT stock_code FROM hiring_demand ORDER BY stock_code"
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def fetch_all_revenue(token: str, start_date: str, requested_codes: list[str] | None = None) -> list[dict]:
    """
    逐一抓取 hiring_demand 中的公司月營收（FinMind 不支援全量查詢）。
    回傳欄位：stock_id, revenue_year, revenue_month, revenue
    """
    import time

    codes = requested_codes or get_stock_codes_from_db()
    if not codes:
        logger.warning('沒有可抓取的股票代碼；全量模式請先執行 fetch_hiring_demand.py')
        return []

    logger.info(f'共 {len(codes)} 家公司，開始逐一抓取月營收...')
    all_records: list[dict] = []
    errors = 0
    rate_limited = 0

    for i, code in enumerate(codes):
        try:
            resp = requests.get(FINMIND_API_URL, params={
                'dataset': 'TaiwanStockMonthRevenue',
                'data_id': code,
                'start_date': start_date,
                'token': token,
            }, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            if result.get('status') == 200:
                records = result.get('data', [])
                # 統一欄位：確保有 stock_id
                for r in records:
                    if 'stock_id' not in r:
                        r['stock_id'] = code
                all_records.extend(records)
            elif result.get('status') == 402:
                rate_limited += 1
                logger.warning(f'{code}: FinMind 每日請求額度已達上限（402），剩餘 {len(codes) - i - 1} 家未抓取')
                # 達到上限後繼續嘗試，可能部分端點仍可用
            else:
                logger.debug(f'{code}: FinMind 回傳 {result.get("msg")}')
        except Exception as e:
            errors += 1
            logger.debug(f'{code}: 抓取失敗 {e}')

        # 每 50 家 log 一次進度，適當 sleep 避免 rate limit
        if (i + 1) % 50 == 0:
            logger.info(f'進度 {i + 1}/{len(codes)}，累計 {len(all_records):,} 筆')
        time.sleep(0.2)

    logger.info(f'抓取完成：{len(all_records):,} 筆（失敗 {errors} 家，額度超限 {rate_limited} 家）')
    return all_records


def fetch_mops_official_revenue(
    *,
    requested_codes: list[str],
    start_month: tuple[int, int],
    end_month: tuple[int, int],
) -> list[dict]:
    """
    使用公開資訊觀測站月營收資料作為沒有 FINMIND_TOKEN 時的 fallback。
    回傳欄位與 FinMind 對齊：stock_id, revenue_year, revenue_month, revenue。
    """
    import fetch_stock_monthly_revenue_raw as raw

    codes = requested_codes or get_stock_codes_from_db()
    if not codes:
        logger.warning('沒有可抓取的股票代碼；MOPS fallback 無資料可抓')
        return []

    stock_codes_csv = raw.latest_stock_codes_csv(raw.STOCK_CODES_DIR)
    all_stock_meta = raw.load_stock_codes(stock_codes_csv, None, market_types={'上市', '上櫃', '興櫃'})
    requested_code_set = set(codes)
    stock_meta = {code: meta for code, meta in all_stock_meta.items() if code in requested_code_set}
    missing_stock_codes = sorted(requested_code_set - set(stock_meta))
    if missing_stock_codes:
        logger.warning(
            'MOPS fallback 略過 Stock_codes 缺少的代碼：%s',
            ','.join(missing_stock_codes),
        )
    grouped: dict[str, dict[str, raw.StockMeta]] = defaultdict(dict)
    for code, meta in stock_meta.items():
        grouped[meta.market_type][code] = meta

    fetched_at = datetime.now().isoformat(timespec='seconds')
    run_id = datetime.now().strftime('mops_fallback_%Y%m%d_%H%M%S')
    all_records: list[dict] = []

    for year, month in raw.iter_months(start_month, end_month):
        for market_type, market_stock_meta in grouped.items():
            records, status = raw.fetch_mops_market_month_records(
                year=year,
                month=month,
                market_type=market_type,
                stock_meta=market_stock_meta,
                fetched_at=fetched_at,
                run_id=run_id,
            )
            if status.get('status') not in {'ok', 'empty_current_month_expected'}:
                logger.debug(f'MOPS {market_type} {year}/{month} status={status.get("status")} error={status.get("error")}')
            for record in records:
                all_records.append({
                    'stock_id': record.stock_code,
                    'revenue_year': record.revenue_year,
                    'revenue_month': record.revenue_month,
                    'revenue': record.revenue_amount,
                })

    logger.info(
        f'MOPS fallback 抓取完成：{len(all_records):,} 筆，'
        f'codes={len(codes)}，range={start_month[0]}/{start_month[1]}-{end_month[0]}/{end_month[1]}'
    )
    return all_records


# ── 計算 MoM% / YoY% ────────────────────────────────────────────────────
def compute_summaries(records: list[dict]) -> dict[str, dict]:
    """
    輸入：FinMind 回傳的 list，每筆含 stock_id / revenue_year / revenue_month / revenue
    輸出：{ stock_code: { 'm1': {...}, ... 'm6': {...} } }
            m1 = 最舊，m6 = 最新
    """
    # 建 lookup: code -> (year, month) -> revenue
    lookup: dict[str, dict[tuple, float]] = defaultdict(dict)
    for r in records:
        code = r.get('stock_id', '')
        y = r.get('revenue_year')
        m = r.get('revenue_month')
        rev = r.get('revenue')
        if code and y and m and rev is not None:
            lookup[code][(int(y), int(m))] = float(rev)

    summaries: dict[str, dict] = {}

    for code, rev_map in lookup.items():
        if not rev_map:
            continue

        # 找最新月份
        latest_y, latest_m = max(rev_map.keys())

        # 近六個月（由舊到新）
        periods = month_back(latest_y, latest_m, REVENUE_MONTH_COUNT)

        result = {}
        for i, (py, pm) in enumerate(periods):
            key = f'm{i + 1}'
            curr = rev_map.get((py, pm))

            # MoM%
            prev_m = pm - 1
            prev_y = py
            if prev_m == 0:
                prev_m = 12
                prev_y -= 1
            prev = rev_map.get((prev_y, prev_m))
            mom = round((curr - prev) / prev * 100, 2) \
                if (curr is not None and prev and prev != 0) else None

            # YoY%
            ly_val = rev_map.get((py - 1, pm))
            yoy = round((curr - ly_val) / ly_val * 100, 2) \
                if (curr is not None and ly_val and ly_val != 0) else None

            result[key] = {
                'label': f'{py}/{pm}',
                'mom': mom,
                'yoy': yoy,
            }

        summaries[code] = result

    logger.info(f'計算完成，共 {len(summaries):,} 家公司')
    return summaries


# ── 寫入 DB ──────────────────────────────────────────────────────────────
def save_summaries(conn: sqlite3.Connection, summaries: dict, updated_at: str):
    rows = []
    for code, s in summaries.items():
        values = [code]
        for index in range(1, REVENUE_MONTH_COUNT + 1):
            month = s.get(f'm{index}') or {}
            values.extend([month.get('label'), month.get('mom'), month.get('yoy')])
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
    logger.info(f'已寫入 {len(rows):,} 筆至 monthly_revenue_summary')


# ── git commit + push ────────────────────────────────────────────────────
def git_commit_and_push(updated_at: str, *, skip_git: bool = False):
    if skip_git or os.environ.get('HIRING_REVENUE_SKIP_GIT', '').lower() in {'1', 'true', 'yes'}:
        logger.info('skip git enabled，略過 monthly revenue git commit/push')
        return
    if not (STAGE3_DIR / '.git').exists():
        logger.error(f'內部 stage3_web 尚未初始化 Git repo，停止 monthly revenue commit/push: {STAGE3_DIR}')
        return
    try:
        repo_dir = STAGE3_DIR
        subprocess.run(['git', 'add', 'investment.db'],
                       cwd=repo_dir, check=True, capture_output=True)
        msg = f'chore: 更新月營收 MoM%/YoY% 摘要 {updated_at[:10]}'
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
    requested_codes: list[str],
    summary_codes: list[str],
    record_count: int,
    skip_git: bool,
    gate_result: str,
    typed_blockers: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        'receipt_type': 'monthly_revenue_fetch_receipt',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'started_at': started_at,
        'updated_at': updated_at,
        'mode': 'targeted_codes' if requested_codes else 'all_hiring_demand_codes',
        'requested_code_count': len(requested_codes),
        'requested_codes': requested_codes,
        'summary_code_count': len(summary_codes),
        'summary_codes': summary_codes,
        'record_count': record_count,
        'db_path': str(DB_PATH),
        'skip_git': skip_git,
        'gate_result': gate_result,
        'typed_blockers': typed_blockers,
    }
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Fetch monthly revenue summary into investment.db.')
    parser.add_argument('--codes', default='', help='Comma-separated stock codes to fetch. Empty means all hiring_demand codes.')
    parser.add_argument('--skip-git', action='store_true', help='Do not git commit/push after updating investment.db.')
    parser.add_argument('--output-receipt', default='', help='Optional JSON receipt path.')
    return parser


# ── 主程式 ───────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None):
    args = build_parser().parse_args(argv)
    logger.info('=== fetch_monthly_revenue 開始 ===')
    started_at = datetime.now().isoformat(timespec='seconds')
    requested_codes = parse_codes(args.codes)

    now = datetime.now()
    # 抓前兩年起到今天，確保近六月即使跨年也有去年同月資料可算 YoY。
    start_year = now.year - 2
    start_date = f'{start_year}-01-01'

    token = load_token()
    if token:
        try:
            records = fetch_all_revenue(token, start_date, requested_codes=requested_codes)
        except Exception as e:
            logger.error(f'FinMind 抓取失敗: {e}')
            sys.exit(1)
    else:
        logger.warning('找不到 FINMIND_TOKEN，改用 MOPS 官方月營收 fallback')
        start_month = (start_year, 1)
        end_month = (now.year, now.month)
        try:
            records = fetch_mops_official_revenue(
                requested_codes=requested_codes,
                start_month=start_month,
                end_month=end_month,
            )
        except Exception as e:
            logger.error(f'MOPS fallback 抓取失敗: {e}')
            sys.exit(1)

    summaries = compute_summaries(records)
    missing_requested_codes = sorted(set(requested_codes) - set(summaries)) if requested_codes else []

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    updated_at = now.strftime('%Y-%m-%d %H:%M:%S')
    save_summaries(conn, summaries, updated_at)
    conn.close()

    typed_blockers: list[dict] = []
    if missing_requested_codes:
        typed_blockers.append({
            'finding_type': 'monthly_revenue_targeted_fetch_missing_codes',
            'plain_description': '指定補抓的公司未能從 FinMind 或 MOPS 取得月營收摘要。',
            'affected_key': ','.join(missing_requested_codes),
            'required_fix': '確認公司市場別與來源；若來源未公布則標記 typed blocker。',
        })
        logger.error(f'指定補抓代碼仍缺月營收：{missing_requested_codes}')

    gate_result = 'PASS' if not typed_blockers else 'FAIL'
    skip_git = bool(args.skip_git)
    if gate_result == 'PASS':
        git_commit_and_push(updated_at, skip_git=skip_git)
    elif skip_git:
        logger.info('補抓 gate FAIL 且 skip-git enabled，不進行 git 操作')

    if args.output_receipt:
        write_receipt(
            Path(args.output_receipt),
            started_at=started_at,
            updated_at=updated_at,
            requested_codes=requested_codes,
            summary_codes=sorted(summaries),
            record_count=len(records),
            skip_git=skip_git,
            gate_result=gate_result,
            typed_blockers=typed_blockers,
        )

    logger.info('=== fetch_monthly_revenue 完成 ===')
    if gate_result != 'PASS':
        sys.exit(2)


if __name__ == '__main__':
    main()
