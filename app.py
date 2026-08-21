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

def parse_qc_cnt(val):
    if isinstance(val, str):
        val = val.replace('< ', '').replace('<', '').replace(',', '').strip()
        try:
            return int(val)
        except:
            return 10  # 네이버 API의 '< 10' 처리
    return int(val) if val else 0

# --- 2. 네이버 지역 기반 키워드 추출 ENGINE ---
def get_naver_target_keywords(target_kw_str, store, reg, men, c_id, a_key, s_key):
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
    
    # 지역명 파싱 (예: "경남", "창원시", "마산합포구", "해운동")
    reg_parts = [p.strip() for p in reg.strip().split()]
    loc_dong = reg_parts[-1] if reg_parts else reg
    loc_city = reg_parts[-2] if len(reg_parts) > 1 else loc_dong
    
    # 필터링을 위한 핵심 지역 키워드 추출 (시, 구, 동 단위 제거)
    valid_locs = [p.replace("시","").replace("군","").replace("구","").replace("동","").replace("읍","").replace("면","") for p in reg_parts]
    valid_locs = [v for v in valid_locs if len(v) >= 1]
    
    core_men = men.split(",")[0].strip() if men else ""
    has_target = bool(target_kw_str and target_kw_str.strip())
    
    # 메인 타겟 리스트 결정
    if has_target:
        # 입력한 타겟 키워드가 있으면 중복 제거 후 그대로 사용
        raw_list = [k.strip() for k in target_kw_str.split(",") if k.strip()]
        target_list = list(dict.fromkeys(raw_list)) 
    else:
        # 타겟 키워드가 없으면, 지역+메뉴 조합으로 억지 키워드(생닭 등) 원천 차단
        target_list = [
            f"{loc_dong} 맛집",
            f"{loc_dong} {core_men}",
            f"{loc_city} 맛집",
            f"{loc_dong} 가볼만한곳",
            f"{loc_dong} 술집" if "술" in men or "안주" in men else f"{loc_dong} 핫플"
        ]

    # API 호출용 힌트 키워드 (띄어쓰기 제거)
    hint_kws_param = ",".join([k.replace(" ", "") for k in target_list[:5]])
    params = {'hintKeywords': hint_kws_param, 'showDetail': 1}
    
    main_kws = []
    detail_kws = []
    seen_kws = set()
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        api_data = res.json().get('keywordList', []) if res.status_code == 200 else []
        
        # 1) 메인 키워드 처리: target_list에 있는 것만 정확히 매칭 (사용자가 2개 넣으면 2개만 노출)
        for t_kw in target_list:
            t_kw_clean = t_kw.replace(" ", "")
            found = next((item for item in api_data if item['relKeyword'].replace(" ", "") == t_kw_clean), None)
            
            if found:
                tot = parse_qc_cnt(found.get('monthlyPcQcCnt')) + parse_qc_cnt(found.get('monthlyMobileQcCnt'))
                main_kws.append({'relKeyword': t_kw, 'total_search': tot})
            else:
                main_kws.append({'relKeyword': t_kw, 'total_search': 10}) # 조회수 10 미만 처리
            seen_kws.add(t_kw_clean)
            
        # 2) 상세 연관 키워드 처리: 도매/재료 키워드 차단 및 지역명 포함 여부 강력 필터링
        for item in api_data:
            if len(detail_kws) >= 5: break
            kw = item['relKeyword']
            kw_clean = kw.replace(" ", "")
            
            if kw_clean in seen_kws:
                continue
                
            # 해당 키워드에 입력된 지역명(창원, 마산, 해운 등)이 하나라도 포함되어 있는지 확인
            is_local = any(v in kw for v in valid_locs)
            
            # 타겟이 없었을 경우 철저히 지역 키워드만, 타겟이 있었을 경우 연관성 기반
            if is_local or has_target: 
                tot = parse_qc_cnt(item.get('monthlyPcQcCnt')) + parse_qc_cnt(item.get('monthlyMobileQcCnt'))
                detail_kws.append({'relKeyword': kw, 'total_search': tot})
                seen_kws.add(kw_clean)

        # 상세 키워드가 부족할 경우 안전한 지역 기반 조합으로 채움
        if len(detail_kws) < 5:
            fb_list = [f"{loc_dong} 모임", f"{loc_city} 핫플", f"{loc_dong} 데이트", f"{loc_city} 가볼만한곳", f"{loc_dong} 추천"]
            for fb in fb_list:
                if len(detail_kws) >= 5: break
                fb_clean = fb.replace(" ", "")
                if fb_clean not in seen_kws:
                    detail_kws.append({'relKeyword': fb, 'total_search': 10})
                    seen_kws.add(fb_clean)

        return main_kws, detail_kws, "success"

    except Exception as e:
        return [{'relKeyword': f"{loc_dong} {core_men}", 'total_search': 0}], [], f"API 통신 오류: {str(e)}"

