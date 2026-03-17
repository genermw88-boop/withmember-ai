import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
from openai import OpenAI

# --- 1. 환경 설정 및 API 키 불러오기 ---
N_CUSTOMER_ID = st.secrets.get("NAVER_CUSTOMER_ID", "4320532")
N_API_KEY = st.secrets.get("NAVER_API_KEY", "")
N_SECRET_KEY = st.secrets.get("NAVER_SECRET_KEY", "")
O_API_KEY = st.secrets.get("OPENAI_API_KEY", "")

def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# --- 3. [완벽 개선] 초정밀 지역 타겟팅 키워드 추출 ---
def get_naver_golden_keywords(reg, cat, men, c_id, a_key, s_key):
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
    
    # 1. 핵심 지역명 추출 (예: 야탑동 -> 야탑, 강남역 -> 강남)
    core_reg = reg.replace("동", "").replace("역", "").replace("구", "").replace("시", "")
    if len(core_reg) < 2: core_reg = reg[:2] # 최소 2글자 방어

    # 2. 힌트 키워드를 내 지역 중심으로만 묶음
    hints = f"{core_reg}{cat},{core_reg}{men},{core_reg}맛집"
    params = {'hintKeywords': hints, 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            if not data:
                return [], "키워드 데이터가 부족합니다."
            
            filtered_data = []
            for item in data:
                kw = item['relKeyword']
                
                # [필터 1] 광범위/타지역 쓰레기 키워드 배제
                if "주변" in kw or "근처" in kw or "오늘" in kw or "추천" in kw:
                    continue
                # [필터 2] '맛집'이 들어갔는데 내 지역명(core_reg)이 없으면 타지역이므로 탈락!
                if "맛집" in kw and core_reg not in kw:
                    continue
                
                pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                base_search = pc + mo
                
                # [필터 3] 내 지역명이 포함된 키워드에 압도적 가중치(x1000) 부여
                weight = 1
                if core_reg in kw:
                    weight = 1000
                elif men in kw or cat in kw:
                    weight = 10
                
                item['total_search'] = base_search
                item['sort_score'] = base_search * weight
                item['comp_level'] = item.get('compIdx', '중간')
                
                filtered_data.append(item)
                
            # 가중치(sort_score) 기준으로 정렬
            sorted_data = sorted(filtered_data, key=lambda x: x['sort_score'], reverse=True)
            
            # 최종 5개 세팅 로직
            final_kws = []
            if sorted_data:
                final_kws.append(sorted_data[0]) # 1위 (압도적 지역+검색량)
                
                # 틈새(월간 100~5000건) 우선 추출
                niche_candidates = [i for i in sorted_data[1:] if 100 <= i['total_search'] <= 5000]
                for kw in niche_candidates:
                    if kw not in final_kws: final_kws.append(kw)
                    if len(final_kws) == 5: break
                
                # 모자라면 남은 것 중 순서대로 강제 채움
                for kw in sorted_data[1:]:
                    if len(final_kws) == 5: break
                    if kw not in final_kws: final_kws.append(kw)
                        
            return final_kws, "success"
            
        else:
            return [], f"API 에러 (코드: {res.status_code})"
            
    except Exception as e:
        return [], f"시스템 에러: {str(e)}"

# --- 4. OpenAI 텍스트 생성 함수 ---
def generate_ai_content(prompt, api_key):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 플레이스 마케팅 카피라이터야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 5. Streamlit UI 구성 ---
st.set_page_config(page_title="위드멤버 통합 관리 시스템", page_icon="🚀", layout="wide")

with st.sidebar:
    st.title("🔑 API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        st.warning("Secrets를 설정하거나 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드 ✅")

tab1, tab2 = st.tabs(["🎯 황금키워드 & 소개글", "💬 방문자 리뷰 답글"])

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
        if not store or not reg or not cat:
            st.error("매장명, 지역, 업종은 필수 입력입니다!")
        else:
            with st.spinner("해당 지역 상권 데이터를 분석 중입니다..."):
                kws_data, msg = get_naver_golden_keywords(reg, cat, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if kws_data and len(kws_data) > 0:
                    st.subheader("🎯 이번 달 황금키워드 5개 조합")
                    
                    st.markdown(f"**🥇 1위 메인 키워드:** `{kws_data[0]['relKeyword']}` (검색량: **{kws_data[0]['total_search']:,}**건 / 경쟁도: {kws_data[0]['comp_level']})")
                    
                    niche_str = ""
                    for kw in kws_data[1:]:
                        niche_str += f"- `{kw['relKeyword']}` (검색량: {kw['total_search']:,}건 / 경쟁도: {kw['comp_level']})\n"
                    st.markdown(f"**💡 틈새 키워드 4개:**\n{niche_str}")
                    
                    st.divider()
                    
                    kw_names = [k['relKeyword'] for k in kws_data]
                    
                    prompt = f"""
                    매장명: '{store}'
                    선정된 핵심키워드 5개: {', '.join(kw_names)}

                    [작성 규칙]
                    1. 위 5개 키워드를 빠짐없이 문장에 자연스럽게 녹여내라.
                    2. 반드시 '공백 포함 40자~60자 사이'로 짧고 압축적으로 쓸 것.
                    3. 첫 문장은 '{store}'(매장명)과 1위 키워드('{kw_names[0]}')로 시작할 것.
                    4. 친근한 이모티콘 1~2개 포함.
                    5. 인사말 생략, 딱 본문만 출력.
                    """
                    
                    intro_res = generate_ai_content(prompt, O_API_KEY)
                    st.subheader("📝 최적화 소개글 (복사/붙여넣기용)")
                    st.info(intro_res)
                    st.code(intro_res)
                else: 
                    st.error(msg)

with tab2:
    st.header("방문자 리뷰 답글 생성기")
    with st.form("review_form"):
        review_content = st.text_area("손님이 남긴 리뷰 내용을 입력하세요")
        submit_review = st.form_submit_button("답글 생성")
    
    if submit_review:
        if not review_content:
            st.warning("리뷰 내용을 입력해주세요!")
        else:
            with st.spinner("정성스러운 답글을 작성 중..."):
                prompt = f"다음 손님의 리뷰에 대해 친절하고 감사해하는 사장님 톤으로 답글을 써줘. 친근한 이모티콘(예: 😊, 💖, 👍 등)을 문맥에 맞게 2~3개 듬뿍 써줘. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
