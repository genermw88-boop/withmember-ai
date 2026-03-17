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

# --- 2. [NEW] AI 기반 다이나믹 힌트 추출 함수 ---
def get_ai_dynamic_hints(reg, men, api_key):
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"지역:'{reg}', 메뉴/업종:'{men}'. 이 매장을 방문할 고객들이 네이버에 검색할 만한 핵심 키워드 딱 5개를 콤마(,)로만 연결해서 출력해. 반드시 지역명(동 또는 구)을 포함하고, 메뉴 특성에 맞춰 상황(회식, 데이트, 핫플, 술집, 밥집 등)을 다양하게 조합해. (출력예시: 장동술집,광주동구맛집,장동육사시미,장동데이트,동명동핫플)"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", # 힌트 추출은 속도를 위해 mini 모델 사용
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        hints = response.choices[0].message.content.strip()
        # 공백 제거 및 딱 5개만 자르기
        hints = hints.replace(" ", "").replace(".", "").replace("\n", "")
        return ",".join(hints.split(",")[:5])
    except Exception:
        # AI 호출 실패 시 비상용 기본 로직
        core_reg = reg.split()[-1]
        core_men = men.split()[0]
        return f"{core_reg}맛집,{core_reg}{core_men},{core_reg}회식,{core_reg}모임,{core_reg}데이트"

# --- 3. [개선] 다이나믹 힌트를 활용한 네이버 API 호출 ---
def get_naver_golden_keywords(reg, men, ai_hints, c_id, a_key, s_key):
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
    
    # 지역명 필터링용 데이터 준비 (예: 광주 동구 장동 -> city:광주, gu:동구, dong:장동)
    reg_parts = reg.strip().split()
    city = reg_parts[0][:2] if reg_parts else ""
    core_gu = ""
    core_dong = ""
    for p in reg_parts:
        if p.endswith('구'): core_gu = p
        elif p.endswith('동') or p.endswith('역'): core_dong = p
    if not core_gu and not core_dong and reg_parts:
        core_dong = reg_parts[-1]

    core_men = men.replace(",", " ").split()[0] if men else ""
    
    # AI가 뽑아준 5개 힌트를 네이버에 투척!
    params = {'hintKeywords': ai_hints, 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            if not data: return [], [], f"데이터가 부족합니다. AI가 분석한 검색어({ai_hints})에 대한 결과가 없습니다."
            
            filtered_data = []
            # 힌트로 사용된 단어들 분리
            hint_words = ai_hints.split(",")
            
            for item in data:
                kw = item['relKeyword']
                
                # 불필요 단어 컷
                if any(x in kw for x in ["주변", "근처", "오늘"]): continue
                
                # 타지역 차단: 시, 구, 동 이름 중 하나라도 안 들어가면 버림 (단, AI 힌트에 정확히 있던 단어면 살림)
                is_safe_region = False
                if city and city in kw: is_safe_region = True
                if core_gu and core_gu in kw: is_safe_region = True
                if core_dong and core_dong in kw: is_safe_region = True
                if kw in hint_words: is_safe_region = True
                
                if not is_safe_region: continue
                
                is_detail = any(x in kw for x in ['회식', '모임', '룸', '데이트', '가족', '핫플', '술집', '카페', '가성비', '분위기', '점심', '저녁'])
                
                pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                base_search = pc + mo
                
                # 가중치 (AI 힌트 단어거나 메뉴가 들어가면 점수 팍팍)
                weight = 1
                if kw in hint_words: weight = 200
                elif core_dong in kw: weight = 100
                elif core_gu in kw: weight = 80
                if core_men and core_men in kw: weight *= 3
                if is_detail: weight *= 2
                
                item['total_search'] = base_search
                item['sort_score'] = base_search * weight
                item['comp_level'] = item.get('compIdx', '중간')
                item['is_detail'] = is_detail
                
                filtered_data.append(item)
                
            sorted_data = sorted(filtered_data, key=lambda x: x['sort_score'], reverse=True)
            
            gold_kws = []
            detail_kws = []
            
            # 메인 5개 / 상세 3개 분리
            for kw in sorted_data:
                if not kw['is_detail'] and len(gold_kws) < 5:
                    gold_kws.append(kw)
                elif kw['is_detail'] and len(detail_kws) < 3:
                    detail_kws.append(kw)
            
            # 메인 키워드가 부족하면 남은 걸로 채움
            for kw in sorted_data:
                if len(gold_kws) == 5: break
                if kw not in gold_kws and kw not in detail_kws:
                    gold_kws.append(kw)
                    
            fallback = [f"{core_dong} 분위기 맛집", f"{core_dong} 데이트", f"{core_dong} 핫플"]
            while len(detail_kws) < 3:
                detail_kws.append({"relKeyword": fallback[len(detail_kws)], "total_search": "AI 타겟팅", "comp_level": "낮음"})
                
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
        c1, c2, c3, c4 = st.columns(4)
        with c1: store = st.text_input("매장명", placeholder="우연희")
        with c2: reg = st.text_input("지역", placeholder="광주 동구 장동")
        with c3: men = st.text_input("주력메뉴", placeholder="육사시미")
        with c4: event = st.text_input("이벤트 (선택)", placeholder="소주 1병 무료")
            
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 주력메뉴는 필수 입력입니다!")
        else:
            # 1단계: AI 힌트 분석
            with st.spinner("1단계: AI가 매장 특성에 맞는 맞춤 검색 트렌드를 분석 중입니다..."):
                ai_hints = get_ai_dynamic_hints(reg, men, O_API_KEY)
                st.caption(f"🤖 AI 분석 기초 검색어: `{ai_hints}`") # 화면에 AI가 어떻게 분석했는지 슬쩍 보여줍니다.
            
            # 2단계: 네이버 API 검증 및 추출
            with st.spinner("2단계: 네이버 실제 광고 데이터를 기반으로 최적의 조합을 추출합니다..."):
                g_kws, d_kws, msg = get_naver_golden_keywords(reg, men, ai_hints, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if g_kws and len(g_kws) > 0:
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        st.subheader("🎯 지역 메인 키워드 5개")
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
                    
                    with st.spinner("3단계: 상위 1% 카피라이팅을 작성 중입니다..."):
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