# --- 3. OpenAI 카피라이팅 함수 ---
def generate_ai_content(prompt, api_key, system_role="", temp=0.7):
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
st.set_page_config(page_title="플레이스 최적화", layout="wide")

with st.sidebar:
    st.title("API 설정")
    if not (N_API_KEY and N_SECRET_KEY and O_API_KEY):
        st.warning("Secrets를 설정하거나 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드")

st.header("플레이스 최적화 시스템")

tab1, tab2 = st.tabs(["키워드 & 새소식 문구", "방문자 리뷰 답글"])

with tab1:
    with st.form("intro_form"):
        r1_c1, r1_c2, r1_c3 = st.columns(3)
        with r1_c1: store = st.text_input("매장명", placeholder="하단끝집 마산경남대점")
        with r1_c2: reg = st.text_input("지역 (시/구/동 모두 입력)", placeholder="경남 창원시 마산합포구 해운동")
        with r1_c3: men = st.text_input("메뉴/업종", placeholder="닭다리살, 술집, 안주맛집")
        
        r2_c1, r2_c2, r2_c3 = st.columns(3)
        with r2_c1: target_kws = st.text_input("타겟 키워드 (선택 입력, 쉼표 구분)", placeholder="창원 술집, 해운동 술집")
        with r2_c2: merit = st.text_input("매장만의 자랑거리 (선택)", placeholder="불향 가득한 닭다리살과 레트로 감성의 분위기")
        with r2_c3: event = st.text_input("이벤트 (선택)", placeholder="방문자 리뷰 작성 시 하이볼 1잔 서비스")
            
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 메뉴/업종은 필수 입력 항목입니다!")
        else:
            with st.spinner("지역 기반 정확도 높은 키워드 검색 및 문구 작성 중..."):
                g_kws, d_kws, msg = get_naver_target_keywords(target_kws, store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    has_event = bool(event and event.strip())
                    has_merit = bool(merit and merit.strip())
                    
                    # 새소식 문구에 강제 적용할 키워드들 (타겟 키워드 1:1 매칭)
                    used_targets = ", ".join([k['relKeyword'] for k in g_kws])
                    
                    system_role = f"""당신은 '{store}'을 직접 운영하는 센스 있는 사장님입니다.
로봇 같은 어투를 절대 쓰지 마세요.
문단마다 어울리는 친근한 이모티콘(✨, 😋, 🍻, 🔥, ❤️, 👍 등)을 듬뿍 사용하여 보기 좋게 작성하세요.
각 문단 사이에는 엔터 두 번(\\n\\n)을 넣어 가독성을 높이세요."""

                    prompt = f"""
[매장 정보]
- 매장명: '{store}'
- 지역: '{reg}'
- 대표 메뉴: '{men}'
- 매장 자랑거리: '{merit if has_merit else "정성껏 준비한 음식과 편안하고 즐거운 분위기"}'
- 진행 이벤트: '{event if has_event else "없음"}'

[SEO 최적화 필수 조건 (매우 중요)]
- **적용할 타겟 키워드**: {used_targets}
- 위 타겟 키워드들을 새소식 본문 안의 문맥에 자연스럽게 모두 한 번 이상씩 포함시켜서 작성하세요. 이는 플레이스 상위 노출에 매우 중요합니다.

[작성 가이드라인]
1. [제목]과 [본문] 형식으로 출력하세요.
2. [제목]: 시선을 사로잡는 매력적인 제목 (이모티콘 포함)
3. [본문 분량]: 공백 포함 500자 ~ 800자 사이
4. [본문 구성 - 4개 문단 필수]:
   - 1문단: 손님들께 보내는 따뜻한 안부 인사와 매장 소개 💛 (2~3문장)
   - 2문단: 대표 메뉴와 자랑거리를 침샘 자극하게 입체적으로 어필 🔥 (4~5문장 이상)
   - 3문단: {'이벤트 소식을 안내하며 방문 독려' if has_event else '편안하게 힐링할 수 있는 공간임을 어필'} ✨ (3~4문장)
   - 4문단: 진심 어린 사장님의 맺음말과 초대 인사 👏 (2~3문장)
5. 절대 주의사항: 부정적이거나 소극적인 표현(비록 이벤트는 없지만 등) 절대 금지, 해시태그(#) 절대 금지.
"""
                    
                    intro_res = generate_ai_content(prompt, O_API_KEY, system_role=system_role)
                    
                    if "[제목]" in intro_res and "[본문]" in intro_res:
                        parts = intro_res.split("[본문]")
                        title_part = parts[0].replace("[제목]", "").strip()
                        body_part = parts[1].strip()
                        body_html = body_part.replace('\n\n', '<br><br>').replace('\n', '<br>')
                        intro_html = f"<h4 style='color: #007bff; margin-top: 0; margin-bottom: 15px; font-size: 18px;'>{title_part}</h4><div style='border-top: 1px dashed #dee2e6; margin-bottom: 15px;'></div><div style='line-height: 1.8; font-size: 15px;'>{body_html}</div>"
                    else:
                        intro_html = intro_res.replace('\n\n', '<br><br>').replace('\n', '<br>')

                    display_event = event if event else "없음"
                    display_merit = merit if merit else "없음"
                    display_target = target_kws if target_kws else "네이버 자동 추출"
                    
                    st.divider()
                    
                    box_title_left = "타겟 키워드 월간 검색량" if target_kws else "네이버 대표 키워드 검색량"
                    
                    # 💡 실제 입력된 갯수(혹은 추출된 갯수)만큼만 깔끔하게 렌더링
                    gold_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 15px; font-weight: 700; color: #212529;'>🎯 {k['relKeyword']}</span> <span style='font-size: 14px; font-weight: 700; color: #007bff;'>(월 검색량: {k['total_search']:,}건)</span></li>" for k in g_kws])
                    detail_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 15px; font-weight: 700; color: #212529;'>✨ {k['relKeyword']}</span> <span style='font-size: 14px; font-weight: 600; color: #666;'>(월 검색량: {k['total_search']:,}건)</span></li>" for k in d_kws])
                    
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
                            .header-title h2 {{ color: #212529; font-size: 24px; margin: 0; font-weight: 800; }}
                            
                            .input-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 25px; }}
                            .input-item label {{ display: block; font-size: 12px; font-weight: 600; color: #666; margin-bottom: 4px; }}
                            .input-item div {{ background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 8px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; color: #212529; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                            
                            .kw-container {{ display: flex; justify-content: space-between; gap: 20px; margin-bottom: 25px; }}
                            .kw-box {{ flex: 1; align-self: flex-start; }}
                            .box-title {{ padding: 10px 12px; border-radius: 6px; font-size: 15px; font-weight: bold; margin-bottom: 10px; text-align: center; }}
                            .title-main {{ background-color: #e7f1ff; border: 1px solid #b6d4fe; color: #084298; }}
                            .title-detail {{ background-color: #f8f9fa; border: 1px solid #dee2e6; color: #212529; }}
                            ul {{ list-style: none; padding: 0; margin: 0; }}
                            
                            .intro-section h3 {{ font-size: 18px; color: #212529; margin-bottom: 10px; font-weight: 800; }}
                            .intro-box {{ background-color: #f8f9fa; padding: 22px; border-radius: 8px; border: 1px solid #dee2e6; color: #212529; }}
                            
                            .btn-down {{ margin-top: 20px; padding: 14px; background-color: #343a40; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; max-width: 800px; text-align: center; transition: 0.2s; }}
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
                                <div class="input-item"><label>메뉴/업종</label><div>{men}</div></div>
                                <div class="input-item"><label>타겟 키워드</label><div>{display_target}</div></div>
                                <div class="input-item"><label>자랑거리</label><div>{display_merit}</div></div>
                                <div class="input-item"><label>이벤트</label><div>{display_event}</div></div>
                            </div>
                            
                            <div class="kw-container">
                                <div class="kw-box">
                                    <div class="box-title title-main">{box_title_left}</div>
                                    <ul>{gold_li}</ul>
                                </div>
                                <div class="kw-box">
                                    <div class="box-title title-detail">추천 연관 상세 키워드</div>
                                    <ul>{detail_li}</ul>
                                </div>
                            </div>
                            
                            <div class="intro-section">
                                <h3>최적화 새소식 문구 (500자~800자)</h3>
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
                    
                    components.html(html_content, height=1050, scrolling=True)
                    
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
                prompt = f"다음 손님의 리뷰에 대해 친절하고 감사해하는 사장님 톤으로 답글을 작성해 주세요. [필수 조건] 단답형을 피하고 반드시 정중한 '존댓말'을 사용하여 작성하세요. 친근한 이모티콘 듬뿍 써주세요. [절대 금지] 글 마지막에 해시태그(#)를 달거나 키워드를 따로 나열하지 마세요. 오직 답글 본문만 작성하세요. 리뷰내용: {review_content}"
                review_res = generate_ai_content(prompt, O_API_KEY)
                st.success("작성된 답글:")
                st.write(review_res)
                st.code(review_res)
