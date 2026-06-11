#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上市櫃公司徵人需求度擷取程式

功能：
1. 從 104 人力銀行搜尋作業員/包裝員/產線相關職缺
2. 二次篩選：職缺名稱含「員」字（如作業員、包裝員、檢驗員、操作員等）
3. 比對台股上市櫃公司名稱
4. 呼叫職缺詳情 API 取得每筆職缺的真實需求人數
5. 計算各公司的徵人需求度（需求人數 / 員工人數）
6. 輸出 CSV 並寫入資料庫

策略：
- 以關鍵字全域搜尋職缺，再按公司名稱比對股票代碼表
- 二次篩選以「員」字為核心（工程師、經理不含「員」自然被排除）
- 搜尋 API 不含需求人數，須對每筆匹配的職缺呼叫詳情 API
- 三分類：明確人數 / 不限（999.0）/ 未標示（998.0）
- 員工人數只採 104 搜尋結果與 Google fallback，避免公司頁 API 非 JSON 雜訊

執行方式：
- 手動執行: python3 fetch_hiring_demand.py
- 定時執行: 透過 launchd 每週一 10:00 自動執行
"""

import json
import os
import sys
import logging
import sqlite3
import time
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import yaml

from hiring_workflow_governance import write_workflow_governance_artifacts

# ==================== 設定 ====================

BASE_DIR = Path(__file__).parent
HIRING_DIR = BASE_DIR.resolve()
PROJECT_ROOT = Path(os.environ.get("HIRING_PROJECT_ROOT", BASE_DIR.parent)).resolve()
CONFIG_PATH = BASE_DIR / 'config.yaml'
LOG_FILE = BASE_DIR / 'hiring_demand.log'
VALID_RUN_MODES = {'scrape-only', 'write-db', 'deploy'}
GOVERNANCE_CONTRACT_ID = 'hiring-demand-ai-runtime-governance-v1'
EXTERNAL_RUNTIME_POLICY = {
    'opa': 'concept_only_not_installed',
    'temporal': 'concept_only_not_installed',
    'langfuse': 'concept_only_not_installed',
    'great_expectations': 'concept_only_not_installed',
    'prefect': 'concept_only_not_installed',
    'dagster': 'concept_only_not_installed',
    'argo_workflows': 'concept_only_not_installed',
    'opentelemetry_collector': 'concept_only_not_installed',
    'superpowers_runtime': 'concept_only_not_installed',
}

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# HTTP 請求標頭
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.104.com.tw/jobs/search/',
    'Accept': 'application/json, text/plain, */*',
}


# ==================== 設定檔載入 ====================

def _resolve_project_path(value: str, *, env_name: str = "") -> str:
    """Resolve config paths relative to the project root unless an env override exists."""
    override = os.environ.get(env_name) if env_name else None
    raw_value = override or value
    path = Path(str(raw_value)).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


def _resolve_hiring_path(value: str, *, env_name: str = "") -> str:
    """Resolve config paths relative to the standalone hiring project folder."""
    override = os.environ.get(env_name) if env_name else None
    raw_value = override or value
    path = Path(str(raw_value)).expanduser()
    if not path.is_absolute():
        path = HIRING_DIR / path
    return str(path.resolve())


def load_config() -> dict:
    """載入設定檔"""
    if not CONFIG_PATH.exists():
        logger.error(f"找不到設定檔: {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    paths = config.setdefault('paths', {})
    paths['stock_codes_dir'] = _resolve_project_path(
        paths.get('stock_codes_dir', '../台股上市櫃公司名稱確認與自動定時更新/Stock_codes'),
        env_name='STOCK_CODES_DIR',
    )
    paths['db_path'] = _resolve_hiring_path(
        paths.get('db_path', 'stage3_web/investment.db'),
        env_name='DB_PATH',
    )
    paths['output_dir'] = _resolve_hiring_path(
        paths.get('output_dir', 'data'),
        env_name='HIRING_OUTPUT_DIR',
    )

    logger.info("已載入設定檔")
    return config


# ==================== 股票代碼表 ====================

def get_latest_stock_codes(stock_codes_dir: str) -> pd.DataFrame:
    """
    讀取最新的股票代碼對照表

    Args:
        stock_codes_dir: Stock_codes 資料夾路徑

    Returns:
        包含所有上市櫃興櫃公司的 DataFrame
    """
    codes_dir = Path(stock_codes_dir)
    csv_files = sorted(codes_dir.glob('*_stock_codes_all.csv'), reverse=True)

    if not csv_files:
        raise FileNotFoundError(f"找不到股票代碼檔案: {codes_dir}")

    latest_file = csv_files[0]
    logger.info(f"使用股票代碼檔案: {latest_file.name}")

    df = pd.read_csv(latest_file, dtype={'股票代碼': str})
    df.attrs['source_file'] = str(latest_file)
    logger.info(f"共 {len(df)} 家上市櫃興櫃公司")

    return df


# ==================== 雙通道通知（macOS + ntfy） ====================

# 嘗試載入共用通知模組（支援 iPhone ntfy 推播）
_notify_module = None
try:
    _tools_dir = str(PROJECT_ROOT)
    if _tools_dir not in sys.path:
        sys.path.insert(0, _tools_dir)
    from tools.notify import send_notification as _send_dual
    _notify_module = True
except ImportError:
    _notify_module = False


def send_notification(title: str, message: str, sound: bool = True):
    """發送通知（macOS 系統通知 + ntfy 手機推播）"""
    # 雙通道：macOS + ntfy
    if _notify_module:
        try:
            _send_dual(title, message)
            logger.info(f"已發送雙通道通知: {title}")
            return
        except Exception as e:
            logger.warning(f"雙通道通知失敗，退回 macOS: {e}")

    # Fallback: 僅 macOS
    try:
        sound_cmd = 'sound name "default"' if sound else ''
        script = f'''
        display notification "{message}" with title "{title}" {sound_cmd}
        '''
        subprocess.run(['osascript', '-e', script], check=True)
        logger.info(f"已發送 macOS 通知: {title}")
    except Exception as e:
        logger.error(f"發送通知失敗: {e}")


# ==================== 104 API 呼叫 ====================

def rate_limited_request(url: str, params: dict, headers: dict, config: dict,
                         delay_min_key: str = 'delay_min',
                         delay_max_key: str = 'delay_max') -> dict:
    """
    帶速率限制和重試的 HTTP GET 請求

    Args:
        url: API URL
        params: 查詢參數
        headers: HTTP 標頭
        config: API 設定
        delay_min_key: 最小延遲設定鍵名
        delay_max_key: 最大延遲設定鍵名

    Returns:
        JSON 回應資料，或 None
    """
    api_config = config.get('api', {})
    max_retries = api_config.get('max_retries', 3)
    delay_min = api_config.get(delay_min_key, 1.0)
    delay_max = api_config.get(delay_max_key, 2.5)
    timeout = api_config.get('timeout', 30)

    for attempt in range(max_retries):
        try:
            # 隨機延遲
            delay = random.uniform(delay_min, delay_max)
            time.sleep(delay)

            response = requests.get(url, params=params, headers=headers, timeout=timeout)

            if response.status_code == 429:
                wait_time = 60 * (attempt + 1)
                logger.warning(f"被限速 (429)，等待 {wait_time} 秒...")
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"請求失敗 (第 {attempt + 1} 次): {e}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))

    return None


def search_104_jobs(keyword: str, config: dict) -> list:
    """
    搜尋 104 人力銀行的職缺（新版 API）

    新版 API 端點: /jobs/search/api/jobs
    回應結構:
    - data[].jobName: 職缺名稱
    - data[].custName: 公司名稱
    - data[].custNo: 公司編號
    - data[].jobNo: 職缺編號
    - data[].employeeCount: 員工人數（整數，0 表示未提供）
    - metadata.pagination.total: 總筆數
    - metadata.pagination.lastPage: 最後一頁
    - metadata.pagination.currentPage: 目前頁碼

    注意: 新版 API 不含 needEmp（需求人數），
    須另外呼叫 /job/ajax/content/{jobNo} 取得

    Args:
        keyword: 搜尋關鍵字（如「作業員」）
        config: 設定

    Returns:
        職缺列表
    """
    api_config = config.get('api', {})
    search_url = api_config.get('search_url', 'https://www.104.com.tw/jobs/search/api/jobs')

    all_jobs = []
    page = 1
    total_pages = None

    logger.info(f"搜尋關鍵字: {keyword}")

    while True:
        params = {
            'ro': '0',           # 全部（全職+兼職）
            'kwop': '7',         # 關鍵字搜尋模式
            'keyword': keyword,
            'order': '15',       # 排序
            'asc': '0',          # 降序
            'page': str(page),
            'mode': 's',         # 搜尋模式
            'jobsource': '2018indexpoc',
        }

        data = rate_limited_request(search_url, params, HEADERS, config)

        if not data:
            logger.warning(f"第 {page} 頁請求失敗，停止搜尋")
            break

        # 新版 API 回應結構
        job_list = data.get('data', [])
        if not job_list:
            logger.info(f"第 {page} 頁無結果，搜尋結束")
            break

        # 取得總頁數（從 metadata.pagination）
        if total_pages is None:
            pagination = data.get('metadata', {}).get('pagination', {})
            total_count = pagination.get('total', 0)
            total_pages = pagination.get('lastPage', 1)
            logger.info(f"共 {total_count} 筆結果，{total_pages} 頁")

        # 收集職缺資料
        for job in job_list:
            # 從 link.job URL 提取 job ID（如 "5jyh6"）
            # link.job 格式: "https://www.104.com.tw/job/5jyh6"
            job_link = job.get('link', {}).get('job', '') if isinstance(job.get('link'), dict) else ''
            link_job_id = job_link.rstrip('/').split('/')[-1] if job_link else ''

            all_jobs.append({
                'custNo': job.get('custNo', ''),
                'custName': job.get('custName', ''),
                'jobName': job.get('jobName', ''),
                'jobNo': job.get('jobNo', ''),
                'linkJobId': link_job_id,  # 詳情 API 用此 ID
                'employeeCount': job.get('employeeCount', 0),  # 新版直接是整數
                'link': job_link,
            })

        logger.info(f"  第 {page}/{total_pages} 頁，已收集 {len(all_jobs)} 筆")

        # 檢查是否還有下一頁
        if page >= total_pages:
            break

        page += 1

    logger.info(f"關鍵字「{keyword}」共收集 {len(all_jobs)} 筆職缺")
    return all_jobs


def fetch_job_detail_need_emp(link_job_id: str, config: dict) -> str:
    """
    從 104 職缺詳情 API 取得需求人數

    API 端點: /job/ajax/content/{linkJobId}
    回應: data.jobDetail.needEmp（如 "1~3人"、"不限"、None）

    注意: linkJobId 來自搜尋 API 的 link.job URL（如 "5jyh6"），
    不是 jobNo（數字格式，詳情 API 不接受）

    Args:
        link_job_id: 職缺 ID（從 link.job URL 提取，如 "5jyh6"）
        config: 設定

    Returns:
        需求人數字串（如 "5"、"不限"、"1~3人"），失敗或未標示回傳 ""
    """
    if not link_job_id:
        return ""

    api_config = config.get('api', {})
    detail_url = api_config.get('job_detail_url', 'https://www.104.com.tw/job/ajax/content/')
    url = f"{detail_url}{link_job_id}"

    detail_headers = HEADERS.copy()
    detail_headers['Referer'] = f'https://www.104.com.tw/job/{link_job_id}'

    data = rate_limited_request(
        url, {}, detail_headers, config,
        delay_min_key='detail_delay_min',
        delay_max_key='detail_delay_max'
    )

    if data and isinstance(data, dict):
        need_emp = data.get('data', {}).get('jobDetail', {}).get('needEmp', None)
        if need_emp:
            return str(need_emp)

    return ""


# ==================== 員工人數解析 ====================

def parse_employee_count(emp_str: str) -> int:
    """
    解析 104 的員工人數字串

    Args:
        emp_str: 員工人數字串（如 "500~1000人"、"1000人以上"、"暫不提供"）

    Returns:
        員工人數（整數）
    """
    if not emp_str or emp_str == '暫不提供':
        return 0

    emp_str = emp_str.replace('人', '').replace(',', '').strip()

    if '以上' in emp_str:
        num_str = emp_str.replace('以上', '').strip()
        try:
            return int(num_str)
        except ValueError:
            return 0

    if '~' in emp_str:
        parts = emp_str.split('~')
        try:
            return (int(parts[0].strip()) + int(parts[1].strip())) // 2
        except (ValueError, IndexError):
            return 0

    try:
        return int(emp_str)
    except ValueError:
        return 0


def fetch_employee_count_from_company_api(cust_no: str, config: dict) -> int:
    """
    從 104 公司頁面 API 取得員工人數

    Args:
        cust_no: 104 公司客戶編號
        config: 設定

    Returns:
        員工人數（整數），失敗回傳 0
    """
    if not cust_no:
        return 0

    api_config = config.get('api', {})
    company_url = api_config.get('company_url', 'https://www.104.com.tw/company/ajax/content/')
    url = f"{company_url}{cust_no}"

    company_headers = HEADERS.copy()
    company_headers['Referer'] = f'https://www.104.com.tw/company/{cust_no}'

    data = rate_limited_request(url, {}, company_headers, config)

    if data and isinstance(data, dict):
        # 嘗試從不同欄位取得員工人數
        emp_no = data.get('data', {}).get('empNo', '')
        if emp_no:
            count = parse_employee_count(str(emp_no))
            if count > 0:
                return count

    return 0


def fetch_employee_count_from_google(company_name: str) -> int:
    """
    從 Google 搜尋取得員工人數

    Args:
        company_name: 公司名稱

    Returns:
        員工人數（整數），失敗回傳 0
    """
    try:
        query = f"{company_name} 員工人數"
        url = f"https://www.google.com/search?q={quote(query)}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        }

        time.sleep(random.uniform(2.0, 4.0))
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            text = response.text

            # 嘗試從 Google 精選摘要中提取員工人數
            patterns = [
                r'員工(?:人數|數)?[：:]\s*約?\s*([\d,]+)\s*人',
                r'約?\s*([\d,]+)\s*(?:名|位)?\s*員工',
                r'員工(?:總數|人數)?.*?([\d,]+)\s*人',
                r'([\d,]+)\s*人.*?員工',
            ]

            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    num_str = match.group(1).replace(',', '')
                    try:
                        count = int(num_str)
                        if 10 <= count <= 500000:  # 合理範圍
                            logger.info(f"  Google 搜尋取得 {company_name} 員工人數: {count}")
                            return count
                    except ValueError:
                        continue

    except Exception as e:
        logger.debug(f"  Google 搜尋 {company_name} 員工人數失敗: {e}")

    return 0


def fetch_employee_count_from_mops(stock_code: str) -> int:
    """
    從公開資訊觀測站取得員工人數

    Args:
        stock_code: 股票代碼

    Returns:
        員工人數（整數），失敗回傳 0
    """
    try:
        url = 'https://mops.twse.com.tw/mops/web/ajax_t05st15'
        data = {
            'encodeURIComponent': '1',
            'step': '1',
            'firstin': '1',
            'off': '1',
            'co_id': stock_code,
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        time.sleep(random.uniform(1.0, 2.0))
        response = requests.post(url, data=data, headers=headers, timeout=15)

        if response.status_code == 200:
            text = response.text
            # 嘗試解析員工人數
            match = re.search(r'員工人數.*?(\d[\d,]*)', text, re.DOTALL)
            if match:
                num_str = match.group(1).replace(',', '')
                try:
                    count = int(num_str)
                    if count > 0:
                        logger.info(f"  MOPS 取得 {stock_code} 員工人數: {count}")
                        return count
                except ValueError:
                    pass

    except Exception as e:
        logger.debug(f"  MOPS 查詢 {stock_code} 失敗: {e}")

    return 0


def get_employee_count(employee_count_int: int, cust_no: str, company_name: str,
                       stock_code: str, config: dict) -> int:
    """
    取得員工人數

    優先順序：
    1. 104 搜尋結果（新版 API 直接提供整數）
    2. Google 搜尋

    Args:
        employee_count_int: 104 搜尋結果的員工人數（整數，0 表示未提供）
        cust_no: 104 公司客戶編號（保留相容參數，不再用於員工人數 fallback）
        company_name: 公司名稱
        stock_code: 股票代碼（保留相容參數，不再用於 MOPS fallback）
        config: 設定

    Returns:
        員工人數（整數）
    """
    # 第一層：104 搜尋結果直接提供
    if employee_count_int and employee_count_int > 0:
        return employee_count_int

    logger.info(f"  {company_name} 員工人數未提供，改用 Google fallback 查詢...")

    # 第二層：Google 搜尋
    count = fetch_employee_count_from_google(company_name)
    if count > 0:
        return count

    logger.warning(f"  {company_name} ({stock_code}) 無法從 104 搜尋結果或 Google 取得員工人數")
    return 0


# ==================== 職缺篩選 ====================

def filter_job(job_name: str, config: dict) -> bool:
    """
    判斷職缺是否符合篩選條件

    篩選邏輯：
    - 職缺名稱必須包含「員」字（如：作業員、包裝員、檢驗員、操作員、倉管員等）
    - 工程師、經理等管理/技術職稱不含「員」字，自然被排除
    - 額外排除：主管、組長、課長、專員、業務員、研究員等

    Args:
        job_name: 職缺名稱
        config: 設定

    Returns:
        True 表示符合條件
    """
    filter_char = config.get('job_title_filter_char', '員')
    exclude_keywords = config.get('exclude_keywords', ['主管', '組長', '經理', '專員', '業務員', '研究員'])

    # 必須包含「員」字
    if filter_char not in job_name:
        return False

    # 不能包含排除關鍵字
    has_exclude = any(kw in job_name for kw in exclude_keywords)
    if has_exclude:
        return False

    return True


def parse_need_emp(need_emp_str: str) -> tuple:
    """
    解析需求人數（三分類）

    Args:
        need_emp_str: 需求人數字串（如 "5人"、"1~3人"、"不限"、"若干"）

    Returns:
        (explicit_count, is_unlimited, is_unspecified)
        - explicit_count: 明確需求人數（整數）
        - is_unlimited: 是否為「不限」（公司主動標示人數不限）
        - is_unspecified: 是否為「未標示」（API 無回傳或空值）
    """
    if not need_emp_str or str(need_emp_str).strip() in ('', '0'):
        return (0, False, True)  # 未標示

    need_emp_str = str(need_emp_str).strip()

    if need_emp_str in ('不限', '若干', '不拘'):
        return (0, True, False)  # 不限

    # 移除「人」等文字
    num_str = need_emp_str.replace('人', '').replace(',', '').strip()

    # 處理範圍格式（如 "1~3"）
    if '~' in num_str:
        parts = num_str.split('~')
        try:
            # 取範圍的中間值
            low = int(parts[0].strip())
            high = int(parts[1].strip())
            return ((low + high) // 2, False, False)  # 明確人數
        except (ValueError, IndexError):
            return (0, False, True)  # 解析失敗 → 未標示

    # 處理「以上」格式
    if '以上' in num_str:
        num_str = num_str.replace('以上', '').strip()

    try:
        return (int(num_str), False, False)  # 明確人數
    except ValueError:
        return (0, False, True)  # 解析失敗 → 未標示


# ==================== 公司名稱比對 ====================

def match_company(company_name_104: str, stock_df: pd.DataFrame) -> dict:
    """
    將 104 上的公司名稱比對到股票代碼表

    Args:
        company_name_104: 104 上的公司名稱
        stock_df: 股票代碼 DataFrame

    Returns:
        匹配的公司資訊 dict，或 None
    """
    if not company_name_104:
        return None

    # 正規化名稱
    normalized = company_name_104.strip()

    # 1. 精確匹配公司全名
    match = stock_df[stock_df['公司全名'] == normalized]
    if not match.empty:
        return match.iloc[0].to_dict()

    # 2. 精確匹配公司簡稱
    match = stock_df[stock_df['公司簡稱'] == normalized]
    if not match.empty:
        return match.iloc[0].to_dict()

    # 3. 移除常見後綴後匹配
    suffixes = ['股份有限公司', '有限公司']
    clean_104 = normalized
    for suffix in suffixes:
        clean_104 = clean_104.replace(suffix, '')
    clean_104 = clean_104.strip()

    for _, row in stock_df.iterrows():
        full_name = str(row['公司全名'])
        clean_full = full_name
        for suffix in suffixes:
            clean_full = clean_full.replace(suffix, '')
        clean_full = clean_full.strip()

        # 去後綴精確匹配
        if clean_104 == clean_full:
            return row.to_dict()

    # 4. 包含匹配（較寬鬆）
    if len(clean_104) >= 3:
        for _, row in stock_df.iterrows():
            full_name = str(row['公司全名'])
            clean_full = full_name
            for suffix in suffixes:
                clean_full = clean_full.replace(suffix, '')
            clean_full = clean_full.strip()

            if clean_104 in clean_full or clean_full in clean_104:
                return row.to_dict()

    return None


# ==================== 資料彙整 ====================

def aggregate_company_data(all_jobs: list, stock_df: pd.DataFrame, config: dict) -> dict:
    """
    將職缺資料按公司彙整

    流程：
    1. 去重（同一職缺可能在不同關鍵字搜尋中出現）
    2. 二次篩選職缺名稱
    3. 比對公司名稱到股票代碼表
    4. 對匹配的職缺呼叫詳情 API 取得 needEmp
    5. 按公司彙整需求人數

    Args:
        all_jobs: 所有職缺列表
        stock_df: 股票代碼 DataFrame
        config: 設定

    Returns:
        按公司彙整的資料 dict
    """
    # 去重（同一職缺可能在不同關鍵字搜尋中出現）
    seen_jobs = set()
    unique_jobs = []
    for job in all_jobs:
        link_job_id = job.get('linkJobId', '')
        job_key = link_job_id if link_job_id else (job.get('custNo', ''), job.get('jobNo', ''))
        if job_key not in seen_jobs:
            seen_jobs.add(job_key)
            unique_jobs.append(job)

    logger.info(f"去重後共 {len(unique_jobs)} 筆職缺（原 {len(all_jobs)} 筆）")

    # 二次篩選職缺名稱
    filtered_jobs = [j for j in unique_jobs if filter_job(j.get('jobName', ''), config)]
    logger.info(f"職缺名稱篩選後共 {len(filtered_jobs)} 筆")

    # 比對公司名稱
    company_cache = {}  # 快取比對結果
    matched_jobs = []   # 比對成功的職缺
    unmatched = set()

    for job in filtered_jobs:
        cust_name = job.get('custName', '')

        # 查快取
        if cust_name not in company_cache:
            company_cache[cust_name] = match_company(cust_name, stock_df)

        matched = company_cache[cust_name]
        if not matched:
            unmatched.add(cust_name)
            continue

        matched_jobs.append((job, matched))

    logger.info(f"比對成功 {len(matched_jobs)} 筆職缺，來自 {len(set(m['股票代碼'] for _, m in matched_jobs))} 家上市櫃公司")
    if unmatched:
        logger.info(f"未匹配的公司共 {len(unmatched)} 家（非上市櫃）")
        for name in list(unmatched)[:20]:
            logger.debug(f"  未匹配: {name}")

    # 呼叫詳情 API 取得每筆職缺的 needEmp
    logger.info(f"開始查詢 {len(matched_jobs)} 筆職缺的需求人數...")
    company_data = {}

    for i, (job, matched_company) in enumerate(matched_jobs):
        stock_code = str(matched_company['股票代碼'])
        link_job_id = job.get('linkJobId', '')

        # 呼叫詳情 API 取得 needEmp（使用 link 中的 job ID）
        need_emp_str = fetch_job_detail_need_emp(link_job_id, config)

        if (i + 1) % 50 == 0:
            logger.info(f"  已查詢 {i + 1}/{len(matched_jobs)} 筆職缺詳情")

        # 初始化公司資料
        if stock_code not in company_data:
            company_data[stock_code] = {
                'stock_code': stock_code,
                'company_short_name': matched_company['公司簡稱'],
                'company_full_name': matched_company['公司全名'],
                'market_type': matched_company['市場類別'],
                'employee_count_raw': job.get('employeeCount', 0),
                'cust_no': job.get('custNo', ''),
                'explicit_need': 0,
                'unlimited_job_count': 0,
                'unspecified_job_count': 0,
                'total_job_count': 0,
                'jobs': [],
            }

        # 解析需求人數（三分類：明確人數 / 不限 / 未標示）
        explicit, is_unlimited, is_unspecified = parse_need_emp(need_emp_str)

        company_data[stock_code]['explicit_need'] += explicit
        if is_unlimited:
            company_data[stock_code]['unlimited_job_count'] += 1
        if is_unspecified:
            company_data[stock_code]['unspecified_job_count'] += 1
        company_data[stock_code]['total_job_count'] += 1
        company_data[stock_code]['jobs'].append({
            'job_name': job.get('jobName', ''),
            'link_job_id': link_job_id,
            'need_emp_raw': need_emp_str,
            'need_emp': explicit,
            'is_unlimited': is_unlimited,
            'is_unspecified': is_unspecified,
        })

    logger.info(f"職缺詳情查詢完成，共 {len(company_data)} 家上市櫃公司")

    return company_data


# ==================== 計算需求度 ====================

def calculate_demand(company_data: dict, config: dict) -> pd.DataFrame:
    """
    計算各公司的徵人需求度

    Args:
        company_data: 按公司彙整的資料
        config: 設定

    Returns:
        結果 DataFrame
    """
    results = []

    for stock_code, info in company_data.items():
        # 取得員工人數（多層查詢）
        emp_count = get_employee_count(
            info['employee_count_raw'],
            info['cust_no'],
            info['company_full_name'],
            stock_code,
            config
        )

        # 計算需求度
        explicit_need = info['explicit_need']
        unlimited_count = info['unlimited_job_count']
        unspecified_count = info['unspecified_job_count']

        if emp_count > 0 and explicit_need > 0:
            # 有明確人數，計算百分比（未標示的職缺不影響百分比）
            demand_ratio = round((explicit_need / emp_count) * 100, 2)
        elif explicit_need == 0 and unlimited_count > 0:
            # 沒有明確人數，但有「不限」職缺
            demand_ratio = 999.0
        elif explicit_need == 0 and unlimited_count == 0 and unspecified_count > 0:
            # 只有「未標示」職缺（API 無回傳需求人數）
            demand_ratio = 998.0
        else:
            demand_ratio = 0.0

        results.append({
            '股票代碼': stock_code,
            '公司簡稱': info['company_short_name'],
            '公司全名': info['company_full_name'],
            '市場類別': info['market_type'],
            '員工人數': emp_count,
            '明確需求人數': explicit_need,
            '不限職缺數': unlimited_count,
            '未標示職缺數': unspecified_count,
            '總職缺數': info['total_job_count'],
            '徵人需求度': demand_ratio,
        })

    df = pd.DataFrame(results)

    if not df.empty:
        # 排序：需求度降序
        df = df.sort_values('徵人需求度', ascending=False).reset_index(drop=True)

    logger.info(f"計算完成，共 {len(df)} 家公司有徵人資料")

    # 統計
    if not df.empty:
        high_demand = df[(df['徵人需求度'] >= 15) & (df['徵人需求度'] < 998)].shape[0]
        unlimited = df[df['徵人需求度'] == 999.0].shape[0]
        unspecified = df[df['徵人需求度'] == 998.0].shape[0]
        logger.info(f"  需求度 ≥15%: {high_demand} 家")
        logger.info(f"  人數不限: {unlimited} 家")
        logger.info(f"  未標示需求人數: {unspecified} 家")

    return df


# ==================== Run manifest / receipt ====================

def _unique_job_count(all_jobs: list) -> int:
    seen = set()
    for job in all_jobs:
        link_job_id = job.get('linkJobId', '')
        job_key = link_job_id if link_job_id else (job.get('custNo', ''), job.get('jobNo', ''))
        seen.add(job_key)
    return len(seen)


def build_run_manifest(
    *,
    run_id: str,
    run_mode: str,
    status: str,
    started_at: datetime,
    ended_at: datetime,
    config: dict,
    stock_codes_file: Path,
    all_jobs: list,
    company_data: dict,
    result_df: pd.DataFrame,
    csv_path: Path,
    db_inserted_count: int,
    job_inserted_count: int,
) -> dict:
    """Build a durable manifest for the current hiring-demand run."""
    matched_jobs = sum(int(info.get('total_job_count', 0)) for info in company_data.values())
    db_path = config.get('paths', {}).get('db_path', '')
    return {
        'schema_version': 1,
        'run_id': run_id,
        'run_mode': run_mode,
        'governance_contract_id': GOVERNANCE_CONTRACT_ID,
        'status': status,
        'started_at': started_at.isoformat(timespec='seconds'),
        'ended_at': ended_at.isoformat(timespec='seconds'),
        'duration_seconds': round((ended_at - started_at).total_seconds(), 1),
        'fetch_date': ended_at.strftime('%Y-%m-%d'),
        'input_stock_codes_file': str(stock_codes_file),
        'csv_path': str(csv_path),
        'db_path': db_path,
        'csv_row_count': int(len(result_df)),
        'db_inserted_count': int(db_inserted_count),
        'job_inserted_count': int(job_inserted_count),
        'ai_runtime_governance': {
            'external_runtime_policy': EXTERNAL_RUNTIME_POLICY,
            'external_runtime_installed_or_started': False,
            'local_gate': 'check_hiring_demand_run.py',
            'closeout_receipt_required': True,
            'deploy_requires_explicit_mode': True,
            'three_layers': [
                'workflow_domain',
                'harness_checker_receipt',
                'agent_session_governance',
            ],
        },
        'lineage': {
            'inputs': [
                {'asset_type': 'stock_codes_csv', 'path': str(stock_codes_file)},
                {
                    'asset_type': '104_search_api',
                    'keywords': list(config.get('search_keywords', [])),
                },
            ],
            'outputs': [
                {'asset_type': 'hiring_demand_csv', 'path': str(csv_path), 'row_count': int(len(result_df))},
                {'asset_type': 'investment_db', 'path': db_path, 'row_count': int(db_inserted_count)},
                {'asset_type': 'hiring_demand_jobs', 'path': db_path, 'row_count': int(job_inserted_count)},
            ],
            'expected_receipts': [
                'hiring_run_check_receipt.json',
                'hiring_run_check_receipt.md',
                'typed_blockers.csv',
                'warnings.csv',
            ],
        },
        'api_source_summary': {
            'search_keywords': list(config.get('search_keywords', [])),
            'total_jobs': int(len(all_jobs)),
            'unique_jobs': int(_unique_job_count(all_jobs)),
            'filtered_jobs': int(sum(1 for job in all_jobs if filter_job(job.get('jobName', ''), config))),
            'matched_jobs': int(matched_jobs),
            'matched_company_count': int(len(company_data)),
            'job_detail_count': int(sum(len(info.get('jobs', [])) for info in company_data.values())),
        },
        'special_value_counts': {
            'unlimited_ratio_999': int((result_df['徵人需求度'] == 999.0).sum()) if not result_df.empty else 0,
            'unspecified_ratio_998': int((result_df['徵人需求度'] == 998.0).sum()) if not result_df.empty else 0,
            'employee_count_zero_with_jobs': int(
                ((result_df['員工人數'] <= 0) & (result_df['總職缺數'] > 0)).sum()
            ) if not result_df.empty else 0,
        },
    }


def write_run_manifest(manifest: dict, output_dir: str) -> Path:
    """Write per-run and latest manifest files."""
    runs_dir = Path(output_dir) / 'runs'
    run_root = runs_dir / manifest['run_id']
    run_root.mkdir(parents=True, exist_ok=True)
    manifest_path = run_root / 'hiring_run_manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    latest_path = runs_dir / 'latest_hiring_run_manifest.json'
    latest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f"已寫入 run manifest: {manifest_path}")
    logger.info(f"已更新 latest manifest: {latest_path}")
    workflow_paths = write_workflow_governance_artifacts(
        manifest,
        run_root=run_root,
        hiring_manifest_path=manifest_path,
    )
    logger.info(f"已寫入 workflow manifest: {workflow_paths['workflow_manifest']}")
    logger.info(f"已寫入 workflow trace receipt: {workflow_paths['workflow_trace_receipt']}")
    return manifest_path


# ==================== 輸出 ====================

def save_to_csv(df: pd.DataFrame, output_dir: str) -> Path:
    """儲存 CSV"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime('%Y%m%d')
    csv_file = output_path / f"{date_str}_hiring_demand.csv"

    # 準備輸出（需求度顯示用）
    df_out = df.copy()
    df_out['更新時間'] = datetime.now().strftime('%Y-%m-%d')

    df_out.to_csv(csv_file, index=False, encoding='utf-8-sig')
    logger.info(f"已儲存 CSV: {csv_file}")

    return csv_file


