import streamlit as st
import streamlit.components.v1 as components
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

# --- 2. 네이버 키워드 추출 엔진 (메뉴 최우선 로직 적용) ---
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
    if not reg_parts: return [], [], "지역명을 올바르게 입력해주세요."

    valid_locs = [p for p in reg_parts if len(p) >= 2]
    if not valid_locs: valid_locs = reg_parts
    fallback_loc = valid_locs[-1] if valid_locs else "지역"
    fallback_loc_stem = fallback_loc[:-1] if len(fallback_loc) >= 3 and fallback_loc.endswith(('동', '역', '읍', '면')) else fallback_loc

    broad_cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]
    input_broad = [loc for loc in valid_locs if any(loc.startswith(bc) for bc in broad_cities)]
    input_specifics = [loc for loc in valid_locs if loc not in input_broad]
    
    expanded_specifics = []
    for loc in input_specifics:
        expanded_specifics.append(loc)
        if len(loc) >= 2 and loc[-1] in ['동', '역', '구', '시', '군', '읍', '면', '리']:
            expanded_specifics.append(loc[:-1])
    expanded_specifics = sorted(list(set(expanded_specifics)), key=len, reverse=True)
    input_broad = sorted(list(set(input_broad)), key=len, reverse=True)

    core_men_list = men.replace(",", " ").split()
    core_men_list = sorted(list(set(core_men_list)), key=len, reverse=True)
    
    is_cafe = any(c in men for c in ['카페', '커피', '디저트', '베이커리', '빵', '마카롱', '케이크', '다과'])
    forbidden = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월', '여름', '겨울', '봄', '가을', '비오는날', '크리스마스', '연말', '신년']
    
    if not is_cafe:
        forbidden.extend(['카페', '커피', '디저트', '베이커리', '빵', '마카롱', '케이크', '다과', '브런치', '대형카페', '스타벅스', '에스프레소', '빙수'])
    else:
        forbidden.extend(['고기', '삼겹살', '곱창', '막창', '횟집', '회식', '술집', '포차', '국밥', '해장', '치킨', '피자', '중국집'])

    is_drink_meat = any(d in men for d in ['술', '맥주', '소주', '포차', '고기', '삼겹살', '곱창', '막창', '안주', '회식'])
    if not is_drink_meat:
        forbidden.extend(['술집', '포차', '호프', '이자카야', '소주', '칵테일', '와인바'])

    extended_generics = ['맛집', '식당', '밥집', '데이트', '핫플', '가볼만한곳', '추천', '점심', '저녁', '분위기', '데이트코스', '가족식사', '모임장소', '모임', '회식', '술집', '고기집', '고깃집', '외식', '장소', '룸식당', '룸', '코스', '드라이브', '근교', '존맛', '가성비', '근처', '주변', '숨은', '오빠랑', '아이와', '놀거리', '여행', '식사', '야식']
    extended_generics = sorted(list(set(extended_generics)), key=len, reverse=True)
    location_suffixes = ['동', '역', '구', '시', '군', '읍', '면', '리', '길', '마을', '숲', '산', '공원', '대', '단지', '거리', '시장', '해변']
    safe_fluff = ['도', '특별시', '광역시', '의', '과', '와', '가', '찐']

    def is_keyword_valid(kw):
        kw_ns = kw.replace(" ", "")
        if any(f in kw_ns for f in forbidden): return False
        has_specific = any(s in kw_ns for s in expanded_specifics)
        has_broad = any(b in kw_ns for b in input_broad)
        if not has_specific and not has_broad: return False

        temp = kw_ns
        if has_specific:
            for s in expanded_specifics: temp = temp.replace(s, "")
        elif has_broad:
            for b in input_broad: temp = temp.replace(b, "")
            
        for m in core_men_list: temp = temp.replace(m, "")
        for g in extended_generics: temp = temp.replace(g, "")
        for f in safe_fluff: temp = temp.replace(f, "")

        if has_specific:
            if len(temp) == 0: return True
            if len(temp) == 1 and temp in location_suffixes: return True 
            return False 
        else:
            if len(temp) == 0: return True
            return False

    hints_list = []
    for loc in reversed(valid_locs):
        hints_list.append(f"{loc}맛집")
        for m in core_men_list[:2]: hints_list.append(f"{loc}{m}")
        if len(hints_list) >= 5: break
    
    params = {'hintKeywords': ",".join(hints_list[:5]), 'showDetail': 1}
    gold_kws, detail_kws = [], []
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code == 200:
            data = res.json().get('keywordList', [])
            valid_kws = []
                
            for item in data:
                kw = item['relKeyword']
                pc = 0 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
                mo = 0 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
                total_search = pc + mo
                if total_search < 50: continue
                if not is_keyword_valid(kw): continue
                
                item['total_search'] = total_search
                item['is_detail'] = any(x in kw for x in core_men_list + ['회식', '모임', '룸', '데이트', '가족', '핫플', '카페', '점심', '저녁', '추천', '분위기', '가볼만한곳', '코스'])
                
                # 🚨 [핵심 추가] 내가 입력한 '메뉴'가 직접 포함된 키워드인지 확인
                item['is_menu'] = any(m in kw for m in core_men_list)
                valid_kws.append(item)
                    
            valid_kws = sorted(valid_kws, key=lambda x: x['total_search'], reverse=True)
            
            # 🚨 [핵심 수정] 범용 키워드가 메뉴 키워드를 밀어내지 못하게, '메뉴' 키워드를 먼저 뽑아냄!
            menu_kws = [kw for kw in valid_kws if kw['is_menu']]
            other_detail_kws = [kw for kw in valid_kws if kw['is_detail'] and not kw['is_menu']]
            main_kws = [kw for kw in valid_kws if not kw['is_detail']]
            
            for kw in main_kws:
                if len(gold_kws) < 5: gold_kws.append(kw)
            
            # 메뉴 키워드 최우선 할당
            for kw in menu_kws:
                if len(detail_kws) < 5: detail_kws.append(kw)
            
            # 자리가 남으면 범용 상세 키워드 할당
            for kw in other_detail_kws:
                if len(detail_kws) < 5: detail_kws.append(kw)

    except Exception:
        pass 

    # 🚨 [핵심 수정] 백업 로직에서도 입력한 모든 메뉴가 우선적으로 생성되도록 수정
    fallback_generics = ['맛집', '핫플', '가볼만한곳', '데이트', '추천']
    fallback_details = core_men_list + ['점심', '저녁', '모임', '분위기']
    
    idx = 0
    while len(gold_kws) < 5:
        kw_str = f"{fallback_loc} {fallback_generics[idx % len(fallback_generics)]}"
        if not any(k['relKeyword'].replace(" ", "") == kw_str.replace(" ", "") for k in gold_kws):
            gold_kws.append({'relKeyword': kw_str, 'total_search': '🔥 추천 타겟'})
        idx += 1
        
    idx = 0
    while len(detail_kws) < 5:
        kw_str = f"{fallback_loc_stem} {fallback_details[idx % len(fallback_details)]}"
        if not any(k['relKeyword'].replace(" ", "") == kw_str.replace(" ", "") for k in detail_kws):
            detail_kws.append({'relKeyword': kw_str, 'total_search': '✨ 맞춤 키워드'})
        idx += 1

    return gold_kws[:5], detail_kws[:5], "success"

