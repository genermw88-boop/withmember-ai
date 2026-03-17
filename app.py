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

# --- 2. [핵심] 100% 네이버 실제 데이터 추출 엔진 ---
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
    
    # 지역명 정밀 분리 (동, 구, 읍, 면 모두 완벽 대응)
    reg_parts = reg.strip().split()
    core_gu = ""
    core_dong = ""
    for p in reg_parts:
        if p.endswith('구') or p.endswith('시'): core_gu = p
        elif any(p.endswith(s) for s in ['동', '역', '읍', '면', '리']): core_dong = p
    
    if not core_gu and not core_dong and reg_parts:
        core_dong = reg_parts[-1]

    core_men = men.replace(",", " ").split()[0] if men else ""
    
    # [수정] 네이버 API 규정에 맞춰 가장 강력한 힌트 딱 5개만 투척! (에러 원천 차단)
    hints_list = []
    if core_dong: hints_list.extend([f"{core_dong}맛집", f"{core_dong}{core_men}", f"{core_dong}식당"])
    if core_gu: hints_list.extend([f"{core_gu}맛집", f"{core_gu}{core_men}"])
    if not hints_list: hints_list = [f"{reg.replace(' ', '')}맛집"]
    
    params = {'hintKeywords': ",".join(hints_list[:5]), 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"네이버 API 오류 (코드: {res.status_code})"
        
        data = res.json().get('keywordList', [])
        real_kws = []
        
        for item in data:
            kw = item['relKeyword']
            # 불필요 단어 차단
            if any(x in kw for x in ["주변", "근처", "오늘"]): continue
            
            # [타지역 완벽 차단] 내 지역(동/구) 이름이 안 들어간 키워드는 즉시 버림
            is_local = False
            if core_dong and core_dong in kw: is_local = True
            if core_gu and core_gu in kw: is_local = True
            if not is_local: continue
            
            # 네이버 공식 검색량 합산
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total_search = pc + mo
            
            is_detail = any(x in kw for x in ['회식', '모임', '룸', '데이트', '가족', '핫플', '술집', '카페', '가성비', '분위기', '점심', '저녁', '추천'])
            
            item['total_search'] = total_search
            item['is_detail'] = is_detail
            real_kws.append(item)
            
        # 1차 필터: 50건 ~ 3000건 사이의 현실적인 알짜 키워드
        target_kws = [i for i in real_kws if 50 <= i['total_search'] <= 3000]
        
        # 2차 보완: 조건에 맞는 게 부족하면 검색량 높은 진짜 키워드로 채움
        if len(target_kws) < 10:
            target_kws = sorted(real_kws, key=lambda x: x['total_search'], reverse=True)[:15]
            
        # 검색량 순으로 정렬
        sorted_kws = sorted(target_kws, key=lambda x: x['total_search'], reverse=True)
        
        gold_kws = []
        detail_kws = []
        
        # 상세 키워드 최대 5개 추출
        for kw in sorted_kws:
            if kw['is_detail'] and len(detail_kws) < 5:
                detail_kws.append(kw)
                
        # 메인 키워드 최대 5개 추출
        for kw in sorted_kws:
            if not kw['is_detail'] and len(gold_kws) < 5:
                gold_kws.append(kw)
                
        # [중요] AI 가상 키워드(0건, AI 분석 등) 추가 로직을 완전히 삭제했습니다!
        # 네이버가 주는 진짜 데이터만 화면에 출력합니다.
        
        return gold_kws, detail_kws, "success"

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

# --- 4. Streamlit UI (예쁜 화면 복구) ---
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
            with st.spinner("네이버 광고 센터에서 100% 실제 검색량 데이터를 끌어오는 중입니다..."):
                g_kws, d_kws, msg = get_naver_real_keywords(store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success" and (g_kws or d_kws):
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        st.success(f"🎯 지역 메인 키워드 (실제 {len(g_kws)}개)")
                        for i, kw in enumerate(g_kws):
                            search_vol = f"{kw['total_search']:,}건"
                            if i == 0:
                                st.markdown(f"**🥇 1위:** `{kw['relKeyword']}` (검색량: **{search_vol}**)")
                            else:
                                st.markdown(f"- `{kw['relKeyword']}` (검색량: {search_vol})")
                            
                    with col_b:
                        st.info(f"✨ 상세 타겟 키워드 (실제 {len(d_kws)}개)")
                        for kw in d_kws:
                            search_vol = f"{kw['total_search']:,}건"
                            st.markdown(f"✔️ `{kw['relKeyword']}` (검색량: {search_vol})")
                    
                    st.divider()
                    
                    all_real_kws = [k['relKeyword'] for k in g_kws + d_kws]
                    kw_count = len(all_real_kws)
                    
                    event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                    event_rule = "제공된 이벤트를 고객이 방문하고 싶게끔 매력적이고 자연스럽게 문장에 포함하세요." if event else "이벤트가 없으므로 메뉴와 매장의 매력(맛, 분위기 등)을 강조하는 데 집중하세요."

                    prompt = f"""
                    매장명: '{store}'
                    주력메뉴: '{men}'
                    {event_instruction}
                    
                    [네이버에서 추출된 실제 키워드 {kw_count}개]
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
                    st.error(f"검색 결과가 부족하거나 오류가 발생했습니다: {msg}")

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
