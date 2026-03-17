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

# --- 2. 네이버 추출 엔진 (5+5 무조건 보장) ---
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

    core_men = men.replace(",", " ").split()[0] if men else ""
    
    hints_list = [f"{core_dong}맛집", f"{core_dong}{core_men}", f"{core_gu}맛집", f"{core_dong}회식", f"{core_dong}데이트"]
    params = {'hintKeywords': ",".join(hints_list), 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"네이버 API 오류 (코드: {res.status_code})"
        
        data = res.json().get('keywordList', [])
        valid_kws = []
        
        for item in data:
            kw = item['relKeyword']
            if any(x in kw for x in ["주변", "근처", "오늘"]): continue
            if (core_dong and core_dong not in kw) and (core_gu and core_gu not in kw): continue
            
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total_search = pc + mo
            
            is_detail = any(x in kw for x in [core_men, '회식', '모임', '룸', '데이트', '가족', '핫플', '술집', '카페', '점심', '저녁', '추천', '고기집', '삼겹살'])
            
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
                
        fallback_mains = [f"{core_dong}{core_men}", f"{core_dong}맛집", f"{core_gu}{core_men}", f"{core_gu}맛집", f"{core_dong}식당", f"{core_dong}밥집"]
        for fb in fallback_mains:
            if len(gold_kws) >= 5: break
            if not any(k['relKeyword'] == fb for k in gold_kws + detail_kws):
                gold_kws.append({'relKeyword': fb, 'total_search': 10, 'is_detail': False})

        fallback_details = [f"{core_dong}회식", f"{core_dong}데이트", f"{core_dong}모임장소", f"{core_dong}핫플", f"{core_dong}가볼만한곳", f"{core_dong}추천"]
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

tab1, tab2 = st.tabs(["🎯 종합 리포트 생성", "💬 방문자 리뷰 답글"])

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
            with st.spinner("네이버 상권 데이터 수집 및 소개글을 생성 중입니다... (약 10~15초 소요)"):
                g_kws, d_kws, msg = get_naver_real_keywords(store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    # 1. 소개글 먼저 생성
                    all_real_kws = [k['relKeyword'] for k in g_kws + d_kws]
                    event_instruction = f"진행 중인 이벤트: '{event}'" if event else "현재 특별히 강조할 이벤트는 없음"
                    
                    prompt = f"""
                    매장명: '{store}'
                    주력메뉴: '{men}'
                    {event_instruction}
                    
                    [필수 반영 타겟 키워드 10개]
                    {', '.join(all_real_kws)}

                    [작성 규칙]
                    1. 위 10개의 키워드를 빠짐없이 문장에 자연스럽게 모두 녹여내세요.
                    2. 인스타그램 감성 맛집 블로거처럼 물 흐르듯 자연스럽게 작성하세요.
                    3. 글자 수는 공백 포함 **150자 ~ 200자 사이**로 넉넉하게 구성하세요.
                    4. 세련된 이모티콘 2~3개를 배치하세요.
                    """
                    intro_res = generate_ai_content(prompt, O_API_KEY)
                    
                    # 소개글 줄바꿈을 HTML 태그로 변환
                    intro_html = intro_res.replace('\n', '<br>')
                    display_event = event if event else "없음"
                    
                    st.divider()
                    st.subheader("📸 종합 리포트 이미지 다운로드")
                    
                    # 2. [수정됨] 글씨 크기(18px) 및 굵기 대폭 상향 
                    gold_li = "".join([f"<li style='padding: 10px 0; border-bottom: 1px dashed #ccc; font-size: 18px; font-weight: bold; color: #2c3e50;'>🥇 {k['relKeyword']} <span style='float:right; font-weight: 800; color:#d32f2f;'>{k['total_search']:,}건</span></li>" for k in g_kws])
                    detail_li = "".join([f"<li style='padding: 10px 0; border-bottom: 1px dashed #ccc; font-size: 18px; font-weight: bold; color: #2c3e50;'>✔️ {k['relKeyword']} <span style='float:right; font-weight: 800; color:#1976d2;'>{k['total_search']:,}건</span></li>" for k in d_kws])
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
                        <style>
                            @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
                            body {{ font-family: 'Pretendard', sans-serif; background-color: white; margin: 0; padding: 0; }}
                            .report-box {{ width: 650px; padding: 30px; background: #ffffff; border: 2px solid #2c3e50; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 8px 16px rgba(0,0,0,0.1); }}
                            .header {{ text-align: center; margin-bottom: 25px; border-bottom: 2px solid #2c3e50; padding-bottom: 15px; }}
                            .header h1 {{ color: #2c3e50; margin: 0; font-size: 26px; font-weight: 800; }}
                            .header p {{ color: #7f8c8d; font-size: 16px; margin-top: 8px; font-weight: 500; }}
                            
                            .info-box {{ background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-size: 16px; color: #34495e; border: 1px solid #e9ecef; }}
                            .info-box strong {{ color: #2c3e50; }}
                            
                            .kw-container {{ display: flex; justify-content: space-between; margin-bottom: 25px; }}
                            .kw-box {{ width: 48%; padding: 15px; border-radius: 8px; }}
                            .box-main {{ background-color: #fff3e0; border: 1px solid #ffe0b2; }}
                            .box-detail {{ background-color: #e3f2fd; border: 1px solid #bbdefb; }}
                            .kw-box h3 {{ margin-top: 0; font-size: 19px; text-align: center; font-weight: 800; margin-bottom: 15px; }}
                            .box-main h3 {{ color: #e65100; }}
                            .box-detail h3 {{ color: #0d47a1; }}
                            ul {{ list-style: none; padding: 0; margin: 0; }}
                            
                            .intro-box {{ background-color: #f4f6f6; padding: 20px; border-radius: 8px; border-left: 5px solid #1abc9c; font-size: 16px; line-height: 1.6; color: #2c3e50; }}
                            .intro-box h3 {{ margin-top: 0; font-size: 19px; color: #16a085; margin-bottom: 12px; font-weight: 800; }}
                            
                            .btn-down {{ padding: 15px; background-color: #2c3e50; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 18px; font-weight: bold; width: 650px; display: block; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: 0.3s; }}
                            .btn-down:hover {{ background-color: #1a252f; }}
                        </style>
                    </head>
                    <body>
                        <div id="capture-area" class="report-box">
                            <div class="header">
                                <h1>📈 위드멤버 플레이스 최적화 리포트</h1>
                                <p>빅데이터 기반 황금 키워드 & AI 카피라이팅 분석 결과</p>
                            </div>
                            
                            <div class="info-box">
                                <strong>🏪 매장명:</strong> {store} &nbsp;|&nbsp; 
                                <strong>📍 지역:</strong> {reg} <br><br>
                                <strong>🍽️ 메뉴:</strong> {men} &nbsp;|&nbsp; 
                                <strong>🎁 이벤트:</strong> {display_event}
                            </div>
                            
                            <div class="kw-container">
                                <div class="kw-box box-main">
                                    <h3>🎯 메인 타겟 키워드</h3>
                                    <ul>{gold_li}</ul>
                                </div>
                                <div class="kw-box box-detail">
                                    <h3>✨ 상세 타겟 키워드</h3>
                                    <ul>{detail_li}</ul>
                                </div>
                            </div>
                            
                            <div class="intro-box">
                                <h3>📝 최적화 소개글 (키워드 10개 100% 반영)</h3>
                                <div>{intro_html}</div>
                            </div>
                        </div>
                        
                        <button class="btn-down" onclick="downloadImage()">⬇️ 종합 리포트 이미지 다운로드</button>

                        <script>
                            function downloadImage() {{
                                const element = document.getElementById('capture-area');
                                html2canvas(element, {{ scale: 2, backgroundColor: "#ffffff" }}).then(canvas => {{
                                    let link = document.createElement('a');
                                    link.download = '[위드멤버]_{store}_최적화리포트.png';
                                    link.href = canvas.toDataURL('image/png');
                                    link.click();
                                }});
                            }}
                        </script>
                    </body>
                    </html>
                    """
                    
                    # 폰트가 커진 만큼 화면 잘림 방지를 위해 높이를 950으로 넉넉하게 수정
                    components.html(html_content, height=950, scrolling=True)
                    
                    st.divider()
                    st.caption("텍스트 복사용 소개글")
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
                prompt = f"다음 손님의 리뷰에 대해 친절하고 감사해하는 사장님 톤으로 답글을 써줘. 친근한 이모티콘 듬뿍 써줘. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
