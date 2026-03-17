import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
import openai

# 1. 네이버 API 인증 서명 생성 함수
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# 2. 네이버 API 기반 황금키워드 추출 함수
def get_naver_golden_keywords(hint_keyword, customer_id, api_key, secret_key):
    uri = '/keywordstool'
    method = 'GET'
    timestamp = str(round(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri, secret_key)

    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': api_key,
        'X-Customer': str(customer_id),
        'X-Signature': signature
    }
    
    # 힌트 키워드로 검색량 조회
    params = {'hintKeywords': hint_keyword, 'showDetail': '1'}
    url = f'https://api.naver.com{uri}'
    
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json().get('keywordList', [])
            if not data: return []

            # 데이터 정제: 검색량 합계 계산 (문자열 '< 10' 처리)
            for item in data:
                pc = item['monthlyPcQcCnt']
                mo = item['monthlyMobileQcCnt']
                pc = 10 if isinstance(pc, str) else pc
                mo = 10 if isinstance(mo, str) else mo
                item['total_sum'] = pc + mo

            # 1. 가장 센 키워드 (검색량 1위)
            sorted_data = sorted(data, key=lambda x: x['total_sum'], reverse=True)
            golden_list = [sorted_data[0]['relKeyword']]

            # 2. 틈새 키워드 4개 (검색량 500~2000 사이 중 무작위 4개 추출)
            niche = [item['relKeyword'] for item in sorted_data if 500 < item['total_sum'] < 2500]
            golden_list.extend(niche[:4] if len(niche) >= 4 else [item['relKeyword'] for item in sorted_data[1:5]])
            
            return golden_list[:5]
        else:
            st.error(f"네이버 API 연결 실패: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"오류 발생: {str(e)}")
        return []

# 3. OpenAI 기반 최적화 소개글 생성 함수
def generate_intro_with_ai(region, category, menu, keywords, openai_key):
    openai.api_key = openai_key
    kw_str = ", ".join(keywords)
    
    prompt = f"""
    너는 네이버 플레이스 상위노출 전문가야. 아래 정보를 바탕으로 '상세 설명(소개글)'을 작성해라.
    
    [입력 정보]
    - 위치: {region}
    - 업종: {category}
    - 메뉴: {menu}
    - 필수 황금키워드: {kw_str}
    
    [작성 규칙]
    1. 반드시 5개의 황금키워드를 문장 속에 자연스럽게 모두 녹여낼 것.
    2. 길이는 공백 포함 50자 내외로 아주 짧고 강렬하게 쓸 것.
    3. 첫 문장에 검색량이 가장 높은 키워드를 배치할 것.
    4. 친절하고 신뢰감 있는 말투를 사용하고 마지막엔 방문 유도 멘트를 넣을 것.
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI 생성 실패: {str(e)}"

# --- Streamlit UI 시작 ---
st.set_page_config(page_title="WithMember AI", page_icon="📈")
st.title("🚀 위드멤버 플레이스 자동화 시스템")
st.subheader("데이터 기반 황금키워드 추출 및 소개글 최적화")

# 사이드바: 아까 발급받은 키 입력창
with st.sidebar:
    st.header("🔑 API 설정 (네이버/OpenAI)")
    c_id = st.text_input("Naver CUSTOMER_ID", value="4320532") # 대표님 ID 기본값 세팅
    a_key = st.text_input("Naver API_KEY", type="password")
    s_key = st.text_input("Naver SECRET_KEY", type="password")
    o_key = st.text_input("OpenAI API KEY", type="password")
    st.info("한 번 입력하면 세션 동안 유지됩니다.")

# 메인 입력 폼
with st.form("main_form"):
    col1, col2, col3 = st.columns(3)
    with col1: reg = st.text_input("지역", placeholder="예: 강남역")
    with col2: cat = st.text_input("업종", placeholder="예: 고기집")
    with col3: men = st.text_input("주력메뉴", placeholder="예: 숙성 삼겹살")
    
    btn = st.form_submit_button("🔥 황금키워드 추출 및 최적화 실행")

if btn:
    if not (a_key and s_key and o_key):
        st.error("사이드바에 모든 API 키를 입력해 주세요!")
    else:
        with st.spinner("네이버 광고 데이터를 분석 중입니다..."):
            # 1. 키워드 추출
            hint = f"{reg} {cat}"
            final_keywords = get_naver_golden_keywords(hint, c_id, a_key, s_key)
            
            if final_keywords:
                st.success(f"✅ 추출된 황금키워드: {', '.join(final_keywords)}")
                
                # 2. 소개글 생성
                intro = generate_intro_with_ai(reg, cat, men, final_keywords, o_key)
                
                st.divider()
                st.subheader("📝 최적화 소개글 (월 1회 업데이트용)")
                st.info(intro)
                st.code(intro, language="text") # 복사하기 편하게 코드블록 제공
                st.write(f"글자 수: {len(intro)}자")
            else:
                st.warning("데이터를 가져오지 못했습니다. 지역/업종명을 확인해 주세요.")
