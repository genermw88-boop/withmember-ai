import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
from openai import OpenAI  # 최신 버전에 맞게 불러오기 방식 변경

# --- 1. 환경 설정 및 API 키 불러오기 ---
N_CUSTOMER_ID = st.secrets.get("NAVER_CUSTOMER_ID", "4320532")
N_API_KEY = st.secrets.get("NAVER_API_KEY", "")
N_SECRET_KEY = st.secrets.get("NAVER_SECRET_KEY", "")
O_API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- 2. 네이버 API 인증 함수 ---
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# --- 3. 네이버 황금키워드 추출 함수 (에러 메시지 강화) ---
def get_naver_golden_keywords(hint_keyword, c_id, a_key, s_key):
    uri = '/keywordstool'
    method = 'GET'
    timestamp = str(round(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri, s_key)
    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': a_key,
        'X-Customer': str(c_id),
        'X-Signature': signature
    }
    params = {'hintKeywords': hint_keyword, 'showDetail': '1'}
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        
        # 1. API 호출 성공 시
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            if not data:
                return [], "해당 키워드는 네이버 검색량 데이터가 너무 적어 추출할 수 없습니다. '강남역 고기집'처럼 조금 더 큰 단위로 검색해보세요."
            
            for item in data:
                pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                item['total'] = pc + mo
                
            sorted_data = sorted(data, key=lambda x: x['total'], reverse=True)
            golden = [sorted_data[0]['relKeyword']]
            niche = [i['relKeyword'] for i in sorted_data if 500 < i['total'] < 2500]
            golden.extend(niche[:4] if len(niche) >= 4 else [i['relKeyword'] for i in sorted_data[1:5]])
            return golden[:5], "success"
            
        # 2. 인증 오류 등 실패 시 (정확한 원인 반환)
        else:
            return [], f"네이버 API 에러 발생 (코드: {res.status_code}) - API 키가 정확한지 확인해주세요."
            
    except Exception as e:
        return [], f"시스템 통신 에러: {str(e)}"

# --- 4. OpenAI 텍스트 생성 함수 (최신 v1.0.0+ 문법 적용) ---
def generate_ai_content(prompt, api_key):
    try:
        client = OpenAI(api_key=api_key) # 최신 문법으로 변경됨
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 플레이스 마케팅 및 고객관리 전문가야."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 5. Streamlit UI 구성 ---
st.set_page_config(page_title="위드멤버 통합 관리 시스템", page_icon="🚀", layout="wide")

with st.sidebar:
    st.title("🔑 API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        st.warning("Secrets를 설정하거나 아래에 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드 ✅")

tab1, tab2 = st.tabs(["🎯 황금키워드 & 소개글", "💬 방문자 리뷰 답글"])

# --- Tab 1: 황금키워드 & 소개글 ---
with tab1:
    st.header("플레이스 최적화 소개글 생성")
    with st.form("intro_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: store = st.text_input("매장명", placeholder="정가네")
        with c2: reg = st.text_input("지역", placeholder="야탑동")
        with c3: cat = st.text_input("업종", placeholder="한식")
        with c4: men = st.text_input("주력메뉴", placeholder="삼겹살")
        
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store:
            st.error("매장명을 입력해주세요!")
        else:
            with st.spinner("데이터 분석 중..."):
                # 변경점: 키워드 결과와 에러 메시지를 동시에 받아옵니다.
                kws, msg = get_naver_golden_keywords(f"{reg} {cat}", N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if kws:
                    st.success(f"🎯 이번 달 황금키워드: {', '.join(kws)}")
                    prompt = f"매장명:'{store}', 지역:'{reg}', 업종:'{cat}', 메뉴:'{men}', 황금키워드:'{','.join(kws)}'를 모두 포함해서 네이버 플레이스 소개글(새소식)을 50자 내외로 써줘. 첫 문장에 매장명과 1위 키워드를 자연스럽게 배치해."
                    intro_res = generate_ai_content(prompt, O_API_KEY)
                    st.info(intro_res)
                    st.code(intro_res)
                else: 
                    # 키워드를 못 가져왔을 때 정확한 이유를 빨간색으로 띄워줍니다.
                    st.error(msg)

# --- Tab 2: 방문자 리뷰 답글 (요청하신 대로 매장명 입력 삭제) ---
with tab2:
    st.header("방문자 리뷰 답글 생성기")
    with st.form("review_form"):
        # 매장명 입력란 삭제됨
        review_content = st.text_area("손님이 남긴 리뷰 내용을 입력하세요", placeholder="맛있어요")
        submit_review = st.form_submit_button("답글 생성")
    
    if submit_review:
        if not review_content:
            st.warning("리뷰 내용을 입력해주세요!")
        else:
            with st.spinner("정성스러운 답글을 작성 중..."):
                prompt = f"다음 리뷰에 대해 친절하고 정중한 사장님 톤으로 답글을 써줘. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