# --- 3. OpenAI 카피라이팅 함수 ---
def generate_ai_content(prompt, api_key, system_role="당신은 상위 1% 플레이스 마케팅 전문 카피라이터입니다.", temp=0.7):
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": prompt}
            ],
            temperature=temp 
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 4. Streamlit UI ---
st.set_page_config(page_title="위드멤버 플레이스 최적화", layout="wide")

with st.sidebar:
    st.title("API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드")

st.header("위드멤버 플레이스 최적화 시스템")

tab1, tab2 = st.tabs(["키워드 & 새소식 생성", "방문자 리뷰 답글"])

with tab1:
    with st.form("intro_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: store = st.text_input("매장명", placeholder="정통집 운서점")
        with c2: reg = st.text_input("지역 (시/구/동 모두 입력)", placeholder="인천 중구 운서동")
        with c3: men = st.text_input("메뉴", placeholder="돼지김치구이")
        with c4: event = st.text_input("이벤트 (선택)", placeholder="음료 제공")
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 메뉴는 필수 입력입니다!")
        else:
            with st.spinner("네이버 상권 데이터 수집 및 새소식을 길고 풍성하게 작성 중입니다..."):
                g_kws, d_kws, msg = get_naver_real_keywords(store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    all_real_kws = [k['relKeyword'] for k in g_kws + d_kws]
                    event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                    system_role = f"""당신은 '{store}' 매장 전담 마케터입니다. 네이버 스마트플레이스의 '새소식' 게시글을 작성합니다."""

                    prompt = f"""
                    매장명: '{store}'
                    지역: '{reg}'
                    주력메뉴: '{men}'
                    {event_instruction}
                    
                    [필수 반영 타겟 키워드 총 10개]
                    {', '.join(all_real_kws)}

                    [작성 규칙]
                    1. [제목]과 [본문]을 반드시 구분해서 작성하세요.
                    2. [제목]: 30자 내외로 고객의 이목을 끄는 매력적인 제목을 작성하세요. (적절한 이모지 1~2개 포함)
                    3. [본문]: 위 10개의 키워드를 모두 자연스럽게 문맥에 녹여내어 300자 ~ 500자 분량으로 길고 상세하게 작성하세요.
                    4. [이모티콘 필수]: 글이 지루하지 않도록, 문장 곳곳에 내용과 어울리는 귀엽고 시선을 끄는 이모티콘을 듬뿍 사용해주세요!
                    5. 고객에게 직접 이야기하듯 다정하고 친근한 말투를 사용하세요.
                    6. [강력 경고] 제공된 정보 외에 엉뚱한 정보나 해시태그(#)를 절대 넣지 마세요.
                    """
                    
                    intro_res = generate_ai_content(prompt, O_API_KEY, system_role=system_role, temp=0.4)
                    
                    title_part = "제목 생성 중..."
                    body_part = intro_res
                    if "[제목]" in intro_res and "[본문]" in intro_res:
                        parts = intro_res.split("[본문]")
                        title_part = parts[0].replace("[제목]", "").strip()
                        body_part = parts[1].strip()

                    display_event = event if event else "없음"
                    st.divider()
                    
                    def format_search(val):
                        if isinstance(val, str): 
                            return f"<span style='color:#007bff; font-size:14px; font-weight:700;'>{val}</span>"
                        return f"({val:,}건)"

                    gold_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between;'><b>🎯 {k['relKeyword']}</b> <span style='color:#666;'>{format_search(k['total_search'])}</span></li>" for k in g_kws])
                    detail_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between;'><b>✨ {k['relKeyword']}</b> <span style='color:#666;'>{format_search(k['total_search'])}</span></li>" for k in d_kws])
                    
                    html_content = f"""
                    <div id="capture-area" style="padding:25px; background:#ffffff; font-family:'Pretendard', sans-serif; border:1px solid #e9ecef; border-radius:12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <h2 style="margin-bottom:25px; color:#212529; font-weight:800; text-align:center;">위드멤버 플레이스 최적화 리포트</h2>
                        
                        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:30px;">
                            <div style="background:#f8f9fa; border:1px solid #dee2e6; padding:15px; border-radius:8px;"><small style="color:#6c757d; font-weight:600;">매장명</small><br><b style="font-size:16px; color:#212529;">{store}</b></div>
                            <div style="background:#f8f9fa; border:1px solid #dee2e6; padding:15px; border-radius:8px;"><small style="color:#6c757d; font-weight:600;">지역</small><br><b style="font-size:16px; color:#212529;">{reg}</b></div>
                            <div style="background:#f8f9fa; border:1px solid #dee2e6; padding:15px; border-radius:8px;"><small style="color:#6c757d; font-weight:600;">메뉴</small><br><b style="font-size:16px; color:#212529;">{men}</b></div>
                            <div style="background:#f8f9fa; border:1px solid #dee2e6; padding:15px; border-radius:8px;"><small style="color:#6c757d; font-weight:600;">이벤트</small><br><b style="font-size:16px; color:#212529;">{display_event}</b></div>
                        </div>
                        
                        <div style="display:flex; gap:20px; margin-bottom:30px;">
                            <div style="flex:1; background:#ffffff; border:1px solid #dee2e6; border-radius:10px; padding:20px;">
                                <h4 style="margin-top:0; color:#212529; font-weight:700;">📍 지역 메인 키워드</h4>
                                <ul style="list-style:none; padding:0; margin:0; color:#495057;">{gold_li}</ul>
                            </div>
                            <div style="flex:1; background:#ffffff; border:1px solid #dee2e6; border-radius:10px; padding:20px;">
                                <h4 style="margin-top:0; color:#212529; font-weight:700;">🔍 상세 타겟 키워드</h4>
                                <ul style="list-style:none; padding:0; margin:0; color:#495057;">{detail_li}</ul>
                            </div>
                        </div>
                        
                        <div style="background:#f8f9fa; border-radius:12px; padding:25px; border:1px solid #dee2e6;">
                            <div style="margin-bottom: 20px;">
                                <h4 style="color:#007bff; margin:0 0 10px 0; font-size:17px; font-weight:700;">📢 추천 새소식 제목</h4>
                                <p style="font-size:20px; font-weight:800; color:#212529; margin:0;">{title_part}</p>
                            </div>
                            
                            <hr style="border:0; border-top:1px solid #dee2e6; margin:20px 0;">
                            
                            <div>
                                <h4 style="color:#007bff; margin:0 0 10px 0; font-size:17px; font-weight:700;">📝 최적화 본문</h4>
                                <p style="font-size:16px; line-height:1.8; color:#495057; margin:0; word-break: keep-all;">{body_part.replace('\n', '<br>')}</p>
                            </div>
                        </div>
                    </div>
                    
                    <button onclick="downloadImage()" style="margin-top:25px; width:100%; padding:16px; background-color:#343a40; color:#ffffff; border:none; border-radius:8px; font-size:18px; font-weight:bold; cursor:pointer; transition:0.2s;">
                        📥 리포트 화면 이미지로 다운로드
                    </button>

                    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
                    <script>
                        function downloadImage() {{
                            const element = document.getElementById('capture-area');
                            html2canvas(element, {{ scale: 2, backgroundColor: "#ffffff" }}).then(canvas => {{
                                let link = document.createElement('a');
                                link.download = '{store}_최적화리포트.png';
                                link.href = canvas.toDataURL('image/png');
                                link.click();
                            }});
                        }}
                    </script>
                    """
                    components.html(html_content, height=1200, scrolling=True)
                else: 
                    st.error(f"오류: {msg}")

with tab2:
    st.header("방문자 리뷰 답글 생성기")
    with st.form("review_form"):
        review_content = st.text_area("손님이 남긴 리뷰 내용을 입력하세요", height=150)
        submit_review = st.form_submit_button("정성 가득한 답글 생성")
    if submit_review:
        if not review_content: st.warning("리뷰 내용을 입력해주세요!")
        else:
            with st.spinner("사장님의 진심을 담아 정성스럽고 긴 답글을 작성 중입니다..."):
                system_role = "당신은 매장을 찾아주신 고객에게 진심으로 감사할 줄 아는 따뜻하고 다정한 사장님입니다."
                prompt = f"""
                아래 손님이 남겨주신 소중한 방문자 리뷰에 대해, 사장님의 진심이 가득 담긴 정성스러운 답글을 작성해주세요.

                [작성 규칙]
                1. 손님이 남긴 리뷰 내용(메뉴, 맛, 분위기, 서비스 등)을 구체적으로 언급하며 깊은 공감과 감사를 표현하세요.
                2. 기계적인 답변이 되지 않도록, 최소 300자 이상으로 매우 길고 상세하게 작성해주세요.
                3. 따뜻하고 친근한 사람의 온기가 느껴지는 말투를 사용하세요. (예: ~했어요, ~랍니다, 정말 감사드려요 등)
                4. 글의 분위기를 살려주는 예쁘고 다정한 이모티콘을 3~4개 정도 자연스럽게 섞어주세요.
                5. 다음 방문을 기대하게 만드는 따뜻한 맺음말을 꼭 넣어주세요.
                6. [절대 금지] 해시태그(#)나 추천 키워드를 의미 없이 나열하지 마세요. 오직 자연스러운 편지 형식이어야 합니다.

                손님의 리뷰 내용:
                "{review_content}"
                """
                
                review_res = generate_ai_content(prompt, O_API_KEY, system_role=system_role, temp=0.7)
                
                st.markdown(f"""
                <div style="background-color:#ffffff; padding:25px; border-radius:12px; border:1px solid #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-top: 15px;">
                    <h4 style="color:#007bff; margin-top:0; font-family:'Pretendard', sans-serif;">✨ 사장님의 진심이 담긴 답글</h4>
                    <hr style="border:0; border-top:1px solid #dee2e6; margin:15px 0;">
                    <p style="color:#212529; line-height:1.8; font-size:16px; font-family:'Pretendard', sans-serif; word-break: keep-all; margin:0;">
                        {review_res.replace('\n', '<br>')}
                    </p>
                </div>
                """, unsafe_allow_html=True)
