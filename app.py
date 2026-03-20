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

# --- 2. [완벽 개선] 100% 화이트리스트 기반 추출 엔진 ---
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
    
    # 1. 입력된 지역 단어 모두 추출
    reg_parts = reg.strip().split()
    if not reg_parts:
        return [], [], "지역명을 올바르게 입력해주세요."

    valid_locs = [p for p in reg_parts if len(p) >= 2]
    if not valid_locs: valid_locs = reg_parts

    broad_cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]
    input_broad = [loc for loc in valid_locs if any(loc.startswith(bc) for bc in broad_cities)]
    input_specific = [loc for loc in valid_locs if loc not in input_broad]

    core_men_list = men.replace(",", " ").split()
    
    hints_list = []
    for loc in reversed(valid_locs):
        hints_list.append(f"{loc}맛집")
        for m in core_men_list[:2]:
            hints_list.append(f"{loc}{m}")
        if len(hints_list) >= 5: break
    
    params = {'hintKeywords': ",".join(hints_list[:5]), 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"네이버 API 오류 (코드: {res.status_code})"
        
        data = res.json().get('keywordList', [])
        valid_kws = []
        
        for item in data:
            kw = item['relKeyword']
            kw_nospace = kw.replace(" ", "")
            if any(x in kw for x in ["주변", "근처", "오늘"]): continue
            
            # 🚨 [규칙 1] 타지역(울산 중구 등) 100% 차단
            conflict = False
            for bc in broad_cities:
                if bc not in input_broad and bc in kw:
                    conflict = True
                    break
            if conflict: continue
            
            # 🚨 [규칙 2] 내가 입력한 지역 단어가 아예 없으면 버림
            matched_broads = [loc for loc in input_broad if loc in kw]
            matched_specifics = [loc for loc in input_specific if loc in kw]
            if not matched_broads and not matched_specifics: continue
            
            # 광역(인천)만 있고 세부(운서동)가 없을 때, 다른 동네(부평, 송도)가 섞여 있는지 엄격히 검사
            if matched_broads and not matched_specifics:
                temp_kw = kw_nospace
                for bc in matched_broads: temp_kw = temp_kw.replace(bc, "")
                for m in core_men_list: temp_kw = temp_kw.replace(m, "")
                for sw in ['맛집', '식당', '카페', '술집', '밥집', '핫플', '데이트', '추천', '가볼만한곳', '회식', '모임', '점심', '저녁']:
                    temp_kw = temp_kw.replace(sw, "")
                # 남은 글자에 동/구/역/길/리가 있으면 무조건 다른 동네이므로 차단
                if any(char in temp_kw for char in ['동', '구', '역', '길', '리', '읍', '면']):
                    continue

            # 🚨 [가장 중요한 핵심 방어막: 화이트리스트]
            # 1) 메뉴 이름이 그대로 박혀있거나
            is_menu_related = any(m in kw for m in core_men_list)
            
            # 2) 완벽하게 순수한 "지역명 + 일반명사(맛집, 핫플 등)" 인 경우만 통과!
            is_exact_generic = False
            allowed_generics = ['맛집', '식당', '밥집', '술집', '데이트', '핫플', '가볼만한곳', '추천', '회식', '모임장소', '모임', '점심', '저녁', '분위기', '카페', '데이트코스', '가족식사', '가족모임']
            for loc in valid_locs:
                for g in allowed_generics:
                    if kw_nospace == f"{loc}{g}":
                        is_exact_generic = True
                        break
                if is_exact_generic: break
                
            # 메뉴도 안 들어있고, 순수한 제네릭도 아니면(예: 운서동 장어, 인천 레스토랑) -> 즉시 사살!
            if not is_menu_related and not is_exact_generic:
                continue 
            
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total_search = pc + mo
            
            is_detail = any(x in kw for x in core_men_list + ['회식', '모임', '룸', '데이트', '가족', '핫플', '카페', '점심', '저녁', '추천', '분위기', '가볼만한곳', '코스'])
            
            item['total_search'] = total_search
            item['is_detail'] = is_detail
            valid_kws.append(item)
                
        # 100~1000건 필터링 
        tier1 = sorted([k for k in valid_kws if 100 <= k['total_search'] <= 1000], key=lambda x: x['total_search'], reverse=True)
        tier2 = sorted([k for k in valid_kws if (50 <= k['total_search'] <= 3000) and (k not in tier1)], key=lambda x: x['total_search'], reverse=True)
        tier3 = sorted([k for k in valid_kws if k not in tier1 and k not in tier2], key=lambda x: x['total_search'], reverse=True)
        
        final_pool = tier1 + tier2 + tier3
        
        gold_kws = []
        detail_kws = []
        
        for kw in final_pool:
            if kw['is_detail'] and len(detail_kws) < 5: detail_kws.append(kw)
            elif not kw['is_detail'] and len(gold_kws) < 5: gold_kws.append(kw)
        
        for kw in final_pool:
            if len(gold_kws) < 5 and kw not in gold_kws and kw not in detail_kws: gold_kws.append(kw)
            if len(detail_kws) < 5 and kw not in gold_kws and kw not in detail_kws: detail_kws.append(kw)
                
        # 💡 [핵심 스마트 보완] 카페냐 식당이냐에 따라 부족한 빈칸을 완벽하게 맞춤 생성
        is_cafe = any(c in men for c in ['카페', '커피', '디저트', '베이커리', '빵', '마카롱', '케이크', '다과'])
        
        fb_mains = []
        fb_details = []
        
        for loc in reversed(valid_locs):
            fb_mains.append(f"{loc}{core_men_list[0]}")
            fb_mains.append(f"{loc}맛집" if not is_cafe else f"{loc}카페")
            
            if is_cafe:
                fb_details.extend([f"{loc}디저트", f"{loc}데이트", f"{loc}분위기", f"{loc}핫플", f"{loc}추천"])
            else:
                fb_details.extend([f"{loc}밥집" if not "술" in men else f"{loc}술집", f"{loc}회식", f"{loc}모임장소", f"{loc}데이트", f"{loc}추천"])
            
        for fb in fb_mains:
            if len(gold_kws) >= 5: break
            if not any(k['relKeyword'] == fb for k in gold_kws + detail_kws):
                gold_kws.append({'relKeyword': fb, 'total_search': 10, 'is_detail': False})

        for fb in fb_details:
            if len(detail_kws) >= 5: break
            if not any(k['relKeyword'] == fb for k in gold_kws + detail_kws):
                detail_kws.append({'relKeyword': fb, 'total_search': 10, 'is_detail': True})
                
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
                {"role": "system", "content": "당신은 상위 1% 플레이스 마케팅 전문 카피라이터입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7 
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"생성 실패: {str(e)}"

# --- 4. Streamlit UI (폰트 및 UI 통일 유지) ---
st.set_page_config(page_title="위드멤버 플레이스 최적화", layout="wide")

with st.sidebar:
    st.title("API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        st.warning("Secrets를 설정하거나 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드")

st.header("위드멤버 플레이스 최적화 시스템")

tab1, tab2 = st.tabs(["키워드 & 소개글", "방문자 리뷰 답글"])

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
            with st.spinner("네이버 상권 데이터 수집 및 소개글을 생성 중입니다... (약 10초 소요)"):
                g_kws, d_kws, msg = get_naver_real_keywords(store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    all_real_kws = [k['relKeyword'] for k in g_kws + d_kws]
                    event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                    
                    prompt = f"""
                    매장명: '{store}'
                    지역: '{reg}'
                    주력메뉴: '{men}'
                    {event_instruction}
                    
                    [필수 반영 타겟 키워드 10개]
                    {', '.join(all_real_kws)}

                    [작성 규칙]
                    1. 위 10개의 키워드를 빠짐없이 문장에 자연스럽게 모두 녹여내세요.
                    2. 인스타그램 감성 맛집 블로거처럼 물 흐르듯 자연스럽게 작성하세요.
                    3. 글자 수는 공백 포함 150자 ~ 200자 사이로 넉넉하게 구성하세요.
                    4. 세련된 이모티콘 2~3개를 배치하세요.
                    5. [강력 경고] 제공된 지역('{reg}')과 메뉴('{men}') 외에 다른 지역명이나 엉뚱한 메뉴는 절대 지어내서 적지 마세요.
                    6. [강력 경고] 글 마지막에 해시태그(#)를 달거나, 추천 키워드 목록을 따로 출력하지 마세요. 오직 소개글 본문 텍스트만 작성하세요.
                    """
                    intro_res = generate_ai_content(prompt, O_API_KEY)
                    intro_html = intro_res.replace('\n', '<br>')
                    display_event = event if event else "없음"
                    
                    st.divider()
                    
                    gold_li = "".join([f"<li style='padding: 14px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 16px; font-weight: 700; color: #212529;'>🎯 {k['relKeyword']}</span> <span style='font-size: 16px; font-weight: 700; color: #212529;'>(검색량: {k['total_search']:,}건)</span></li>" for k in g_kws])
                    detail_li = "".join([f"<li style='padding: 14px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 16px; font-weight: 700; color: #212529;'>✨ {k['relKeyword']}</span> <span style='font-size: 16px; font-weight: 700; color: #212529;'>(검색량: {k['total_search']:,}건)</span></li>" for k in d_kws])
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
                        <style>
                            @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
                            body {{ font-family: 'Pretendard', sans-serif; background-color: #ffffff; margin: 0; padding: 0; }}
                            .report-box {{ width: 100%; max-width: 800px; padding: 25px; background: #ffffff; box-sizing: border-box; }}
                            
                            .header-title {{ border-bottom: 1px solid #ddd; padding-bottom: 15px; margin-bottom: 25px; }}
                            .header-title h2 {{ color: #212529; font-size: 26px; margin: 0; font-weight: 800; }}
                            
                            .input-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 35px; }}
                            .input-item label {{ display: block; font-size: 13px; font-weight: 600; color: #666; margin-bottom: 6px; }}
                            .input-item div {{ background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 12px; border-radius: 6px; font-size: 15px; font-weight: 600; color: #212529; }}
                            
                            .kw-container {{ display: flex; justify-content: space-between; gap: 20px; margin-bottom: 35px; }}
                            .kw-box {{ flex: 1; }}
                            .box-title {{ padding: 14px 15px; border-radius: 6px; font-size: 17px; font-weight: bold; margin-bottom: 15px; text-align: center; }}
                            .title-main {{ background-color: #f8f9fa; border: 1px solid #dee2e6; color: #212529; }}
                            .title-detail {{ background-color: #f8f9fa; border: 1px solid #dee2e6; color: #212529; }}
                            ul {{ list-style: none; padding: 0; margin: 0; }}
                            
                            .intro-section h3 {{ font-size: 22px; color: #212529; margin-bottom: 15px; font-weight: 800; }}
                            .intro-box {{ background-color: #f8f9fa; padding: 25px; border-radius: 8px; border: 1px solid #dee2e6; font-size: 16px; line-height: 1.7; color: #212529; }}
                            
                            .btn-down {{ margin-top: 25px; padding: 16px; background-color: #343a40; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 18px; font-weight: bold; width: 100%; max-width: 800px; text-align: center; transition: 0.2s; }}
                            .btn-down:hover {{ background-color: #212529; }}
                        </style>
                    </head>
                    <body>
                        <div id="capture-area" class="report-box">
                            <div class="header-title">
                                <h2>위드멤버 플레이스 최적화 시스템</h2>
                            </div>
                            
                            <div class="input-grid">
                                <div class="input-item"><label>매장명</label><div>{store}</div></div>
                                <div class="input-item"><label>지역</label><div>{reg}</div></div>
                                <div class="input-item"><label>메뉴</label><div>{men}</div></div>
                                <div class="input-item"><label>이벤트 (선택)</label><div>{display_event}</div></div>
                            </div>
                            
                            <div class="kw-container">
                                <div class="kw-box">
                                    <div class="box-title title-main">지역 메인 키워드 5개</div>
                                    <ul>{gold_li}</ul>
                                </div>
                                <div class="kw-box">
                                    <div class="box-title title-detail">메뉴 맞춤 상세 키워드 5개</div>
                                    <ul>{detail_li}</ul>
                                </div>
                            </div>
                            
                            <div class="intro-section">
                                <h3>최적화 소개글 (새소식)</h3>
                                <div class="intro-box">{intro_html}</div>
                            </div>
                        </div>
                        
                        <button class="btn-down" onclick="downloadImage()">리포트 화면 이미지로 다운로드</button>

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
                    </body>
                    </html>
                    """
                    
                    components.html(html_content, height=1000, scrolling=True)
                    
                    st.caption("텍스트 복사용 원본")
                    st.code(intro_res)
                    
                else: 
                    st.error(f"오류가 발생했습니다: {msg}")

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
                prompt = f"다음 손님의 리뷰에 대해 친절하고 감사해하는 사장님 톤으로 답글을 써줘. 친근한 이모티콘 듬뿍 써줘. [절대 금지] 글 마지막에 해시태그(#)를 달거나 키워드를 따로 나열하지 마세요. 오직 답글 본문만 작성하세요. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
