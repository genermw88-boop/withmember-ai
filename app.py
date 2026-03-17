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
except Exception as e:
    st.error("Streamlit Cloud의 Secrets 설정이 필요합니다.")
    st.stop()

def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash_mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash_mac.digest()).decode('utf-8')

# --- 2. AI 다이나믹 힌트 추출 ---
def get_ai_dynamic_hints(store, reg, men, api_key):
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"매장명:'{store}', 지역:'{reg}', 메뉴:'{men}'. 이 매장을 방문할 고객들이 네이버에 검색할 만한 핵심 키워드 딱 10개를 콤마(,)로만 연결해서 출력해. 반드시 지역명(동 또는 구)을 포함하고, 메뉴 특성에 맞춰 상황을 다양하게 조합해."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        hints = response.choices[0].message.content.strip().replace(" ", "").replace(".", "").replace("\n", "")
        return ",".join(hints.split(",")[:10])
    except Exception:
        core_reg = reg.split()[-1]
        core_men = men.split()[0]
        return f"{core_reg}맛집,{core_reg}{core_men},{core_reg}회식,{core_reg}데이트,{core_reg}핫플"

# --- 3. 네이버 데이터 추출 및 5+5 강제 보장 ---
def get_naver_golden_keywords(store, reg, men, ai_hints, c_id, a_key, s_key):
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
        if p.endswith('구'): core_gu = p
        elif p.endswith('동') or p.endswith('역'): core_dong = p
    if not core_gu and not core_dong and reg_parts:
        core_dong = reg_parts[-1]

    core_men = men.replace(",", " ").split()[0] if men else ""
    params = {'hintKeywords': ai_hints, 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        
        filtered_data = []
        
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            for item in data:
                kw = item['relKeyword']
                # 타지역 및 불필요 단어 완벽 차단
                if any(x in kw for x in ["주변", "근처", "오늘"]): continue
                
                # 지역명이 아예 포함 안 된 키워드는 가차없이 버림 (서판교, 신림동 등 차단)
                if core_dong and core_dong not in kw and core_gu and core_gu not in kw:
                    continue
                
                pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                base_search = pc + mo
                
                is_detail = any(x in kw for x in ['회식', '모임', '룸', '데이트', '가족', '핫플', '술집', '카페', '가성비', '분위기', '점심', '저녁', '추천'])
                
                item['total_search'] = base_search
                item['is_detail'] = is_detail
                filtered_data.append(item)
                
        # 1차 필터: 100~1500건 사이의 알짜 키워드 우선
        target_kws = [i for i in filtered_data if 100 <= i['total_search'] <= 1500]
        
        # 2차 보완: 데이터가 부족하면 검색량이 높은 순으로 싹 다 끌어옴 (에러 방지)
        if len(target_kws) < 10:
            target_kws = sorted(filtered_data, key=lambda x: x['total_search'], reverse=True)[:15]
            
        gold_kws = []
        detail_kws = []
        
        # [에러 해결] 문제가 되었던 왈러스 연산자(:=) 제거 및 분리
        sorted_data = sorted(target_kws, key=lambda x: x['total_search'], reverse=True)
        
        for kw in sorted_data:
            if not kw['is_detail'] and len(gold_kws) < 5:
                gold_kws.append(kw)
            elif kw['is_detail'] and len(detail_kws) < 5:
                detail_kws.append(kw)
        
        for kw in sorted_data:
            if len(gold_kws) == 5: break
            if kw not in gold_kws and kw not in detail_kws:
                gold_kws.append(kw)
                
        # 5개가 안 채워지면 AI 가상 키워드로 무조건 화면을 채움
        fallback_mains = [f"{core_dong} {core_men}", f"{core_dong} 맛집", f"{core_gu} {core_men}", f"{core_gu} 맛집", f"{core_dong} 식당"]
        while len(gold_kws) < 5:
            for fb in fallback_mains:
                if len(gold_kws) == 5: break
                if not any(k['relKeyword'] == fb.replace(" ", "") for k in gold_kws):
                    gold_kws.append({"relKeyword": fb.replace(" ", ""), "total_search": "AI 분석(소형)"})

        fallback_details = [f"{core_dong} 분위기 맛집", f"{core_dong} 데이트 코스", f"{core_dong} 모임장소 추천", f"{core_dong} {core_men} 추천", f"{core_dong} 핫플"]
        while len(detail_kws) < 5:
            detail_kws.append({"relKeyword": fallback_details[len(detail_kws)].replace(" ", ""), "total_search": "AI 분석(상세)"})
            
        return gold_kws, detail_kws, "success"

    except Exception as e:
        return [], [], f"시스템 에러: {str(e)}"

# --- 4. OpenAI 텍스트 생성 함수 ---
def generate_ai_content(prompt, api_key):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 상위 1% 플레이스 마케팅 전문 카피라이터입니다. 키워드를 기계적으로 나열하지 않고 자연스럽고 매력적인 문장으로 녹여냅니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 5. Streamlit UI 구성 ---
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

st.header("📈 위드멤버 플레이스 최적화")

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
            with st.spinner("1단계: 매장명과 메뉴에 맞는 맞춤 검색 트렌드를 분석 중입니다..."):
                ai_hints = get_ai_dynamic_hints(store, reg, men, O_API_KEY)
                st.caption(f"🤖 AI 힌트: `{ai_hints}`") 
            
            with st.spinner("2단계: 타지역(신림, 서판교 등)을 차단하고 알짜 키워드 10개를 선별합니다..."):
                g_kws, d_kws, msg = get_naver_golden_keywords(store, reg, men, ai_hints, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        st.subheader("🎯 지역 메인 키워드 5개")
                        for i, kw in enumerate(g_kws):
                            search_vol = f"{kw['total_search']:,}건" if isinstance(kw['total_search'], int) else kw['total_search']
                            if i == 0:
                                st.markdown(f"**🥇 1위:** `{kw['relKeyword']}` (검색량: **{search_vol}**)")
                            else:
                                st.markdown(f"- `{kw['relKeyword']}` (검색량: {search_vol})")
                            
                    with col_b:
                        st.subheader("✨ 상세 타겟 키워드 5개")
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
                    
                    [필수 반영 타겟 키워드 10개]
                    1. 메인 지역 키워드: {', '.join(g_names)}
                    2. 상세/상황별 키워드: {', '.join(d_names)}

                    [작성 규칙 - 반드시 지킬 것]
                    1. 위 10개의 키워드를 빠짐없이 문장에 자연스럽게 모두 녹여내세요.
                    2. 마치 인스타그램 감성 맛집이나 유명 블로거가 소개하듯, 물 흐르듯 자연스러운 문맥을 만들어주세요.
                    3. {event_rule}
                    4. 글자 수는 공백 포함 **150자 ~ 200자 사이**(약 4~5문장)로 구성하세요.
                    5. 방문 욕구를 자극하는 맛깔스러운 표현을 섞어주세요.
                    6. 세련된 이모티콘 2~3개를 적재적소에 배치하세요.
                    """
                    
                    with st.spinner("3단계: 상위 1% 카피라이팅을 작성 중입니다..."):
                        intro_res = generate_ai_content(prompt, O_API_KEY)
                        
                    st.subheader("📝 최적화 소개글 (복사/붙여넣기용)")
                    st.info(intro_res)
                    st.code(intro_res)
                else: 
                    st.error(msg)

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
                prompt = f"다음 손님의 리뷰에 대해 친절하고 감사해하는 사장님 톤으로 답글을 써줘. 친근한 이모티콘(예: 😊, 💖, 👍 등)을 문맥에 맞게 2~3개 듬뿍 써줘. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
