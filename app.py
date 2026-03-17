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

# --- 3. [오류 완벽 해결] 정직한 지역명 추출 로직 ---
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
    
    # 1. 띄어쓰기 기준으로 구와 동을 찾습니다. (자르지 않고 원형 보존!)
    reg_parts = reg.strip().split()
    core_gu = ""
    core_dong = ""
    for p in reg_parts:
        if p.endswith('구'): core_gu = p        # 예: 동구 (그대로 유지)
        elif p.endswith('동') or p.endswith('역'): core_dong = p # 예: 장동 (그대로 유지)
        
    if not core_gu and not core_dong and reg_parts:
        core_dong = reg_parts[-1] # 구/동이 없으면 마지막 단어 통째로 사용

    # 2. 메뉴 정제 (콤마 앞 단어만 힌트로 사용)
    core_men = men.replace(",", " ").split()[0] if men else ""
    
    # 3. 구와 동을 원형 그대로 네이버에 힌트 투척!
    hints_list = []
    if core_gu: hints_list.extend([f"{core_gu}맛집", f"{core_gu}{core_men}"])
    if core_dong: hints_list.extend([f"{core_dong}맛집", f"{core_dong}{core_men}", f"{core_dong}회식"])
    if not hints_list: hints_list = [f"{reg.replace(' ', '')}맛집"]
    
    safe_hints = ",".join(hints_list[:5])
    params = {'hintKeywords': safe_hints, 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            if not data: return [], [], f"'{core_dong or core_gu}' 관련 검색량이 부족합니다."
            
            filtered_data = []
            for item in data:
                kw = item['relKeyword']
                
                if any(x in kw for x in ["주변", "근처", "오늘"]): continue
                
                is_gu = bool(core_gu and core_gu in kw)
                is_dong = bool(core_dong and core_dong in kw)
                
                # 구나 동 이름이 명확히 안 들어가면 버림 (타지역 차단)
                if (core_gu or core_dong) and not (is_gu or is_dong): continue
                
                is_detail = any(x in kw for x in ['회식', '모임', '룸', '데이트', '가족', '외식', '추천', '가성비', '분위기', '점심', '저녁'])
                
                pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                base_search = pc + mo
                
                weight = 1
                if is_gu and is_dong: weight = 150
                elif is_dong: weight = 100
                elif is_gu: weight = 80
                if core_men and core_men in kw: weight *= 3
                if is_detail: weight *= 2
                
                item['total_search'] = base_search
                item['sort_score'] = base_search * weight
                item['comp_level'] = item.get('compIdx', '중간')
                item['is_gu'] = is_gu
                item['is_dong'] = is_dong
                item['is_detail'] = is_detail
                
                filtered_data.append(item)
                
            sorted_data = sorted(filtered_data, key=lambda x: x['sort_score'], reverse=True)
            
            gold_kws = []
            detail_kws = []
            
            if sorted_data:
                gold_kws.append(sorted_data[0]) 
                
                for kw in sorted_data:
                    if kw['is_gu'] and not kw['is_dong'] and kw not in gold_kws and not kw['is_detail']:
                        gold_kws.append(kw)
                        break
                        
                for kw in sorted_data:
                    if kw['is_dong'] and kw not in gold_kws and not kw['is_detail']:
                        gold_kws.append(kw)
                        break
                        
                for kw in sorted_data:
                    if len(gold_kws) == 5: break
                    if kw not in gold_kws and not kw['is_detail']:
                        gold_kws.append(kw)
            
            for kw in sorted_data:
                if len(detail_kws) == 3: break
                if kw['is_detail'] and kw not in gold_kws:
                    detail_kws.append(kw)
                    
            fallback = [f"{core_dong} 분위기 맛집", f"{core_gu} 데이트 코스", f"{core_dong} 모임장소"]
            while len(detail_kws) < 3:
                detail_kws.append({"relKeyword": fallback[len(detail_kws)], "total_search": "AI 분석", "comp_level": "낮음"})
                
            return gold_kws, detail_kws, "success"
        else:
            return [], [], f"API 에러 (코드: {res.status_code})"
    except Exception as e:
        return [], [], f"시스템 에러: {str(e)}"

# --- 4. OpenAI 텍스트 생성 함수 ---
def generate_ai_content(prompt, api_key):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 상위 1% 플레이스 마케팅 전문 카피라이터입니다. 키워드를 자연스럽고 매력적인 문장으로 녹여냅니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8
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
        with c1: store = st.text_input("매장명", placeholder="우연희")
        with c2: reg = st.text_input("지역 (예: 광주 동구 장동)", placeholder="광주 동구 장동")
        with c3: men = st.text_input("주력메뉴", placeholder="육사시미")
        with c4: event = st.text_input("이벤트 (선택)", placeholder="소주 1병 무료")
            
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 주력메뉴는 필수 입력입니다!")
        else:
            with st.spinner("구/동 혼합 알고리즘으로 타겟 키워드를 분석 중입니다..."):
                g_kws, d_kws, msg = get_naver_golden_keywords(reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if g_kws and len(g_kws) > 0:
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        st.subheader("🎯 지역 메인 키워드 5개 (구/동 혼합)")
                        st.markdown(f"**🥇 1위:** `{g_kws[0]['relKeyword']}` (검색량: **{g_kws[0]['total_search']:,}**건)")
                        for kw in g_kws[1:]:
                            st.markdown(f"- `{kw['relKeyword']}` (검색량: {kw['total_search']:,}건)")
                            
                    with col_b:
                        st.subheader("✨ 상세/상황별 키워드 3개")
                        for kw in d_kws:
                            search_vol = f"{kw['total_search']:,}건" if isinstance(kw['total_search'], int) else kw['total_search']
                            st.markdown(f"✔️ `{kw['relKeyword']}` (검색량: {search_vol})")
                    
                    st.divider()
                    
                    g_names = [k['relKeyword'] for k in g_kws]
                    d_names = [k['relKeyword'] for k in d_kws]
                    
                    event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                    event_rule = "제공된 이벤트를 고객이 방문하고 싶게끔 매력적이고 자연스럽게 문장에 포함하세요." if event else "이벤트가 없으므로 메뉴와 매장의 매력(맛, 분위기 등)을 강조하는 데 집중하세요."

                    prompt = f"""
                    매장명: '{store}'
                    주력메뉴: '{men}'
                    {event_instruction}
                    
                    [필수 반영 타겟 키워드 8개]
                    1. 메인 지역 키워드: {', '.join(g_names)}
                    2. 상세/상황별 키워드: {', '.join(d_names)}

                    [작성 규칙 - 반드시 지킬 것]
                    1. 위 8개의 키워드를 빠짐없이 문장에 자연스럽게 모두 녹여내세요. (키워드 단순 억지 나열 절대 금지)
                    2. 마치 인스타그램 감성 맛집이나 유명 블로거가 소개하듯, 물 흐르듯 자연스러운 문맥을 만들어주세요.
                    3. {event_rule}
                    4. 글자 수는 공백 포함 **130자 ~ 180자 사이**(약 3~4문장)로 구성하세요.
                    5. '육즙', '프라이빗', '가성비', '친절함' 등 방문 욕구를 자극하는 표현을 섞어주세요.
                    6. 세련된 이모티콘 2~3개를 적재적소에 배치하세요.
                    """
                    
                    intro_res = generate_ai_content(prompt, O_API_KEY)
                    st.subheader("📝 8대 키워드 최적화 소개글 (복사/붙여넣기용)")
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
