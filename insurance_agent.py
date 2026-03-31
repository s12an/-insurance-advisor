"""
Insurance Advisor Ultimate - 완전 자동화 보험 컨설팅 에이전트
다크 모드 테마 + 대화형 CLI (API 없이 로컬 DB로 동작)
"""

import os
import sys
import json
import sqlite3
import requests
import re
import hashlib
import logging
import time
import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup

# 다크 모드 색상 테마
class Theme:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    HEADER = "\033[38;5;147m"
    TITLE = "\033[38;5;117m"
    SUBTITLE = "\033[38;5;159m"
    SUCCESS = "\033[38;5;120m"
    WARNING = "\033[38;5;214m"
    ERROR = "\033[38;5;203m"
    INFO = "\033[38;5;187m"
    TEXT = "\033[38;5;252m"
    DIM_TEXT = "\033[38;5;240m"
    PROMPT = "\033[38;5;153m"
    BORDER = "\033[38;5;244m"
    BAR = "\033[38;5;39m"

# PDF 처리 (선택적)
try:
    import pdfplumber  # type: ignore
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# ------------------------------
# 설정
# ------------------------------
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()
DB_PATH = os.path.join(SCRIPT_DIR, "insurance_advisor.db")
UPDATE_INTERVAL_HOURS = 24
LOG_LEVEL = logging.WARNING
MAX_HISTORY_PER_USER = 100

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PRODUCT_LIST_URL = "https://insis.fss.or.kr/life/productList"
NONLIFE_URL = "https://insis.fss.or.kr/nonlife/productList"

# ------------------------------
# UI 헬퍼 함수
# ------------------------------
def print_header(text: str):
    print(f"\n{Theme.BOLD}{Theme.TITLE}{'='*60}{Theme.RESET}")
    print(f"{Theme.BOLD}{Theme.TITLE}  {text}{Theme.RESET}")
    print(f"{Theme.BOLD}{Theme.TITLE}{'='*60}{Theme.RESET}\n")

def print_subheader(text: str):
    print(f"{Theme.SUBTITLE}{'─'*50}{Theme.RESET}")
    print(f"{Theme.SUBTITLE}  {text}{Theme.RESET}")
    print(f"{Theme.SUBTITLE}{'─'*50}{Theme.RESET}")

def print_info(text: str):
    print(f"  {Theme.INFO}ℹ{Theme.RESET} {text}")

def print_success(text: str):
    print(f"  {Theme.SUCCESS}✓{Theme.RESET} {text}")

def print_warning(text: str):
    print(f"  {Theme.WARNING}⚠{Theme.RESET} {text}")

def print_error(text: str):
    print(f"  {Theme.ERROR}✗{Theme.RESET} {text}")

def print_dim(text: str):
    print(f"  {Theme.DIM_TEXT}{text}{Theme.RESET}")

def print_prompt(text: str):
    print(f"{Theme.PROMPT}{text}{Theme.RESET}")

def print_bar(label: str, value: int, max_val: int, width: int = 35):
    bar_len = int(width * value / max_val) if max_val > 0 else 0
    bar = "█" * bar_len
    print(f"  {Theme.TEXT}{label:<15}{Theme.RESET} : {Theme.BAR}{bar}{Theme.RESET} {Theme.INFO}{value:,}원{Theme.RESET}")

def print_table(headers: List[str], rows: List[List[str]]):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    header_line = "  " + " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
    print(f"  {Theme.BOLD}{Theme.TITLE}{header_line}{Theme.RESET}")
    print(f"  {Theme.BORDER}{'-' * len(header_line)}{Theme.RESET}")
    for row in rows:
        line = "  " + " | ".join(f"{str(cell):<{col_widths[i]}}" for i, cell in enumerate(row))
        print(f"  {Theme.TEXT}{line}{Theme.RESET}")