def save_to_database(df: pd.DataFrame, db_path: str) -> int:
    """寫入資料庫"""
    db_file = Path(db_path)

    if not db_file.parent.exists():
        logger.error(f"資料庫目錄不存在: {db_file.parent}")
        return 0

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # 建表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hiring_demand (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            company_short_name TEXT NOT NULL,
            company_full_name TEXT,
            market_type TEXT,
            employee_count INTEGER DEFAULT 0,
            explicit_need INTEGER DEFAULT 0,
            unlimited_job_count INTEGER DEFAULT 0,
            unspecified_job_count INTEGER DEFAULT 0,
            total_job_count INTEGER DEFAULT 0,
            demand_ratio REAL DEFAULT 0.0,
            fetch_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, fetch_date)
        )
    ''')

    # 向下相容：若舊表不存在 unspecified_job_count 欄位，自動新增
    try:
        cursor.execute('ALTER TABLE hiring_demand ADD COLUMN unspecified_job_count INTEGER DEFAULT 0')
        logger.info("已新增 unspecified_job_count 欄位（資料庫升級）")
    except sqlite3.OperationalError:
        pass  # 欄位已存在

    # 建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hiring_stock_code ON hiring_demand(stock_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hiring_fetch_date ON hiring_demand(fetch_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hiring_demand_ratio ON hiring_demand(demand_ratio)')

    # 寫入資料
    fetch_date = datetime.now().strftime('%Y-%m-%d')

    # 先刪除當天舊資料（避免多次執行時殘留不同公司的資料）
    cursor.execute('DELETE FROM hiring_demand WHERE fetch_date = ?', (fetch_date,))

    inserted = 0

    for _, row in df.iterrows():
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO hiring_demand
                (stock_code, company_short_name, company_full_name, market_type,
                 employee_count, explicit_need, unlimited_job_count, unspecified_job_count,
                 total_job_count, demand_ratio, fetch_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                row['股票代碼'], row['公司簡稱'], row['公司全名'], row['市場類別'],
                int(row['員工人數']), int(row['明確需求人數']),
                int(row['不限職缺數']), int(row['未標示職缺數']),
                int(row['總職缺數']),
                float(row['徵人需求度']), fetch_date
            ))
            inserted += 1
        except Exception as e:
            logger.error(f"寫入失敗 ({row['股票代碼']}): {e}")

    conn.commit()
    conn.close()

    logger.info(f"已寫入資料庫: {db_file} ({inserted} 筆)")
    return inserted


def save_jobs_to_database(company_data: dict, db_path: str) -> int:
    """寫入職缺明細到資料庫（供網頁子表格展開使用）"""
    db_file = Path(db_path)

    if not db_file.parent.exists():
        logger.error(f"資料庫目錄不存在: {db_file.parent}")
        return 0

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # 建表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hiring_demand_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            job_name TEXT NOT NULL,
            link_job_id TEXT,
            need_emp_raw TEXT,
            need_emp INTEGER DEFAULT 0,
            is_unlimited INTEGER DEFAULT 0,
            is_unspecified INTEGER DEFAULT 0,
            fetch_date TEXT NOT NULL,
            UNIQUE(stock_code, link_job_id, fetch_date)
        )
    ''')

    # 建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hdj_stock ON hiring_demand_jobs(stock_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hdj_date ON hiring_demand_jobs(fetch_date)')

    # 寫入資料
    fetch_date = datetime.now().strftime('%Y-%m-%d')

    # 先刪除當天舊資料（避免重複）
    cursor.execute('DELETE FROM hiring_demand_jobs WHERE fetch_date = ?', (fetch_date,))

    inserted = 0
    for stock_code, info in company_data.items():
        for job in info['jobs']:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO hiring_demand_jobs
                    (stock_code, job_name, link_job_id, need_emp_raw, need_emp,
                     is_unlimited, is_unspecified, fetch_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stock_code,
                    job['job_name'],
                    job.get('link_job_id', ''),
                    job.get('need_emp_raw', ''),
                    job.get('need_emp', 0),
                    1 if job.get('is_unlimited') else 0,
                    1 if job.get('is_unspecified') else 0,
                    fetch_date
                ))
                inserted += 1
            except Exception as e:
                logger.error(f"寫入職缺明細失敗 ({stock_code} - {job['job_name']}): {e}")

    conn.commit()
    conn.close()

    logger.info(f"已寫入職缺明細資料庫: {db_file} ({inserted} 筆)")
    return inserted


