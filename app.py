"""
Insurance Advisor Ultimate - Streamlit 웹앱
모바일/PC 대응 다크모드 보험 컨설팅 웹서비스
"""

import streamlit as st
import sqlite3
import json
import re
import hashlib
import csv
import os
import logging
from io import StringIO
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
import requests

# 페이지 설정
st.set_page_config(
    page_title="Insurance Advisor Ultimate",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 다크모드 CSS
st.markdown("""
<style>
    .stApp {
        background-color: #0d1117;
    }
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #58a6ff;
        text-align: center;
        padding: 1rem;
        border-bottom: 2px solid #30363d;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #7ee787;
        margin-top: 1rem;
    }
    .result-box {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .info-text {
        color: #8b949e;
        font-size: 0.9rem;
    }
    .warning-text {
        color: #d29922;
    }
    .error-text {
        color: #f85149;
    }
    .success-text {
        color: #7ee787;
    }
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: #58a6ff;
    }
    .metric-label {
        color: #8b949e;
        font-size: 0.8rem;
    }
    div[data-testid="stExpander"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
    }
    .stDataFrame {
        background-color: #161b22;
    }
</style>
""", unsafe_allow_html=True)

# DB 설정
DB_PATH = "insurance_advisor.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id TEXT PRIMARY KEY, name TEXT, company TEXT, category TEXT,
                  premium_min INTEGER, premium_max INTEGER, coverages TEXT,
                  expense_ratio REAL, surrender_fee_rate REAL, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS encyclopedia
                 (keyword TEXT PRIMARY KEY, summary TEXT, link TEXT, legal_ref TEXT,
                  created_at TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT, timestamp TEXT, session_id TEXT,
                  session_data TEXT, feedback_score INTEGER, feedback_text TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences
                 (user_id TEXT, preference_key TEXT, preference_value TEXT,
                  updated_at TEXT, PRIMARY KEY (user_id, preference_key))''')

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
        now = datetime.now().isoformat()
        c.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)",
                      [(p + (now,)) for p in demo_products])

        encyclopedia_data = [
            ("고지의무", "계약 체결 시 중요한 사실을 보험회사에 알려야 할 의무. 위반 시 계약 해지 가능.", "상법 제651조", "상법 제651조"),
            ("해약환급금", "보험 계약을 중간에 해지할 때 돌려받는 금액. 납입 초기에는 손실이 큼.", "보험업법 제94조", "보험업법 제94조"),
            ("면책기간", "보험 가입 후 일정 기간 동안 보장이 제한되는 기간. 보통 1년.", "표준약관 제12조", "표준약관 제12조"),
            ("사업비율", "보험료가 보장과 사업비로 나뉘는 비율. 낮을수록 유리.", "금융위 고시", "금융위 고시"),
        ]
        c.executemany("INSERT OR IGNORE INTO encyclopedia VALUES (?,?,?,?,?,?)",
                      [(k, s, l, r, now, now) for k, s, l, r in encyclopedia_data])

    conn.commit()
    conn.close()

def search_products(category, max_premium, coverages=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = "SELECT * FROM products WHERE premium_min <= ?"
    params = [max_premium]
    if category:
        query += " AND category = ?"
        params.append(category)
    if coverages:
        for cov in coverages:
            query += " AND coverages LIKE ?"
            params.append(f"%{cov}%")
    c.execute(query, params)
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results

def calculate_surrender(product_id, paid_months, monthly_premium):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, expense_ratio, surrender_fee_rate FROM products WHERE id=?", (product_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"error": "상품을 찾을 수 없습니다."}
    name, expense_ratio, surrender_fee = row
    total_paid = monthly_premium * paid_months
    business_cost = total_paid * expense_ratio
    risk_premium = total_paid * 0.002 * paid_months / 12
    surrender_value = (total_paid - business_cost - risk_premium) * (1 - surrender_fee)
    loss = total_paid - surrender_value
    return {
        "name": name,
        "total_paid": total_paid,
        "business_cost": int(business_cost),
        "risk_premium": int(risk_premium),
        "surrender_value": int(surrender_value),
        "loss": int(loss),
        "refund_rate": surrender_value / total_paid * 100 if total_paid > 0 else 0
    }

def calculate_future(monthly_premium, years):
    total = 0
    current = monthly_premium * 12
    breakdown = []
    for y in range(1, years + 1):
        total += current
        breakdown.append({"year": y, "yearly": current, "cumulative": total})
        current *= 1.03
    return {"total": total, "breakdown": breakdown}

def validate_portfolio(products):
    issues = []
    all_cov = []
    for p in products:
        for c in p.get("coverages", "").split(","):
            if c in all_cov:
                issues.append(f"중복 보장: {c} ({p['name']})")
            else:
                all_cov.append(c)
    total = sum(p.get("premium_min", 0) for p in products)
    if total > 500000:
        issues.append(f"월 총 보험료 {total:,}원 과도")
    issues.append("고지의무 위반 시 계약 해지 가능 (상법 제651조)")
    return {"valid": len(issues) == 0, "issues": issues}

def search_encyclopedia(keyword):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT summary, link, legal_ref FROM encyclopedia WHERE keyword=?", (keyword,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"summary": row[0], "link": row[1], "legal_ref": row[2]}
    return {"summary": "정보 없음", "link": "", "legal_ref": ""}

def parse_input(text):
    t = text.lower()
    if any(k in t for k in ["도움", "help"]):
        return {"action": "help"}
    if any(k in t for k in ["종료", "exit"]):
        return {"action": "exit"}
    if any(k in t for k in ["백과", "용어", "의미", "무엇", "정의", "뭐야", "뭐지", "설명"]):
        kw = None
        for k in ["고지의무", "해약환급금", "면책기간", "사업비율"]:
            if k in t:
                kw = k
                break
        return {"action": "encyclopedia", "keyword": kw or t}
    if any(k in t for k in ["미래", "예상", "예측", "누적", "총액", "총합"]):
        if any(k in t for k in ["년", "월", "보험료", "납입", "예상", "예측", "총액"]):
            mp = 50000
            m = re.search(r'(\d+)\s*만?원?', t)
            if m:
                v = int(m.group(1))
                mp = v * 10000 if v < 1000 else v
            y = 10
            ym = re.search(r'(\d+)\s*년', t)
            if ym:
                y = int(ym.group(1))
            return {"action": "future", "monthly_premium": mp, "years": y}
    if any(k in t for k in ["해약", "환급", "중도해지", "손실"]):
        pid = None
        if "kb" in t: pid = "KB_CHILD_001"
        elif "삼성" in t: pid = "SAMSUNG_CHILD_002"
        elif "db" in t: pid = "DB_BUSINESS_001"
        elif "교보" in t: pid = "VUL_CORP_001"
        elif "현대" in t: pid = "HYUNDAI_SENIOR_001"
        elif "하나" in t: pid = "HANA_CHILD_003"
        elif "nh" in t or "농협" in t: pid = "NH_BUSINESS_002"
        pm = 36
        mm = re.search(r'(\d+)\s*개월', t)
        if mm: pm = int(mm.group(1))
        mp = 50000
        m = re.search(r'(\d+)\s*만?원?', t)
        if m:
            v = int(m.group(1))
            mp = v * 10000 if v < 1000 else v
        return {"action": "surrender", "product_id": pid, "paid_months": pm, "monthly_premium": mp}
    if any(k in t for k in ["포트폴리오", "검증", "점검", "중복"]):
        return {"action": "portfolio"}
    if any(k in t for k in ["추천", "검색", "찾아", "알려", "비교", "상품"]):
        cat = "어린이"
        if any(k in t for k in ["어린이", "유아", "자녀", "아이", "학부모"]): cat = "어린이"
        elif any(k in t for k in ["사업자", "카페", "영업", "개인사업"]): cat = "개인사업자"
        elif any(k in t for k in ["법인", "회사", "기업"]): cat = "법인"
        elif any(k in t for k in ["시니어", "노인", "부모", "어르신"]): cat = "시니어"
        mp = 100000
        m = re.search(r'(\d+)\s*만?원?', t)
        if m:
            v = int(m.group(1))
            mp = v * 10000 if v < 1000 else v
        cov = []
        if "상해" in t: cov.append("상해")
        if "암" in t: cov.append("암")
        if "질병" in t: cov.append("질병")
        if "입원" in t: cov.append("입원")
        if "사망" in t: cov.append("사망")
        return {"action": "search", "category": cat, "max_premium": mp, "coverages": cov}
    return {"action": "unknown", "text": text}

# 세션 초기화
if 'initialized' not in st.session_state:
    init_db()
    st.session_state.initialized = True
    st.session_state.history = []

# 헤더
st.markdown('<div class="main-header">🛡️ Insurance Advisor Ultimate</div>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;color:#8b949e;">완전 자동화 보험 컨설팅 에이전트</p>', unsafe_allow_html=True)

# 사이드바
with st.sidebar:
    st.markdown("### 📋 메뉴")
    page = st.selectbox("기능 선택", [
        "💬 자연어 상담",
        "🔍 상품 검색",
        "💰 해약환급금 계산",
        "📊 포트폴리오 검증",
        "📈 미래 보험료 예측",
        "📖 보험 백과사전"
    ])

    st.markdown("---")
    st.markdown("### 💡 사용 예시")
    st.markdown("""
    - 어린이 보험 추천해줘 (월 10만원)
    - KB 보험 해약하면 얼마?
    - 포트폴리오 검증해줘
    - 10년 후 보험료 총액?
    - 고지의무가 뭐야?
    """)

# 메인 컨텐츠
if page == "💬 자연어 상담":
    st.markdown("### 💬 자연어로 보험 상담하세요")
    user_input = st.text_input("질문을 입력하세요", placeholder="예: 어린이 보험 추천해줘 (월 10만원 이하)", key="chat_input")

    if user_input:
        parsed = parse_input(user_input)
        action = parsed.get("action")

        if action == "search":
            results = search_products(parsed["category"], parsed["max_premium"], parsed.get("coverages"))
            if results:
                st.success(f"총 {len(results)}개 상품을 찾았습니다.")
                df = []
                for r in results:
                    df.append({
                        "상품명": r["name"],
                        "회사": r["company"],
                        "월 보험료": f"{r['premium_min']:,} ~ {r['premium_max']:,}원",
                        "보장내용": r["coverages"],
                        "사업비율": f"{r['expense_ratio']*100:.0f}%"
                    })
                st.dataframe(df, use_container_width=True, hide_index=True)

                # 차트
                chart_data = [{"name": r["name"][:10], "value": r["premium_min"]} for r in results]
                st.bar_chart(
                    {r["name"][:10]: r["premium_min"] for r in results},
                    horizontal=True
                )
            else:
                st.warning("검색 결과가 없습니다.")

        elif action == "surrender":
            if not parsed.get("product_id"):
                st.warning("상품을 지정해주세요. (예: 'KB 보험 해약하면 얼마?')")
            else:
                r = calculate_surrender(parsed["product_id"], parsed["paid_months"], parsed["monthly_premium"])
                if "error" in r:
                    st.error(r["error"])
                else:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("납입총액", f"{r['total_paid']:,}원")
                    with col2:
                        st.metric("해약환급금", f"{r['surrender_value']:,}원")
                    with col3:
                        st.metric("손실액", f"{r['loss']:,}원", delta=f"-{r['loss']:,}원", delta_color="inverse")
                    with col4:
                        st.metric("환급률", f"{r['refund_rate']:.1f}%")

                    if r["refund_rate"] < 50:
                        st.warning("⚠️ 납입 초기에는 해약 시 손실이 큽니다. 계속 유지하는 것이 유리할 수 있습니다.")

        elif action == "portfolio":
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM products")
            products = [dict(row) for row in c.fetchall()]
            conn.close()
            v = validate_portfolio(products[:5])
            if v["valid"]:
                st.success("✓ 모든 검증을 통과했습니다.")
            else:
                st.warning("다음 이슈가 발견되었습니다:")
                for issue in v["issues"]:
                    st.warning(f"- {issue}")

        elif action == "future":
            r = calculate_future(parsed["monthly_premium"], parsed["years"])
            st.info(f"총 납입 예상액: {r['total']:,.0f}원 (연 3% 증가율 적용)")
            df = []
            for y in r["breakdown"]:
                df.append({
                    "연도": y["year"],
                    "연간보험료": f"{y['yearly']:,.0f}원",
                    "누적": f"{y['cumulative']:,.0f}원"
                })
            st.dataframe(df, use_container_width=True, hide_index=True)

            # 차트
            st.bar_chart(
                {y["year"]: y["cumulative"] for y in r["breakdown"]}
            )

        elif action == "encyclopedia":
            kw = parsed.get("keyword", "")
            r = search_encyclopedia(kw)
            st.info(f"**{kw}**\n\n{r['summary']}")
            if r["legal_ref"]:
                st.caption(f"법률 근거: {r['legal_ref']}")

        elif action == "help":
            st.info("""
            ### 도움말
            자연어로 보험 관련 질문을 하세요.

            **예시:**
            - 어린이 보험 추천해줘 (월 10만원 이하)
            - KB 보험 해약하면 얼마 받아? (36개월, 월 5만원)
            - 포트폴리오 검증해줘
            - 10년 후 보험료 총액이 얼마야?
            - 고지의무가 뭐야?
            """)

        else:
            st.warning("""
            입력을 이해하지 못했습니다. 다음 예시를 참고하세요:
            - 어린이 보험 추천해줘 (월 10만원 이하)
            - KB 보험 해약하면 얼마 받아?
            - 포트폴리오 검증해줘
            - 10년 후 보험료 총액이 얼마야?
            - 고지의무가 뭐야?
            """)

elif page == "🔍 상품 검색":
    st.markdown("### 🔍 보험 상품 검색")
    col1, col2, col3 = st.columns(3)
    with col1:
        category = st.selectbox("카테고리", ["전체", "어린이", "개인사업자", "법인", "시니어", "일반"])
    with col2:
        max_premium = st.number_input("최대 월 보험료 (원)", min_value=10000, max_value=10000000, value=100000, step=10000)
    with col3:
        coverages = st.multiselect("보장 내용", ["상해", "질병", "암", "입원", "사망"])

    if st.button("검색", type="primary"):
        cat = None if category == "전체" else category
        cov = coverages if coverages else None
        results = search_products(cat, max_premium, cov)
        if results:
            st.success(f"총 {len(results)}개 상품을 찾았습니다.")
            df = []
            for r in results:
                df.append({
                    "상품명": r["name"],
                    "회사": r["company"],
                    "카테고리": r["category"],
                    "월 보험료": f"{r['premium_min']:,} ~ {r['premium_max']:,}원",
                    "보장내용": r["coverages"],
                    "사업비율": f"{r['expense_ratio']*100:.0f}%",
                    "해약공제율": f"{r['surrender_fee_rate']*100:.0f}%"
                })
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("검색 결과가 없습니다.")

elif page == "💰 해약환급금 계산":
    st.markdown("### 💰 해약환급금 계산")
    col1, col2, col3 = st.columns(3)
    with col1:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, name FROM products")
        products = {row["name"]: row["id"] for row in c.fetchall()}
        conn.close()
        product_name = st.selectbox("상품 선택", list(products.keys()))
    with col2:
        paid_months = st.number_input("납입 월수", min_value=1, max_value=360, value=36)
    with col3:
        monthly_premium = st.number_input("월 보험료 (원)", min_value=10000, max_value=10000000, value=50000, step=10000)

    if st.button("계산하기", type="primary"):
        r = calculate_surrender(products[product_name], paid_months, monthly_premium)
        if "error" in r:
            st.error(r["error"])
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("상품명", r["name"])
            with col2:
                st.metric("납입총액", f"{r['total_paid']:,}원")
            with col3:
                st.metric("해약환급금", f"{r['surrender_value']:,}원")
            with col4:
                st.metric("손실액", f"{r['loss']:,}원", delta=f"-{r['loss']:,}원", delta_color="inverse")

            st.info(f"환급률: {r['refund_rate']:.1f}%")
            if r["refund_rate"] < 50:
                st.warning("⚠️ 납입 초기에는 해약 시 손실이 큽니다.")

elif page == "📊 포트폴리오 검증":
    st.markdown("### 📊 포트폴리오 검증")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    all_products = [dict(row) for row in c.fetchall()]
    conn.close()

    selected = st.multiselect("검증할 상품 선택", [p["name"] for p in all_products])
    if st.button("검증하기", type="primary"):
        selected_products = [p for p in all_products if p["name"] in selected]
        if selected_products:
            v = validate_portfolio(selected_products)
            if v["valid"]:
                st.success("✓ 모든 검증을 통과했습니다.")
            else:
                st.warning("다음 이슈가 발견되었습니다:")
                for issue in v["issues"]:
                    st.warning(f"- {issue}")
        else:
            st.warning("상품을 선택해주세요.")

elif page == "📈 미래 보험료 예측":
    st.markdown("### 📈 미래 보험료 예측")
    col1, col2 = st.columns(2)
    with col1:
        monthly_premium = st.number_input("월 보험료 (원)", min_value=10000, max_value=10000000, value=50000, step=10000)
    with col2:
        years = st.slider("예측 기간 (년)", min_value=1, max_value=30, value=10)

    if st.button("예측하기", type="primary"):
        r = calculate_future(monthly_premium, years)
        st.info(f"총 납입 예상액: {r['total']:,.0f}원 (연 3% 증가율 적용)")

        df = []
        for y in r["breakdown"]:
            df.append({
                "연도": y["year"],
                "연간보험료": y["yearly"],
                "누적": y["cumulative"]
            })
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.bar_chart(
            {y["year"]: y["cumulative"] for y in r["breakdown"]}
        )

elif page == "📖 보험 백과사전":
    st.markdown("### 📖 보험 백과사전")
    keyword = st.text_input("검색할 용어", placeholder="예: 고지의무, 해약환급금, 면책기간, 사업비율")
    if st.button("검색", type="primary") and keyword:
        r = search_encyclopedia(keyword)
        if r["summary"] != "정보 없음":
            st.info(f"**{keyword}**\n\n{r['summary']}")
            if r["legal_ref"]:
                st.caption(f"법률 근거: {r['legal_ref']}")
        else:
            st.warning(f"'{keyword}'에 대한 정보가 없습니다.")

# 푸터
st.markdown("---")
st.markdown('<p style="text-align:center;color:#8b949e;font-size:0.8rem;">Insurance Advisor Ultimate © 2026 | 데이터는 참고용이며 실제 보험 상품과 다를 수 있습니다.</p>', unsafe_allow_html=True)
