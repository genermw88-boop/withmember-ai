import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
from openai import OpenAI

# --- 1. 환경 설정 ---
N_CUSTOMER_ID = st.secrets.get("NAVER_CUSTOMER_ID", "4320532")
N_API_KEY = st.secrets.get("NAVER_API_KEY", "")
N_SECRET_KEY = st.secrets.get("NAVER_SECRET_KEY", "")
O_API_KEY = st.secrets.get("OPENAI_API_KEY", "")

def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# --- 2. AI 다이나믹 힌트 추출 ---
def get_ai_dynamic_hints(store, reg, men, api_key):
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"매장명:'{store}', 지역:'{reg}', 메뉴:'{men}'. 이 매장의 네이버 검색 광고용 힌트 키워드 10개를 콤마로만 연결해 출력해. 반드시 지역명을 포함할 것."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip().replace(" ", "")
    except:
        return f"{reg}맛집,{reg}{men},{reg}회식"

# --- 3. [개선] 실제 검색량 우선 추출 로직 ---
def get_naver_golden_keywords(reg, ai_hints, c_id, a_key, s_key):
    uri = '/keywordstool'
    method = 'GET'
    timestamp = str(round(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri, s_key)
    headers = {'Content-Type': 'application/json; charset=UTF-8', 'X-Timestamp': timestamp, 'X-API-KEY': a_key, 'X-Customer': str(c_id), 'X-Signature': signature}
    
    params = {'hintKeywords': ai_hints, 'showDetail': 1}
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"API 에러:{res.status_code}"
        
        data = res.json().get('keywordList', [])
        all_results = []
        for item in data:
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total = pc + mo
            item['total_search'] = total
            all_results.append(item)

        # [핵심] 100~1500건 사이의 키워드를 먼저 찾고, 없으면 전체에서 검색량 높은 순으로 가져옵니다.
        target_kws = [i for i in all_results if 100 <= i['total_search'] <= 1500]
        if len(target_kws) < 10:
            target_kws = sorted(all_results, key=lambda x: x['total_search'], reverse=True)[:20]
        
        # 메인 5개 / 상세 5개 분리
        sorted_kws = sorted(target_kws, key=lambda x: x['total_search'], reverse=True)
        gold = sorted_kws[:5]
        detail = sorted_kws[5:10]
        
        return gold, detail, "success"
    except Exception as e:
        return [], [], str(e)

# --- 4. UI 및 실행 ---
st.set_page_config(page_title="위드멤버 AI", layout="wide")
st.header("🚀 위드멤버 플레이스 최적화 시스템")

with st.sidebar:
    st.title("🔑 API 설정")
    if not (N_API_KEY and O_API_KEY): st.error("Secrets 설정을 확인해주세요.")
    else: st.success("연결 완료 ✅")

with st.form("my_form"):
    c1, c2, c3, c4 = st.columns(4)
    with c1: store = st.text_input("매장명", "우연희")
    with c2: reg = st.text_input("지역", "광주 동구 장동")
    with c3: men = st.text_input("주력메뉴", "육사시미")
    with c4: event = st.text_input("이벤트", "소주 1병 무료")
    submit = st.form_submit_button("최적화 실행")

if submit:
    with st.spinner("네이버 실제 검색량을 조회 중..."):
        hints = get_ai_dynamic_hints(store, reg, men, O_API_KEY)
        gold, detail, msg = get_naver_golden_keywords(reg, hints, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
        
        if gold:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🎯 메인 키워드 (실제 검색량)")
                for k in gold: st.write(f"- {k['relKeyword']}: **{k['total_search']:,}건**")
            with col2:
                st.subheader("✨ 상세 키워드 (실제 검색량)")
                for k in detail: st.write(f"- {k['relKeyword']}: **{k['total_search']:,}건**")
            
            # 소개글 생성
            kw_list = [k['relKeyword'] for k in gold + detail]
            client = OpenAI(api_key=O_API_KEY)
            prompt = f"매장명 {store}, 메뉴 {men}, 이벤트 {event}, 키워드 {kw_list}를 넣어 플레이스 소개글을 150자 내외로 자연스럽게 써줘."
            res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
            
            st.divider()
            st.subheader("📝 최적화 소개글")
            st.info(res.choices[0].message.content)
            st.code(res.choices[0].message.content)
        else:
            st.error(f"데이터 추출 실패: {msg}")