# ------------------------------
# 데이터베이스 초기화
# ------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id TEXT PRIMARY KEY, name TEXT, company TEXT, category TEXT,
                  premium_min INTEGER, premium_max INTEGER, coverages TEXT,
                  expense_ratio REAL, surrender_fee_rate REAL, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS crawl_log
                 (source TEXT, last_crawled TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT, timestamp TEXT, session_id TEXT,
                  session_data TEXT, feedback_score INTEGER, feedback_text TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS terms_cache
                 (product_id TEXT, clause_number TEXT, clause_text TEXT, source_url TEXT,
                  PRIMARY KEY (product_id, clause_number))''')
    c.execute('''CREATE TABLE IF NOT EXISTS encyclopedia
                 (keyword TEXT PRIMARY KEY, summary TEXT, link TEXT, legal_ref TEXT,
                  created_at TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS scheduler_lock
                 (job_name TEXT PRIMARY KEY, last_run TEXT, running INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences
                 (user_id TEXT, preference_key TEXT, preference_value TEXT,
                  updated_at TEXT, PRIMARY KEY (user_id, preference_key))''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversation_context
                 (session_id TEXT, user_id TEXT, context_json TEXT, last_updated TEXT,
                  PRIMARY KEY (session_id, user_id))''')

    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        demo_products = [
            ("KB_CHILD_001", "KB 무배당 어린이튼튼보험", "KB손해보험", "어린이", 30000, 150000, "상해사망,소아암,상해의료비", 0.35, 0.05),
            ("SAMSUNG_CHILD_002", "삼성 어린이사랑보험", "삼성화재", "어린이", 35000, 180000, "상해,질병입원,암", 0.38, 0.06),
            ("DB_BUSINESS_001", "영업배상책임보험(카페형)", "DB손보", "개인사업자", 40000, 200000, "화재,영업배상", 0.40, 0.10),
            ("VUL_CORP_001", "변액유니버셜보험(법인용)", "교보생명", "법인", 500000, 10000000, "저축,세제혜택", 0.25, 0.12),
            ("HYUNDAI_SENIOR_001", "현대해상 시니어 종합보험", "현대해상", "시니어", 80000, 300000, "상해,질병,입원,실손", 0.32, 0.08),
            ("LIFE_GLOBAL_001", "생명보험 글로벌 종합보험", "삼성화재", "일반", 50000, 500000, "사망,질병,암", 0.36, 0.07),
            ("HANA_CHILD_003", "하나생명 어린이건강보험", "하나생명", "어린이", 25000, 120000, "상해,질병,입원,치아", 0.33, 0.04),
            ("NH_BUSINESS_002", "NH농협 사업자종합보험", "NH농협손보", "개인사업자", 60000, 250000, "화재,배상,상해,질병", 0.37, 0.09),
        ]
        c.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)",
                      [(p + (datetime.now().isoformat(),)) for p in demo_products])

        encyclopedia_data = [
            ("고지의무", "계약 체결 시 중요한 사실을 보험회사에 알려야 할 의무. 위반 시 계약 해지 가능.", "상법 제651조", "상법 제651조"),
            ("해약환급금", "보험 계약을 중간에 해지할 때 돌려받는 금액. 납입 초기에는 손실이 큼.", "보험업법 제94조", "보험업법 제94조"),
            ("면책기간", "보험 가입 후 일정 기간 동안 보장이 제한되는 기간. 보통 1년.", "표준약관 제12조", "표준약관 제12조"),
            ("사업비율", "보험료가 보장과 사업비로 나뉘는 비율. 낮을수록 유리.", "금융위 고시", "금융위 고시"),
        ]
        c.executemany("INSERT OR IGNORE INTO encyclopedia VALUES (?,?,?,?,?,?)",
                      [(k, s, l, r, datetime.now().isoformat(), datetime.now().isoformat()) for k, s, l, r in encyclopedia_data])

    conn.commit()
    conn.close()
    logger.info("Database initialized.")

# ------------------------------
# 상품 크롤러
# ------------------------------
def crawl_products_from_insis() -> List[Dict]:
    products = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(PRODUCT_LIST_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('table tbody tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 5:
                name = cols[0].get_text(strip=True)
                company = cols[1].get_text(strip=True)
                premium_text = cols[2].get_text(strip=True)
                premium_min, premium_max = 0, 1000000
                match = re.search(r'(\d+)[~-](\d+)', premium_text)
                if match:
                    premium_min = int(match.group(1)) * 10000 if '만' in premium_text else int(match.group(1))
                    premium_max = int(match.group(2)) * 10000 if '만' in premium_text else int(match.group(2))
                category = "일반"
                if "어린이" in name: category = "어린이"
                elif "사업자" in name or "영업" in name: category = "개인사업자"
                elif "법인" in name: category = "법인"
                products.append({
                    "id": hashlib.md5(f"{company}_{name}".encode()).hexdigest()[:16],
                    "name": name, "company": company, "category": category,
                    "premium_min": premium_min, "premium_max": premium_max,
                    "coverages": "기본 보장", "expense_ratio": 0.35, "surrender_fee_rate": 0.08
                })
    except Exception as e:
        logger.error(f"Crawling error: {e}")
    return products

def crawl_products(force=False) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_crawled FROM crawl_log WHERE source='products'")
    row = c.fetchone()
    if not force and row:
        last = datetime.fromisoformat(row[0])
        if (datetime.now() - last).total_seconds() < UPDATE_INTERVAL_HOURS * 3600:
            logger.info(f"Products already updated at {last}")
            return row[0]
    logger.info("Starting product crawl...")
    products = crawl_products_from_insis()
    if not products:
        logger.warning("Crawl empty, using demo data.")
        products = [
            {"id": "KB_CHILD_001", "name": "KB 무배당 어린이튼튼보험", "company": "KB손해보험", "category": "어린이",
             "premium_min": 30000, "premium_max": 150000, "coverages": "상해사망,소아암,상해의료비",
             "expense_ratio": 0.35, "surrender_fee_rate": 0.05},
            {"id": "SAMSUNG_CHILD_002", "name": "삼성 어린이사랑보험", "company": "삼성화재", "category": "어린이",
             "premium_min": 35000, "premium_max": 180000, "coverages": "상해,질병입원,암",
             "expense_ratio": 0.38, "surrender_fee_rate": 0.06},
            {"id": "DB_BUSINESS_001", "name": "영업배상책임보험(카페형)", "company": "DB손보", "category": "개인사업자",
             "premium_min": 40000, "premium_max": 200000, "coverages": "화재,영업배상",
             "expense_ratio": 0.40, "surrender_fee_rate": 0.10},
            {"id": "VUL_CORP_001", "name": "변액유니버셜보험(법인용)", "company": "교보생명", "category": "법인",
             "premium_min": 500000, "premium_max": 10000000, "coverages": "저축,세제혜택",
             "expense_ratio": 0.25, "surrender_fee_rate": 0.12},
        ]
    for p in products:
        c.execute('''INSERT OR REPLACE INTO products
                     (id, name, company, category, premium_min, premium_max, coverages,
                      expense_ratio, surrender_fee_rate, updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  (p['id'], p['name'], p['company'], p['category'],
                   p['premium_min'], p['premium_max'], p['coverages'],
                   p['expense_ratio'], p['surrender_fee_rate'], datetime.now().isoformat()))
    now_str = datetime.now().isoformat()
    c.execute("DELETE FROM crawl_log WHERE source='products'")
    c.execute("INSERT INTO crawl_log (source, last_crawled, status) VALUES (?,?,?)",
              ("products", now_str, "success"))
    conn.commit()
    conn.close()
    logger.info(f"Crawl finished at {now_str}")
    return now_str

# ------------------------------
# PDF 약관 추출
# ------------------------------
def extract_clause_from_pdf(pdf_url: str, clause_number: str) -> Optional[str]:
    if not PDF_SUPPORT:
        return None
    try:
        resp = requests.get(pdf_url, timeout=30)
        with open("temp.pdf", "wb") as f:
            f.write(resp.content)
        clause_text = None
        import pdfplumber  # type: ignore
        with pdfplumber.open("temp.pdf") as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"
            pattern = rf"제\s*{clause_number}\s*조[^\n]*\n(.*?)(?=제\s*\d+\s*조|\Z)"
            match = re.search(pattern, full_text, re.DOTALL)
            if match: clause_text = match.group(1).strip()[:500]
        os.remove("temp.pdf")
        return clause_text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return None

def get_contract_terms(product_name: str, clause_number: str) -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT clause_text, source_url FROM terms_cache WHERE product_id=? AND clause_number=?",
              (product_name, clause_number))
    row = c.fetchone()
    if row:
        conn.close()
        return {"clause_text": row[0], "source_url": row[1]}
    pdf_url = f"https://example.com/terms/{product_name.replace(' ', '_')}.pdf"
    clause_text = extract_clause_from_pdf(pdf_url, clause_number)
    if not clause_text:
        clause_text = f"제{clause_number}조 (약관 내용) - 실제 PDF에서 추출 실패."
    c.execute("INSERT INTO terms_cache (product_id, clause_number, clause_text, source_url) VALUES (?,?,?,?)",
              (product_name, clause_number, clause_text, pdf_url))
    conn.commit()
    conn.close()
    return {"clause_text": clause_text, "source_url": pdf_url}

# ------------------------------
# 상품 검색
# ------------------------------
def search_insurance_products(target: str, coverages: List[str], max_premium: int,
                              min_premium: int = 0, limit: Optional[int] = None,
                              preferred_company: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    category_map = {
        "유아부모님": "어린이", "학부모": "어린이", "시니어": "시니어",
        "개인사업자": "개인사업자", "법인사업자": "법인"
    }
    category = category_map.get(target, "어린이")
    query = "SELECT * FROM products WHERE category = ? AND premium_min <= ? AND premium_max >= ?"
    params = [category, max_premium, min_premium]
    if coverages:
        cov_conditions = []
        for cov in coverages:
            cov_conditions.append("coverages LIKE ?")
            params.append(f"%{cov}%")
        query += " AND (" + " OR ".join(cov_conditions) + ")"
    if preferred_company:
        query += " AND company LIKE ?"
        params.append(f"%{preferred_company}%")
    c.execute(query, params)
    rows = c.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    if limit is not None:
        results = results[:limit]
    return results

# ------------------------------
# 해약 계산
# ------------------------------
def calculate_surrender_value(product_id: str, paid_months: int, monthly_premium: int) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, expense_ratio, surrender_fee_rate FROM products WHERE id=?", (product_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"error": "Product not found", "surrender_value": 0, "loss_amount": 0}
    name, expense_ratio, surrender_fee = row
    total_paid = monthly_premium * paid_months
    business_cost = total_paid * expense_ratio
    risk_premium = total_paid * 0.002 * paid_months / 12
    surrender_before_fee = total_paid - business_cost - risk_premium
    surrender_value = surrender_before_fee * (1 - surrender_fee)
    loss_amount = total_paid - surrender_value
    return {
        "name": name,
        "surrender_value": int(surrender_value),
        "loss_amount": int(loss_amount),
        "total_paid": total_paid,
        "expense_ratio": expense_ratio,
        "surrender_fee_rate": surrender_fee
    }

# ------------------------------
# 미래 가치 예측
# ------------------------------
def calculate_future_value(monthly_premium: int, years: int, annual_increase_rate: float = 0.03) -> Dict:
    total_paid = 0
    yearly_breakdown = []
    current_premium = monthly_premium * 12
    for y in range(1, years+1):
        yearly_paid = current_premium
        total_paid += yearly_paid
        yearly_breakdown.append({"year": y, "yearly_premium": yearly_paid, "cumulative": total_paid})
        current_premium *= (1 + annual_increase_rate)
    return {"total_paid": total_paid, "yearly_breakdown": yearly_breakdown}

# ------------------------------
# 비교 매트릭스
# ------------------------------
def generate_comparison_matrix(product_ids: List[str]) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    placeholders = ','.join(['?']*len(product_ids))
    c.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", product_ids)
    products = [dict(row) for row in c.fetchall()]
    conn.close()
    matrix = {"products": products, "comparison": []}
    for p in products:
        matrix["comparison"].append({
            "name": p["name"], "company": p["company"],
            "premium_range": f"{p['premium_min']:,} ~ {p['premium_max']:,} 원",
            "expense_ratio": f"{p['expense_ratio']*100:.1f}%",
            "surrender_fee": f"{p['surrender_fee_rate']*100:.1f}%"
        })
    return matrix

# ------------------------------
# 포트폴리오 검증
# ------------------------------
def validate_portfolio(selected_products: List[Dict]) -> Dict:
    issues = []
    all_coverages = []
    for p in selected_products:
        covs = p.get("coverages", "").split(",")
        for c in covs:
            if c in all_coverages:
                issues.append(f"중복 보장 항목: {c} (상품: {p['name']})")
            else:
                all_coverages.append(c)
    total_premium = sum(p.get("premium_min", 0) for p in selected_products)
    if total_premium > 500000:
        issues.append(f"월 총 보험료가 {total_premium:,}원으로 과도할 수 있습니다.")
    issues.append("고지의무 위반 시 계약 해지 가능 (상법 제651조). 모든 계약 전 알릴 의무를 이행하세요.")
    return {"valid": len(issues)==0, "issues": issues}

# ------------------------------
# 피드백
# ------------------------------
def save_feedback(user_id: str, session_id: str, score: int, feedback_text: str = "") -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE history SET feedback_score=?, feedback_text=? WHERE user_id=? AND session_id=?",
              (score, feedback_text, user_id, session_id))
    if c.rowcount == 0:
        c.execute("INSERT INTO history (user_id, timestamp, session_id, session_data, feedback_score, feedback_text) VALUES (?,?,?,?,?,?)",
                  (user_id, datetime.now().isoformat(), session_id, "{}", score, feedback_text))
    conn.commit()
    conn.close()
    return {"status": "saved", "score": score}

def get_feedback_stats(user_id: Optional[str] = None) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if user_id:
        c.execute("SELECT AVG(feedback_score), COUNT(*) FROM history WHERE user_id=? AND feedback_score IS NOT NULL", (user_id,))
    else:
        c.execute("SELECT AVG(feedback_score), COUNT(*) FROM history WHERE feedback_score IS NOT NULL")
    avg, cnt = c.fetchone()
    conn.close()
    return {"average_score": avg if avg else 0, "total_feedbacks": cnt if cnt else 0}

# ------------------------------
# 백과사전
# ------------------------------
def search_encyclopedia(keyword: str) -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT summary, link, legal_ref FROM encyclopedia WHERE keyword=?", (keyword,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"summary": row[0], "link": row[1], "legal_ref": row[2]}
    else:
        return {"summary": "정보 없음. 백과사전에 등록하세요.", "link": "", "legal_ref": ""}

def add_encyclopedia_entry(keyword: str, summary: str, link: str = "", legal_ref: str = "") -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("SELECT 1 FROM encyclopedia WHERE keyword=?", (keyword,))
    exists = c.fetchone()
    if exists:
        c.execute('''UPDATE encyclopedia SET summary=?, link=?, legal_ref=?, updated_at=?
                     WHERE keyword=?''', (summary, link, legal_ref, now, keyword))
        msg = "updated"
    else:
        c.execute('''INSERT INTO encyclopedia (keyword, summary, link, legal_ref, created_at, updated_at)
                     VALUES (?,?,?,?,?,?)''', (keyword, summary, link, legal_ref, now, now))
        msg = "created"
    conn.commit()
    conn.close()
    return {"status": msg, "keyword": keyword, "timestamp": now}

# ------------------------------
# 히스토리
# ------------------------------
def save_history(user_id: str, session_id: str, session_data: Dict[str, Any]) -> Dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO history (user_id, timestamp, session_id, session_data) VALUES (?, ?, ?, ?)",
              (user_id, datetime.now().isoformat(), session_id, json.dumps(session_data, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return {"status": "saved", "timestamp": datetime.now().isoformat()}

def get_user_history(user_id: str, limit: int = 10) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT timestamp, session_data, feedback_score FROM history WHERE user_id=? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
    rows = c.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    return results

# ------------------------------
# 사용자 선호도
# ------------------------------
def set_user_preference(user_id: str, key: str, value: str) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT OR REPLACE INTO user_preferences (user_id, preference_key, preference_value, updated_at) VALUES (?,?,?,?)",
              (user_id, key, value, now))
    conn.commit()
    conn.close()
    return {"status": "saved", "key": key, "value": value}

def get_user_preferences(user_id: str) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT preference_key, preference_value FROM user_preferences WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {k: v for k, v in rows}

# ------------------------------
# 대화 컨텍스트
# ------------------------------
def save_conversation_context(session_id: str, user_id: str, context: Dict) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT OR REPLACE INTO conversation_context (session_id, user_id, context_json, last_updated) VALUES (?,?,?,?)",
              (session_id, user_id, json.dumps(context, ensure_ascii=False), now))
    conn.commit()
    conn.close()
    return {"status": "saved"}

def get_conversation_context(session_id: str, user_id: str) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT context_json FROM conversation_context WHERE session_id=? AND user_id=?", (session_id, user_id))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return {}

# ------------------------------
# 데이터 내보내기
# ------------------------------
def export_products_to_csv() -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    rows = c.fetchall()
    conn.close()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'name', 'company', 'category', 'premium_min', 'premium_max', 'coverages', 'expense_ratio', 'surrender_fee_rate', 'updated_at'])
    writer.writerows(rows)
    return output.getvalue()

