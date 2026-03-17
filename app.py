import streamlit as st
import time
import hashlib
import hmac
import base64
import requests
from openai import OpenAI

# --- 1. 환경 설정 및 API 키 ---
try:
    N_CUSTOMER_ID = st.secrets.get("NAVER_CUSTOMER_ID", "4320532")
    N_API_KEY = st.secrets.get("NAVER_API_KEY", "")
    N_SECRET_KEY = st.secrets.get("NAVER_SECRET_KEY", "")
    O_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
except Exception:
    st.error("API 키 설정이 필요합니다.")
    st.stop()

def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# --- 2. [핵심] 네이버 100~1000건 & 맞춤 상세 키워드 추출 ---
def get_naver_real_keywords(store, reg, men, c_id, a_key, s_key):
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
    
    reg_parts = reg.strip().split()
    core_gu = ""
    core_dong = ""
    for p in reg_parts:
        if p.endswith('구') or p.endswith('시'): core_gu = p
        elif any(p.endswith(s) for s in ['동', '역', '읍', '면', '리']): core_dong = p
    
    if not core_gu and not core_dong and reg_parts:
        core_dong = reg_parts[-1]

    # 메뉴의 핵심 단어만 추출 (예: "꽃삼겹, 목살" -> "꽃삼겹")
    core_men = men.replace(",", " ").split()[0] if men else ""
    
    # 💡 [개선] 네이버에 던질 힌트를 매장(메뉴)에 완벽하게 맞춤!
    hints_list = []
    if core_dong:
        hints_list.extend([f"{core_dong}맛집", f"{core_dong}{core_men}", f"{core_dong}회식", f"{core_dong}데이트", f"{core_dong}가볼만한곳"])
    elif core_gu:
        hints_list.extend([f"{core_gu}맛집", f"{core_gu}{core_men}", f"{core_gu}회식"])
    
    params = {'hintKeywords': ",".join(hints_list[:5]), 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"네이버 API 오류 (코드: {res.status_code})"
        
        data = res.json().get('keywordList', [])
        valid_kws = []
        
        for item in data:
            kw = item['relKeyword']
            if any(x in kw for x in ["주변", "근처", "오늘"]): continue
            
            # 타지역 차단
            if core_dong and core_dong not in kw and core_gu and core_gu not in kw: 
                continue
            
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total_search = pc + mo
            
            # 🚨 [가장 중요한 필터] 100건 이상 ~ 1000건 이하만 무조건 통과!
            if 100 <= total_search <= 1000:
                # 상세 키워드 조건: 메뉴 이름이 들어가 있거나, 특정 상황을 나타내는 단어
                is_detail = any(x in kw for x in [core_men, '회식', '모임', '룸', '데이트', '가족', '핫플', '술집', '카페', '점심', '저녁', '추천'])
                
                item['total_search'] = total_search
                item['is_detail'] = is_detail
                valid_kws.append(item)
                
        # 검색량 순으로 정렬
        valid_kws = sorted(valid_kws, key=lambda x: x['total_search'], reverse=True)
        
        gold_kws = []
        detail_kws = []
        
        # 메인과 상세로 분류 (각각 최대 5개씩)
        for kw in valid_kws:
            if kw['is_detail'] and len(detail_kws) < 5:
                detail_kws.append(kw)
            elif not kw['is_detail'] and len(gold_kws) < 5:
                gold_kws.append(kw)
        
        # 만약 한쪽이 5개가 안 채워졌는데 다른 쪽에 여유분이 있다면 끌어와서 꽉 채워줌
        for kw in valid_kws:
            if len(gold_kws) < 5 and kw not in gold_kws and kw not in detail_kws:
                gold_kws.append(kw)
            elif len(detail_kws) < 5 and kw not in gold_kws and kw not in detail_kws:
                detail_kws.append(kw)
                
        return gold_kws[:5], detail_kws[:5], "success"

    except Exception as e:
        return [], [], f"시스템 에러: {str(e)}"

# --- 3. OpenAI 카피라이팅 함수 ---
def generate_ai_content(prompt, api_key):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 상위 1% 플레이스 마케팅 전문 카피라이터입니다. 키워드를 기계적으로 나열하지 않고 아주 매력적인 문장으로 녹여냅니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 4. Streamlit UI ---
st.set_page_config(page_title="위드멤버 플레이스 최적화", page_icon="🚀", layout="wide")

with st.sidebar:
    st.title("🔑 API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        st.warning("Secrets를 설정하거나 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드 ✅")

st.header("📈 위드멤버 플레이스 최적화 시스템")

tab1, tab2 = st.tabs(["🎯 키워드 & 소개글", "💬 방문자 리뷰 답글"])

with tab1:
    with st.form("intro_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: store = st.text_input("매장명", placeholder="다정푸드 뒤집고")
        with c2: reg = st.text_input("지역", placeholder="광주 남구 양림동")
        with c3: men = st.text_input("메뉴", placeholder="꽃삼겹")
        with c4: event = st.text_input("이벤트 (선택)", placeholder="소주 1병 무료")
            
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 메뉴는 필수 입력입니다!")
        else:
            with st.spinner("100~1000건 사이의 메뉴 맞춤형 알짜 키워드를 추출 중입니다..."):
                g_kws, d_kws, msg = get_naver_real_keywords(store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    if not g_kws and not d_kws:
                        st.warning("이 지역과 메뉴 조합으로는 '검색량 100~1000건' 사이의 키워드가 없습니다. 네이버 공식 데이터 기준이므로 지역명을 조금 더 넓게(구 단위 등) 입력해 보세요.")
                    else:
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            st.success(f"🎯 지역 메인 키워드 (추출: {len(g_kws)}개)")
                            for i, kw in enumerate(g_kws):
                                search_vol = f"{kw['total_search']:,}건"
                                st.markdown(f"- `{kw['relKeyword']}` (검색량: **{search_vol}**)")
                                
                        with col_b:
                            st.info(f"✨ 메뉴 맞춤 상세 키워드 (추출: {len(d_kws)}개)")
                            for kw in d_kws:
                                search_vol = f"{kw['total_search']:,}건"
                                st.markdown(f"✔️ `{kw['relKeyword']}` (검색량: **{search_vol}**)")
                        
                        st.divider()
                        
                        all_real_kws = [k['relKeyword'] for k in g_kws + d_kws]
                        kw_count = len(all_real_kws)
                        
                        event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                        event_rule = "제공된 이벤트를 고객이 방문하고 싶게끔 매력적이고 자연스럽게 문장에 포함하세요." if event else "이벤트가 없으므로 메뉴와 매장의 매력(맛, 분위기 등)을 강조하는 데 집중하세요."

                        prompt = f"""
                        매장명: '{store}'
                        주력메뉴: '{men}'
                        {event_instruction}
                        
                        [네이버에서 추출된 실제 타겟 키워드 {kw_count}개]
                        {', '.join(all_real_kws)}

                        [작성 규칙 - 반드시 지킬 것]
                        1. 위 {kw_count}개의 키워드를 빠짐없이 문장에 자연스럽게 모두 녹여내세요. (단순 나열 금지)
                        2. 마치 인스타그램 감성 맛집이나 유명 블로거가 소개하듯, 물 흐르듯 자연스러운 문맥을 만들어주세요.
                        3. {event_rule}
                        4. 글자 수는 공백 포함 **150자 ~ 200자 사이**(약 4~5문장)로 구성하세요.
                        5. 방문 욕구를 자극하는 맛깔스러운 표현을 섞어주세요.
                        6. 세련된 이모티콘 2~3개를 적재적소에 배치하세요.
                        """
                        
                        with st.spinner("최적화된 키워드를 바탕으로 상위 1% 카피라이팅을 작성 중입니다..."):
                            intro_res = generate_ai_content(prompt, O_API_KEY)
                            
                        st.subheader("📝 최적화 소개글 (복사/붙여넣기용)")
                        st.info(intro_res)
                        st.code(intro_res)
                else: 
                    st.error(f"오류가 발생했습니다: {msg}")

with tab2:
    st.header("💬 방문자 리뷰 답글 생성기")
    with st.form("review_form"):
        review_content = st.text_area("손님이 남긴 리뷰 내용을 입력하세요")
        submit_review = st.form_submit_button("답글 생성")
    
    if submit_review:
        if not review_content:
            st.warning("리뷰 내용을 입력해주세요!")
        else:
            with st.spinner("정성스러운 답글을 작성 중..."):
                prompt = f"다음 손님의 리뷰에 대해 친절하고 감사해하는 사장님 톤으로 답글을 써줘. 친근한 이모티콘을 문맥에 맞게 2~3개 듬뿍 써줘. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