# ==================== 主程式 ====================

def main():
    """主程式"""
    start_time = datetime.now()
    run_id = start_time.strftime('%Y%m%d_%H%M%S_hiring_demand')
    run_mode = os.environ.get('HIRING_DEMAND_RUN_MODE', 'write-db').strip() or 'write-db'
    if run_mode not in VALID_RUN_MODES:
        logger.error(f"不支援的 HIRING_DEMAND_RUN_MODE: {run_mode}")
        send_notification("徵人需求度更新失敗", f"不支援的 run mode: {run_mode}")
        return False

    logger.info("=" * 60)
    logger.info("上市櫃公司徵人需求度擷取程式")
    logger.info(f"執行時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"run mode: {run_mode}")
    logger.info("=" * 60)

    try:
        # 載入設定
        config = load_config()

        # 讀取股票代碼表
        stock_df = get_latest_stock_codes(config['paths']['stock_codes_dir'])
        stock_codes_file = Path(stock_df.attrs.get('source_file', ''))

        # 搜尋各關鍵字的職缺
        all_jobs = []
        for keyword in config['search_keywords']:
            jobs = search_104_jobs(keyword, config)
            all_jobs.extend(jobs)
            logger.info("")

        if not all_jobs:
            logger.warning("未搜尋到任何職缺，程式結束")
            send_notification("徵人需求度", "未搜尋到任何職缺")
            return False

        # 彙整公司資料（包含呼叫詳情 API 取得 needEmp）
        company_data = aggregate_company_data(all_jobs, stock_df, config)

        if not company_data:
            logger.warning("未匹配到任何上市櫃公司，程式結束")
            send_notification("徵人需求度", "未匹配到任何上市櫃公司")
            return False

        # 計算需求度
        result_df = calculate_demand(company_data, config)

        # 儲存結果
        csv_path = save_to_csv(result_df, config['paths']['output_dir'])

        if run_mode == 'scrape-only':
            logger.info("scrape-only mode：略過 DB 與職缺明細寫入")
            db_inserted_count = 0
            job_inserted_count = 0
        else:
            db_inserted_count = save_to_database(result_df, config['paths']['db_path'])

            # 儲存職缺明細（供網頁子表格展開使用）
            job_inserted_count = save_jobs_to_database(company_data, config['paths']['db_path'])

        # 統計
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        manifest = build_run_manifest(
            run_id=run_id,
            run_mode=run_mode,
            status='success',
            started_at=start_time,
            ended_at=end_time,
            config=config,
            stock_codes_file=stock_codes_file,
            all_jobs=all_jobs,
            company_data=company_data,
            result_df=result_df,
            csv_path=csv_path,
            db_inserted_count=db_inserted_count,
            job_inserted_count=job_inserted_count,
        )
        manifest_path = write_run_manifest(manifest, config['paths']['output_dir'])

        logger.info("")
        logger.info("=" * 60)
        logger.info("擷取完成！")
        logger.info(f"  上市櫃公司數: {len(result_df)}")
        if not result_df.empty:
            high_demand = result_df[(result_df['徵人需求度'] >= 15) & (result_df['徵人需求度'] < 999)].shape[0]
            unlimited = result_df[result_df['徵人需求度'] == 999.0].shape[0]
            logger.info(f"  需求度 ≥15%: {high_demand} 家")
            logger.info(f"  人數不限: {unlimited} 家")
        logger.info(f"  執行時間: {duration:.1f} 秒")
        logger.info(f"  CSV 檔案: {csv_path}")
        logger.info(f"  Run manifest: {manifest_path}")
        logger.info("=" * 60)

        # 發送通知
        send_notification(
            "徵人需求度更新完成",
            f"共 {len(result_df)} 家公司，耗時 {duration:.1f} 秒"
        )

        return True

    except Exception as e:
        logger.error(f"執行失敗: {e}", exc_info=True)
        send_notification("徵人需求度更新失敗", f"錯誤: {str(e)[:50]}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