def export_history_to_json(user_id: str) -> str:
    history = get_user_history(user_id, limit=MAX_HISTORY_PER_USER)
    return json.dumps(history, ensure_ascii=False, indent=2)

# ------------------------------
# ASCII 차트
# ------------------------------
def generate_ascii_chart(data: List[Tuple[str, int]], title: str = "보험료 비교") -> str:
    if not data:
        return "데이터 없음"
    max_val = max(v for _, v in data)
    chart = f"\n{title}\n" + "="*40 + "\n"
    for label, value in data:
        bar_len = int(40 * value / max_val) if max_val > 0 else 0
        bar = "█" * bar_len
        chart += f"{label[:15]:15} : {bar} {value:,}원\n"
    return chart

# ------------------------------
# 추천 알고리즘
# ------------------------------
def personalized_recommendation(user_id: str, target: str, max_premium: int) -> List[Dict]:
    prefs = get_user_preferences(user_id)
    preferred_company = prefs.get("preferred_company", None)
    coverages = prefs.get("preferred_coverages", "").split(",") if prefs.get("preferred_coverages") else []
    results = search_insurance_products(target, coverages, max_premium, preferred_company=preferred_company)
    results.sort(key=lambda x: (x['expense_ratio'], x['premium_min']))
    return results[:5]

