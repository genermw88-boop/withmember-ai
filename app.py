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

# --- 2. 네이버 추출 엔진 (엉뚱한 메뉴 차단 강화) ---
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
    core_city = ""
    core_gu = ""
    core_dong = ""
    
    if reg_parts:
        if len(reg_parts[0]) >= 2:
            core_city = reg_parts[0][:2] 
            
    for p in reg_parts:
        if p.endswith('구') or p.endswith('시') or p.endswith('군'): core_gu = p
        elif any(p.endswith(s) for s in ['동', '역', '읍', '면', '리']): core_dong = p
    
    if not core_gu and not core_dong and reg_parts:
        core_dong = reg_parts[-1]

    core_men_list = men.replace(",", " ").split()
    core_men = core_men_list[0] if core_men_list else ""
    
    hints_list = [f"{core_dong}맛집", f"{core_gu}맛집", f"{core_dong}{core_men}", f"{core_dong}데이트", f"{core_dong}가볼만한곳"]
    params = {'hintKeywords': ",".join(hints_list), 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"네이버 API 오류 (코드: {res.status_code})"
        
        data = res.json().get('keywordList', [])
        valid_kws = []
        
        korea_cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
        
        # 🚨 [새로운 핵심 필터] 타 업종 메뉴 블랙리스트
        stop_foods = ['삼겹살', '돼지갈비', '김치찌개', '횟집', '회', '국밥', '마라탕', '치킨', '피자', '중국집', '짜장면', '짬뽕', '초밥', '스시', '떡볶이', '한정식', '백반', '칼국수', '냉면', '족발', '보쌈', '곱창', '막창', '닭갈비', '고기집', '소고기', '한우', '돈까스', '파스타', '스테이크', '브런치', '카페', '디저트']
        
        # 입력한 메뉴와 관련된 단어는 블랙리스트에서 제외 (살려둠)
        blacklist = []
        for sf in stop_foods:
            is_safe = False
            for m in core_men_list:
                if m in sf or sf in m:  # 예: 입력이 '삼겹'이면 '삼겹살'은 허용
                    is_safe = True
                    break
            if not is_safe:
                blacklist.append(sf)
                
        for item in data:
            kw = item['relKeyword']
            if any(x in kw for x in ["주변", "근처", "오늘", "배달"]): continue
            
            # 지역 충돌 방지
            conflict = False
            if core_city in korea_cities:
                for city in korea_cities:
                    if city != core_city and city in kw:
                        conflict = True
                        break
            if conflict: continue
            
            # 타지역 차단
            if (core_dong and core_dong not in kw) and (core_gu and core_gu not in kw): continue
            
            # 🚨 엉뚱한 메뉴(횟집, 삼겹살 등) 완벽 차단
            if any(b in kw for b in blacklist): continue
            
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total_search = pc + mo
            
            is_detail = any(x in kw for x in core_men_list + ['회식', '모임', '룸', '데이트', '가족', '핫플', '술집', '카페', '점심', '저녁', '추천', '분위기'])
            
            item['total_search'] = total_search
            item['is_detail'] = is_detail
            valid_kws.append(item)
                
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
                
        # 대체 생성 키워드도 입력된 메뉴 기반으로만 생성
        fallback_mains = [f"{core_dong}맛집", f"{core_dong}{core_men}", f"{core_gu}맛집", f"{core_gu}{core_men}", f"{core_dong}식당"]
        for fb in fallback_mains:
            if len(gold_kws) >= 5: break
            if not any(k['relKeyword'] == fb for k in gold_kws + detail_kws):
                gold_kws.append({'relKeyword': fb, 'total_search': 10, 'is_detail': False})

        fallback_details = [f"{core_dong}데이트", f"{core_dong}모임장소", f"{core_dong}핫플", f"{core_dong}분위기", f"{core_dong}추천"]
        for fb in fallback_details:
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

# --- 4. Streamlit UI ---
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
        with c1: store = st.text_input("매장명", placeholder="로얄경양식&스테이크")
        with c2: reg = st.text_input("지역", placeholder="부산 수영구 민락동")
        with c3: men = st.text_input("메뉴", placeholder="스테이크 돈까스 파스타")
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
                    
                    gold_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 15px; font-weight: 700; color: #333;'>• {k['relKeyword']}</span> <span style='font-size: 15px; color:#555;'>(검색량: <strong>{k['total_search']:,}건</strong>)</span></li>" for k in g_kws])
                    detail_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 15px; font-weight: 700; color: #333;'>- {k['relKeyword']}</span> <span style='font-size: 15px; color:#555;'>(검색량: <strong>{k['total_search']:,}건</strong>)</span></li>" for k in d_kws])
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
                        <style>
                            @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
                            body {{ font-family: 'Pretendard', sans-serif; background-color: #ffffff; margin: 0; padding: 0; }}
                            .report-box {{ width: 100%; max-width: 800px; padding: 20px; background: #ffffff; box-sizing: border-box; }}
                            
                            .header-title {{ border-bottom: 1px solid #ddd; padding-bottom: 15px; margin-bottom: 20px; }}
                            .header-title h2 {{ color: #212529; font-size: 24px; margin: 0; display: flex; align-items: center; gap: 8px; }}
                            
                            .input-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }}
                            .input-item label {{ display: block; font-size: 12px; color: #666; margin-bottom: 5px; }}
                            .input-item div {{ background-color: #f8f9fa; border: 1px solid #eee; padding: 10px; border-radius: 6px; font-size: 14px; color: #333; }}
                            
                            .kw-container {{ display: flex; justify-content: space-between; gap: 20px; margin-bottom: 30px; }}
                            .kw-box {{ flex: 1; }}
                            .box-title {{ padding: 12px 15px; border-radius: 6px; font-size: 15px; font-weight: bold; margin-bottom: 15px; }}
                            .title-main {{ background-color: #f8f9fa; border: 1px solid #ddd; color: #333; }}
                            .title-detail {{ background-color: #f8f9fa; border: 1px solid #ddd; color: #333; }}
                            ul {{ list-style: none; padding: 0; margin: 0; }}
                            
                            .intro-section h3 {{ font-size: 20px; color: #212529; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }}
                            .intro-box {{ background-color: #f8f9fa; padding: 20px; border-radius: 8px; border: 1px solid #ddd; font-size: 15px; line-height: 1.6; color: #333; }}
                            
                            .btn-down {{ margin-top: 20px; padding: 15px; background-color: #495057; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; max-width: 800px; text-align: center; transition: 0.2s; }}
                            .btn-down:hover {{ background-color: #343a40; }}
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
                    
                    components.html(html_content, height=900, scrolling=True)
                    
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
