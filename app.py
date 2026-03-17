import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
import openai

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

# --- 3. 네이버 황금키워드 추출 함수 ---
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
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            for item in data:
                pc = 10 if isinstance(item['monthlyPcQcCnt'], str) else item['monthlyPcQcCnt']
                mo = 10 if isinstance(item['monthlyMobileQcCnt'], str) else item['monthlyMobileQcCnt']
                item['total'] = pc + mo
            sorted_data = sorted(data, key=lambda x: x['total'], reverse=True)
            golden = [sorted_data[0]['relKeyword']]
            niche = [i['relKeyword'] for i in sorted_data if 500 < i['total'] < 2500]
            golden.extend(niche[:4] if len(niche) >= 4 else [i['relKeyword'] for i in sorted_data[1:5]])
            return golden[:5]
    except: return []
    return []

# --- 4. OpenAI 텍스트 생성 함수 ---
def generate_ai_content(prompt, api_key):
    openai.api_key = api_key
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "너는 플레이스 마케팅 및 고객관리 전문가야."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 5. Streamlit UI 구성 ---
st.set_page_config(page_title="위드멤버 통합 관리 시스템", page_icon="🚀", layout="wide")

# 사이드바 설정
with st.sidebar:
    st.title("🔑 API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        st.warning("Secrets를 설정하거나 아래에 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드 ✅")

# 메인 탭 구성
tab1, tab2 = st.tabs(["🎯 황금키워드 & 소개글", "💬 방문자 리뷰 답글"])

# --- Tab 1: 황금키워드 & 소개글 ---
with tab1:
    st.header("플레이스 최적화 소개글 생성")
    with st.form("intro_form"):
        # 입력칸을 4개로 늘렸습니다.
        c1, c2, c3, c4 = st.columns(4)
        with c1: store = st.text_input("매장명", placeholder="위드멤버 고깃집")
        with c2: reg = st.text_input("지역", placeholder="강남역")
        with c3: cat = st.text_input("업종", placeholder="삼겹살집")
        with c4: men = st.text_input("주력메뉴", placeholder="숙성 삼겹살")
        
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store:
            st.error("매장명을 입력해주세요!")
        else:
            with st.spinner("데이터 분석 중..."):
                kws = get_naver_golden_keywords(f"{reg} {cat}", N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                if kws:
                    st.success(f"🎯 이번 달 황금키워드: {', '.join(kws)}")
                    # 프롬프트에 매장명을 추가하여 자연스럽게 녹이도록 지시했습니다.
                    prompt = f"매장명:'{store}', 지역:'{reg}', 업종:'{cat}', 메뉴:'{men}', 황금키워드:'{','.join(kws)}'를 모두 포함해서 네이버 플레이스 소개글(새소식)을 50자 내외로 써줘. 첫 문장에 매장명과 1위 키워드를 자연스럽게 배치해."
                    intro_res = generate_ai_content(prompt, O_API_KEY)
                    st.info(intro_res)
                    st.code(intro_res)
                else: st.error("키워드 데이터를 가져오지 못했습니다.")

# --- Tab 2: 방문자 리뷰 답글 ---
with tab2:
    st.header("방문자 리뷰 답글 생성기")
    with st.form("review_form"):
        # 답글 생성 시에도 매장명을 넣을 수 있도록 추가했습니다.
        review_store = st.text_input("매장명 (답글용)", placeholder="위드멤버 고깃집")
        review_content = st.text_area("손님이 남긴 리뷰 내용을 입력하세요", placeholder="고기가 너무 맛있고 사장님이 친절해요!")
        submit_review = st.form_submit_button("답글 생성")
    
    if submit_review:
        if not review_store:
            st.error("매장명을 입력해주세요!")
        else:
            with st.spinner("정성스러운 답글을 작성 중..."):
                prompt = f"다음 리뷰에 대해 친절하고 정중한 사장님 톤으로 답글을 써줘. 우리 매장 이름은 '{review_store}'야. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