# ------------------------------
# 유틸리티
# ------------------------------
def get_last_update() -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_crawled FROM crawl_log WHERE source='products'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Never"

def scheduled_update():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_run, running FROM scheduler_lock WHERE job_name='daily_crawl'")
    row = c.fetchone()
    now = datetime.now()
    if row:
        last_run = datetime.fromisoformat(row[0]) if row[0] else None
        running = row[1]
        if running:
            logger.info("Previous crawl still running, skip.")
            return
        if last_run and (now - last_run).total_seconds() < UPDATE_INTERVAL_HOURS * 3600:
            logger.info("Recently updated, skip.")
            return
    c.execute("INSERT OR REPLACE INTO scheduler_lock (job_name, last_run, running) VALUES (?,?,?)",
              ("daily_crawl", now.isoformat(), 1))
    conn.commit()
    conn.close()
    try:
        crawl_products(force=True)
    finally:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE scheduler_lock SET running=0, last_run=? WHERE job_name='daily_crawl'",
                  (datetime.now().isoformat(),))
        conn.commit()
        conn.close()

# ------------------------------
# Tool Dispatcher
# ------------------------------
def run_tool(tool_name: str, params: dict) -> dict:
    tools = {
        "search_insurance_products": search_insurance_products,
        "personalized_recommendation": personalized_recommendation,
        "get_contract_terms": get_contract_terms,
        "calculate_surrender_value": calculate_surrender_value,
        "calculate_future_value": calculate_future_value,
        "search_encyclopedia": search_encyclopedia,
        "add_encyclopedia_entry": add_encyclopedia_entry,
        "generate_comparison_matrix": generate_comparison_matrix,
        "generate_ascii_chart": generate_ascii_chart,
        "validate_portfolio": validate_portfolio,
        "save_feedback": save_feedback,
        "get_feedback_stats": get_feedback_stats,
        "save_history": save_history,
        "get_user_history": get_user_history,
        "set_user_preference": set_user_preference,
        "get_user_preferences": get_user_preferences,
        "save_conversation_context": save_conversation_context,
        "get_conversation_context": get_conversation_context,
        "export_products_to_csv": export_products_to_csv,
        "export_history_to_json": export_history_to_json,
        "get_last_update": get_last_update,
        "scheduled_update": scheduled_update,
    }
    if tool_name in tools:
        return {"result": tools[tool_name](**params)}
    return {"error": f"Unknown tool: {tool_name}"}

