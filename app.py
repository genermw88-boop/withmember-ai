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

# --- 3. [완벽 개선] 스마트 단어 추출 로직 ---
def get_naver_golden_keywords(reg, men, c_id, a_key, s_key):
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
    
    # [핵심 1] 띄어쓰기 기준으로 가장 마지막 단어만 지역명으로 추출 (예: "광주 동구 동명동" -> "동명동")
    reg_parts = reg.strip().split()
    core_reg = reg_parts[-1] if reg_parts else reg.strip()
    
    # 필터링을 위한 짧은 지역명 (예: "동명동" -> "동명", "야탑동" -> "야탑")
    # 단, "장동"처럼 2글자인 경우는 그대로 유지
    short_reg = core_reg[:-1] if len(core_reg) >= 3 and core_reg[-1] in ['동', '역', '구', '시'] else core_reg

    # [핵심 2] 메뉴에 콤마가 있으면 무조건 첫 번째 단어만 사용 (예: "카츠, 사시미" -> "카츠")
    core_men = men.replace(",", " ").split()[0] if men else ""
    
    # 네이버에 던질 5가지 힌트 (이제 콤마 오류나 정체불명 지역명 오류가 없습니다)
    hints = f"{core_reg}맛집,{core_reg}{core_men},{short_reg}회식,{short_reg}모임,{short_reg}데이트"
    params = {'hintKeywords': hints, 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            if not data: return [], f"'{core_reg}' 주변의 키워드 검색량이 부족합니다. 지역명을 조금 다르게 적어주세요."
            
            filtered_data = []
            for item in data:
                kw = item['relKeyword']
                
                # 타지역 및 불필요한 단어 제거
                if "주변" in kw or "근처" in kw or "오늘" in kw: continue
                # 지역명이 안 들어간 '맛집' 키워드 제거
                if "맛집" in kw and short_reg not in kw: continue
                
                pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                base_search = pc + mo
                
                # 가중치 부여
                weight = 1
                if short_reg in kw: weight = 100
                if core_men and core_men in kw: weight *= 5
                if "회식" in kw or "모임" in kw or "룸" in kw or "데이트" in kw: weight *= 3
                
                item['total_search'] = base_search
                item['sort_score'] = base_search * weight
                item['comp_level'] = item.get('compIdx', '중간')
                
                filtered_data.append(item)
                
            sorted_data = sorted(filtered_data, key=lambda x: x['sort_score'], reverse=True)
            
            final_kws = []
            if sorted_data:
                final_kws.append(sorted_data[0]) 
                niche_candidates = [i for i in sorted_data[1:] if 100 <= i['total_search'] <= 8000]
                for kw in niche_candidates:
                    if kw not in final_kws: final_kws.append(kw)
                    if len(final_kws) == 5: break
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
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 상위 1% 플레이스 마케팅 전문 카피라이터입니다. 방문자의 마음을 사로잡는 세련되고 감성적인 문구를 작성합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85
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
        # UI 입력 제한 해제 (스마트 추출 로직이 알아서 걸러줍니다)
        c1, c2, c3, c4 = st.columns(4)
        with c1: 
            store = st.text_input("매장명", placeholder="육산도 동명")
        with c2: 
            reg = st.text_input("지역 (예: 광주 동명동)", placeholder="광주 동구 동명동")
        with c3: 
            men = st.text_input("주력메뉴", placeholder="카츠, 사시미")
        with c4: 
            event = st.text_input("이벤트 (선택)", placeholder="소주 1병 무료")
            
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 주력메뉴는 필수 입력입니다!")
        else:
            with st.spinner("해당 지역 상권 데이터를 분석 중입니다..."):
                kws_data, msg = get_naver_golden_keywords(reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if kws_data and len(kws_data) > 0:
                    st.subheader("🎯 이번 달 황금키워드 5개 조합")
                    st.markdown(f"**🥇 1위 메인 키워드:** `{kws_data[0]['relKeyword']}` (검색량: **{kws_data[0]['total_search']:,}**건)")
                    niche_str = ""
                    for kw in kws_data[1:]:
                        niche_str += f"- `{kw['relKeyword']}` (검색량: {kw['total_search']:,}건)\n"
                    st.markdown(f"**💡 틈새/TPO 키워드 4개:**\n{niche_str}")
                    st.divider()
                    
                    kw_names = [k['relKeyword'] for k in kws_data]
                    
                    event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                    event_rule = "제공된 이벤트를 고객이 방문하고 싶게끔 매력적이고 자연스럽게 문장에 포함하세요." if event else "이벤트가 없으므로 메뉴와 매장의 매력(맛, 분위기 등)을 강조하는 데 집중하세요."

                    prompt = f"""
                    매장명: '{store}'
                    주력메뉴: '{men}'
                    {event_instruction}
                    선정된 타겟 키워드 5개: {', '.join(kw_names)}

                    [작성 규칙 - 반드시 지킬 것]
                    1. 키워드를 절대 단순 나열하지 마세요. (예: "A와 B가 있는 C입니다" 금지)
                    2. 마치 실제 방문해 본 단골손님이나 센스 있는 사장님이 소개하듯, 물 흐르듯 자연스러운 문맥 안에 5개 키워드를 숨겨두세요.
                    3. {event_rule}
                    4. 글자 수는 공백 포함 **100자 ~ 150자 사이**로, 고객이 읽기 편한 2~3문장으로 구성하세요.
                    5. '육즙', '분위기', '가성비', '친절함' 등 방문 욕구를 자극하는 표현을 섞어주세요.
                    6. 과하지 않은 세련된 이모티콘 2~3개를 적재적소에 배치하세요.
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
