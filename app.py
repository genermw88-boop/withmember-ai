import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
from openai import OpenAI

# --- 1. 환경 설정 및 API 키 불러오기 ---
try:
    N_CUSTOMER_ID = st.secrets.get("NAVER_CUSTOMER_ID", "4320532")
    N_API_KEY = st.secrets.get("NAVER_API_KEY", "")
    N_SECRET_KEY = st.secrets.get("NAVER_SECRET_KEY", "")
    O_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
except:
    st.error("Streamlit Cloud의 Secrets 설정이 필요합니다.")
    st.stop()

# --- 2. 네이버 API 인증 함수 ---
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# --- 3. AI 기반 다이나믹 힌트 추출 ---
def get_ai_dynamic_hints(store, reg, men, api_key):
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"매장명:{store}, 지역:{reg}, 메뉴:{men}. 네이버 광고 검색용 키워드 10개를 콤마로만 연결해서 알려줘."
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content.strip().replace(" ", "")
    except:
        return f"{reg}맛집,{reg}{men}"

# --- 4. 키워드 추출 핵심 로직 (100~1500건 우선) ---
def get_naver_golden_keywords(reg, ai_hints, c_id, a_key, s_key):
    uri = '/keywordstool'
    method = 'GET'
    timestamp = str(round(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri, s_key)
    headers = {'Content-Type': 'application/json; charset=UTF-8', 'X-Timestamp': timestamp, 'X-API-KEY': a_key, 'X-Customer': str(c_id), 'X-Signature': signature}
    params = {'hintKeywords': ai_hints, 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"API 오류({res.status_code})"
        
        data = res.json().get('keywordList', [])
        all_kws = []
        for item in data:
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            item['total_search'] = pc + mo
            all_kws.append(item)
            
        # 100~1500건 사이 우선 필터링
        filtered = [i for i in all_kws if 100 <= i['total_search'] <= 1500]
        if len(filtered) < 10:
            filtered = sorted(all_kws, key=lambda x: x['total_search'], reverse=True)[:15]
            
        gold = filtered[:5]
        detail = filtered[5:10]
        
        # 데이터가 없을 때 방어
        if not gold: gold = [{"relKeyword": f"{reg}맛집", "total_search": 0}]
        if not detail: detail = [{"relKeyword": f"{reg}추천", "total_search": 0}]
            
        return gold, detail, "success"
    except Exception as e:
        return [], [], str(e)

# --- 5. UI 구성 ---
st.set_page_config(page_title="위드멤버 통합툴", layout="wide")
st.header("📈 위드멤버 플레이스 최적화")

tab1, tab2 = st.tabs(["🎯 키워드 & 소개글", "💬 리뷰 답글"])

with tab1:
    with st.form("main_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: st_name = st.text_input("매장명", "정혜순조림")
        with c2: st_reg = st.text_input("지역", "광주 서구 쌍촌동")
        with c3: st_men = st.text_input("메뉴", "고등어조림")
        with c4: st_event = st.text_input("이벤트", "음료 서비스")
        btn = st.form_submit_button("분석 시작")
        
    if btn:
        with st.spinner("네이버 상권 데이터를 정밀 분석 중입니다..."):
            hints = get_ai_dynamic_hints(st_name, st_reg, st_men, O_API_KEY)
            gold, detail, msg = get_naver_golden_keywords(st_reg, hints, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
            
            if msg == "success":
                col1, col2 = st.columns(2)
                with col1:
                    st.success("🎯 지역 메인 키워드 5개")
                    for k in gold:
                        vol = f"{k['total_search']:,}건" if isinstance(k['total_search'], int) else k['total_search']
                        st.write(f"**{k['relKeyword']}**: {vol}")
                with col2:
                    st.info("✨ 상세 타겟 키워드 5개")
                    for k in detail:
                        vol = f"{k['total_search']:,}건" if isinstance(k['total_search'], int) else k['total_search']
                        st.write(f"**{k['relKeyword']}**: {vol}")
                
                # 소개글 생성
                client = OpenAI(api_key=O_API_KEY)
                kw_str = ", ".join([k['relKeyword'] for k in gold + detail])
                prompt = f"매장:{st_name}, 메뉴:{st_men}, 이벤트:{st_event}, 키워드:{kw_str}를 자연스럽게 포함해 180자 내외의 플레이스 소개글을 써줘. 이모티콘 사용."
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
                
                st.divider()
                st.subheader("📝 최적화 소개글")
                st.write(res.choices[0].message.content)
                st.code(res.choices[0].message.content)
            else:
                st.error(f"오류 발생: {msg}")

with tab2:
    st.subheader("💬 리뷰 답글 생성기")
    review_text = st.text_area("리뷰 내용을 입력하세요")
    if st.button("답글 생성"):
        client = OpenAI(api_key=O_API_KEY)
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": f"리뷰 답글 써줘: {review_text}"}])
        st.success(res.choices[0].message.content)