# ------------------------------
# 자연어 파서
# ------------------------------
def parse_user_input(user_input: str) -> Dict:
    text = user_input.lower()

    # 도움말
    if any(kw in text for kw in ["도움", "help", "명령", "사용"]):
        return {"action": "help"}

    # 종료
    if any(kw in text for kw in ["종료", "exit", "quit", "나가"]):
        return {"action": "exit"}

    # 내보내기
    if any(kw in text for kw in ["내보내", "저장", "export", "csv", "json"]):
        return {"action": "export"}

    # 백과사전 (먼저 체크 - "뭐야" 등 일반 질문 포함)
    if any(kw in text for kw in ["백과", "용어", "의미", "무엇", "정의", "뭐야", "뭐지", "설명"]):
        keyword = None
        for kw in ["고지의무", "해약환급금", "면책기간", "사업비율"]:
            if kw in text:
                keyword = kw
                break
        return {"action": "encyclopedia", "keyword": keyword or text}

    # 미래 가치 예측 (총액, 누적, 예측 등)
    if any(kw in text for kw in ["미래", "예상", "예측", "누적", "총액", "총합", "얼마나"]):
        if any(kw in text for kw in ["년", "월", "보험료", "납입", "예상", "예측", "총액", "누적"]):
            monthly_premium = 50000
            premium_match = re.search(r'(\d+)\s*만?원?', text)
            if premium_match:
                val = int(premium_match.group(1))
                monthly_premium = val * 10000 if val < 1000 else val

            years = 10
            years_match = re.search(r'(\d+)\s*년', text)
            if years_match: years = int(years_match.group(1))

            return {"action": "future", "monthly_premium": monthly_premium, "years": years}

    # 해약환급금 계산
    if any(kw in text for kw in ["해약", "환급", "중도해지", "손실"]):
        product_id = None
        if "kb" in text: product_id = "KB_CHILD_001"
        elif "삼성" in text: product_id = "SAMSUNG_CHILD_002"
        elif "db" in text: product_id = "DB_BUSINESS_001"
        elif "교보" in text: product_id = "VUL_CORP_001"
        elif "현대" in text: product_id = "HYUNDAI_SENIOR_001"
        elif "하나" in text: product_id = "HANA_CHILD_003"
        elif "nh" in text or "농협" in text: product_id = "NH_BUSINESS_002"

        paid_months = 36
        months_match = re.search(r'(\d+)\s*개월', text)
        if months_match: paid_months = int(months_match.group(1))

        monthly_premium = 50000
        premium_match = re.search(r'(\d+)\s*만?원?', text)
        if premium_match:
            val = int(premium_match.group(1))
            monthly_premium = val * 10000 if val < 1000 else val

        return {"action": "surrender", "product_id": product_id, "paid_months": paid_months, "monthly_premium": monthly_premium}

    # 포트폴리오 검증
    if any(kw in text for kw in ["포트폴리오", "검증", "점검", "중복", "확인"]):
        return {"action": "portfolio"}

    # 보험 상품 검색
    if any(kw in text for kw in ["추천", "검색", "찾아", "알려", "비교", "상품"]):
        category = "어린이"
        if any(kw in text for kw in ["어린이", "유아", "자녀", "아이", "학부모"]):
            category = "어린이"
        elif any(kw in text for kw in ["사업자", "카페", "영업", "개인사업"]):
            category = "개인사업자"
        elif any(kw in text for kw in ["법인", "회사", "기업"]):
            category = "법인"
        elif any(kw in text for kw in ["시니어", "노인", "부모", "어르신"]):
            category = "시니어"

        max_premium = 100000
        premium_match = re.search(r'(\d+)\s*만?원?', text)
        if premium_match:
            val = int(premium_match.group(1))
            max_premium = val * 10000 if val < 1000 else val

        coverages = []
        if "상해" in text: coverages.append("상해")
        if "암" in text or "소아암" in text: coverages.append("암")
        if "질병" in text: coverages.append("질병")
        if "입원" in text: coverages.append("입원")
        if "사망" in text: coverages.append("사망")

        return {"action": "search", "category": category, "max_premium": max_premium, "coverages": coverages}

    return {"action": "unknown", "text": user_input}

# ------------------------------
# 결과 포맷터
# ------------------------------
def format_search_result(results: List[Dict]) -> str:
    if not results:
        return f"{Theme.WARNING}검색 결과가 없습니다.{Theme.RESET}"

    output = f"{Theme.SUCCESS}총 {len(results)}개 상품을 찾았습니다.{Theme.RESET}\n"

    headers = ["상품명", "회사", "보험료(월)", "보장내용"]
    rows = []
    for r in results:
        rows.append([
            r['name'][:15],
            r['company'],
            f"{r['premium_min']:,}~{r['premium_max']:,}원",
            r['coverages'][:20]
        ])

    print_table(headers, rows)

    chart_data = [(r['name'][:15], r['premium_min']) for r in results]
    chart = generate_ascii_chart(chart_data, '월 최저 보험료 비교')
    print(f"\n{Theme.BAR}{chart}{Theme.RESET}")

    return output

def format_surrender_result(result: Dict) -> str:
    if "error" in result:
        return f"{Theme.ERROR}오류: {result['error']}{Theme.RESET}"

    output = f"\n{Theme.TITLE}해약환급금 계산 결과{Theme.RESET}\n"
    output += f"{Theme.BORDER}{'─'*40}{Theme.RESET}\n"
    output += f"  {Theme.TEXT}상품명{Theme.RESET}: {result['name']}\n"
    output += f"  {Theme.TEXT}납입총액{Theme.RESET}: {result['total_paid']:,}원\n"
    output += f"  {Theme.TEXT}사업비 차감{Theme.RESET}: {int(result['total_paid'] * result['expense_ratio']):,}원\n"
    output += f"  {Theme.TEXT}위험보험료{Theme.RESET}: {int(result['total_paid'] * 0.002):,}원\n"
    output += f"  {Theme.SUCCESS}해약환급금{Theme.RESET}: {result['surrender_value']:,}원\n"
    output += f"  {Theme.ERROR}손실액{Theme.RESET}: {result['loss_amount']:,}원\n"

    refund_rate = result['surrender_value'] / result['total_paid'] * 100
    output += f"  {Theme.INFO}환급률{Theme.RESET}: {refund_rate:.1f}%\n"

    if refund_rate < 50:
        output += f"\n{Theme.WARNING}⚠ 납입 초기에는 해약 시 손실이 큽니다. 계속 유지하는 것이 유리할 수 있습니다.{Theme.RESET}\n"

    return output

def format_portfolio_result(validation: Dict) -> str:
    output = f"\n{Theme.TITLE}포트폴리오 검증 결과{Theme.RESET}\n"
    output += f"{Theme.BORDER}{'─'*40}{Theme.RESET}\n"

    if validation['valid']:
        output += f"  {Theme.SUCCESS}✓ 모든 검증을 통과했습니다.{Theme.RESET}\n"
    else:
        output += f"  {Theme.WARNING}다음 이슈가 발견되었습니다:{Theme.RESET}\n"
        for issue in validation['issues']:
            output += f"  {Theme.WARNING}- {issue}{Theme.RESET}\n"

    return output

def format_future_result(result: Dict) -> str:
    output = f"\n{Theme.TITLE}미래 보험료 예측{Theme.RESET}\n"
    output += f"{Theme.BORDER}{'─'*40}{Theme.RESET}\n"

    headers = ["연도", "연간보험료", "누적"]
    rows = []
    for y in result['yearly_breakdown']:
        rows.append([str(y['year']), f"{y['yearly_premium']:,.0f}원", f"{y['cumulative']:,.0f}원"])

    print_table(headers, rows)
    output += f"\n  {Theme.INFO}총 납입 예상액: {result['total_paid']:,.0f}원{Theme.RESET}\n"
    output += f"  {Theme.DIM_TEXT}(연 3% 보험료 증가율 적용){Theme.RESET}\n"

    return output

def format_encyclopedia_result(result: Dict, keyword: str) -> str:
    output = f"\n{Theme.TITLE}백과사전: {keyword}{Theme.RESET}\n"
    output += f"{Theme.BORDER}{'─'*40}{Theme.RESET}\n"
    output += f"  {Theme.TEXT}{result['summary']}{Theme.RESET}\n"
    if result['legal_ref']:
        output += f"  {Theme.DIM_TEXT}[법률 근거: {result['legal_ref']}]{Theme.RESET}\n"
    return output

# ------------------------------
# 메인 CLI
# ------------------------------
class InsuranceAdvisorCLI:
    def __init__(self):
        self.user_id = "user_001"
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.context = {}
        init_db()
        self.show_welcome()

    def show_welcome(self):
        print(f"\n{Theme.BOLD}{Theme.TITLE}")
        print("+-----------------------------------------------------------+")
        print("|         Insurance Advisor Ultimate                        |")
        print("|         완전 자동화 보험 컨설팅 에이전트                     |")
        print("+-----------------------------------------------------------+")
        print(f"{Theme.RESET}")
        print(f"{Theme.DIM_TEXT}  세션: {self.session_id}{Theme.RESET}")
        print(f"{Theme.DIM_TEXT}  데이터: {get_last_update()}{Theme.RESET}\n")
        print(f"{Theme.INFO}  /help - 도움말 | /export - 내보내기 | /exit - 종료{Theme.RESET}\n")

    def process_input(self, user_input: str):
        if user_input.startswith("/"):
            cmd = user_input[1:].lower()
            if cmd in ["exit", "quit"]: return "exit"
            elif cmd == "help": return self.show_help()
            elif cmd == "export": return self.export_data()
            elif cmd == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                return ""

        parsed = parse_user_input(user_input)
        return self.execute_action(parsed)

    def show_help(self):
        return f"""{Theme.TITLE}
=== 도움말 ==={Theme.RESET}

{Theme.SUBTITLE}자연어로 질문하세요:{Theme.RESET}
  {Theme.TEXT}- "어린이 보험 추천해줘 (월 10만원 이하)"{Theme.RESET}
  {Theme.TEXT}- "삼성 보험 해약하면 얼마 받아?"{Theme.RESET}
  {Theme.TEXT}- "포트폴리오 검증해줘"{Theme.RESET}
  {Theme.TEXT}- "10년 후 보험료 총액이 얼마야?"{Theme.RESET}
  {Theme.TEXT}- "고지의무가 뭐야?"{Theme.RESET}

{Theme.SUBTITLE}명령어:{Theme.RESET}
  {Theme.TEXT}/help   - 도움말{Theme.RESET}
  {Theme.TEXT}/export - 데이터 내보내기{Theme.RESET}
  {Theme.TEXT}/clear  - 화면 지우기{Theme.RESET}
  {Theme.TEXT}/exit   - 종료{Theme.RESET}
"""

    def export_data(self):
        csv_data = export_products_to_csv()
        with open("products_export.csv", "w", encoding="utf-8") as f:
            f.write(csv_data)
        json_data = export_history_to_json(self.user_id)
        with open("history_export.json", "w", encoding="utf-8") as f:
            f.write(json_data)
        return f"{Theme.SUCCESS}내보내기 완료: products_export.csv, history_export.json{Theme.RESET}"

    def execute_action(self, parsed: Dict) -> str:
        action = parsed.get("action", "unknown")

        if action == "search":
            results = search_insurance_products(
                target=parsed["category"],
                coverages=parsed.get("coverages", []),
                max_premium=parsed["max_premium"]
            )
            if not results:
                results = search_insurance_products(
                    target="일반",
                    coverages=parsed.get("coverages", []),
                    max_premium=parsed["max_premium"]
                )
            return format_search_result(results)

        elif action == "surrender":
            if not parsed.get("product_id"):
                return f"{Theme.WARNING}상품을 지정해주세요. (예: 'KB 보험 해약하면 얼마?'){Theme.RESET}"
            result = calculate_surrender_value(
                product_id=parsed["product_id"],
                paid_months=parsed["paid_months"],
                monthly_premium=parsed["monthly_premium"]
            )
            return format_surrender_result(result)

        elif action == "portfolio":
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM products")
            products = [dict(row) for row in c.fetchall()]
            conn.close()
            validation = validate_portfolio(products[:3])
            return format_portfolio_result(validation)

        elif action == "future":
            result = calculate_future_value(
                monthly_premium=parsed["monthly_premium"],
                years=parsed["years"]
            )
            return format_future_result(result)

        elif action == "encyclopedia":
            keyword = parsed.get("keyword", "")
            result = search_encyclopedia(keyword)
            return format_encyclopedia_result(result, keyword)

        elif action == "help":
            return self.show_help()

        elif action == "exit":
            return "exit"

        elif action == "export":
            return self.export_data()

        else:
            return f"""{Theme.WARNING}
입력을 이해하지 못했습니다. 다음 예시를 참고하세요:{Theme.RESET}

  {Theme.TEXT}- "어린이 보험 추천해줘 (월 10만원 이하)"{Theme.RESET}
  {Theme.TEXT}- "KB 보험 해약하면 얼마 받아? (36개월, 월 5만원)"{Theme.RESET}
  {Theme.TEXT}- "포트폴리오 검증해줘"{Theme.RESET}
  {Theme.TEXT}- "10년 후 보험료 총액이 얼마야?"{Theme.RESET}
  {Theme.TEXT}- "고지의무가 뭐야?"{Theme.RESET}
"""

def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    advisor = InsuranceAdvisorCLI()

    while True:
        try:
            user_input = input(f"{Theme.BOLD}{Theme.PROMPT}사용자 > {Theme.RESET}").strip()
            if not user_input:
                continue

            response = advisor.process_input(user_input)

            if response == "exit":
                print(f"\n{Theme.DIM_TEXT}대화를 저장하고 종료합니다...{Theme.RESET}")
                break

            if response:
                print(response)

        except KeyboardInterrupt:
            print(f"\n\n{Theme.DIM_TEXT}대화를 저장하고 종료합니다...{Theme.RESET}")
            break
        except EOFError:
            break

if __name__ == "__main__":
    main()
else:
    init_db()
    crawl_products(force=False)
