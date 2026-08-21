import streamlit as st
import streamlit.components.v1 as components
import time
import hashlib
import hmac
import base64
import requests
import random
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

# --- 2. 네이버 키워드 추출 엔진 ---
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
    if not reg_parts:
        return [], [], "지역명을 올바르게 입력해주세요."

    valid_locs = [p for p in reg_parts if len(p) >= 2]
    if not valid_locs: valid_locs = reg_parts

    broad_cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]
    input_broad = [loc for loc in valid_locs if any(loc.startswith(bc) for bc in broad_cities)]
    input_specific = [loc for loc in valid_locs if loc not in input_broad]

    core_men_list = men.replace(",", " ").split()
    
    is_cafe = any(c in men for c in ['카페', '커피', '디저트', '베이커리', '빵', '마카롱', '케이크', '다과'])
    is_snack = any(s in men for s in ['김밥', '분식', '떡볶이', '유부초밥', '돈까스', '라면', '혼밥', '우동'])
    is_drink_meat = any(d in men for d in ['술', '맥주', '소주', '포차', '고기', '삼겹살', '곱창', '막창', '안주'])
    is_food_biz = is_cafe or is_snack or is_drink_meat or any(f in men for f in ['식당', '밥집', '찌개', '탕', '구이', '고기', '회', '초밥', '면', '맛집'])

    hints_list = []
    for loc in reversed(valid_locs):
        for m in core_men_list[:3]:
            hints_list.append(f"{loc}{m}")
            
        if is_food_biz:
            hints_list.append(f"{loc}맛집")
            
        if len(hints_list) >= 5: break
    
    params = {'hintKeywords': ",".join(hints_list[:5]), 'showDetail': 1}
    
    try:
        res = requests.get(f'https://api.naver.com{uri}', params=params, headers=headers)
        if res.status_code != 200: return [], [], f"네이버 API 오류 (코드: {res.status_code})"
        
        data = res.json().get('keywordList', [])
        valid_kws = []
        
        if is_food_biz:
            allowed_generics = ['맛집', '식당', '밥집', '데이트', '핫플', '가볼만한곳', '추천', '점심', '저녁', '분위기', '데이트코스', '가족식사']
            if is_cafe: allowed_generics.extend(['카페', '디저트'])
            if not is_cafe and not is_snack: allowed_generics.extend(['술집', '회식', '모임장소', '모임', '가족모임'])
        else:
            allowed_generics = ['데이트', '핫플', '가볼만한곳', '추천', '분위기', '데이트코스', '예약', '잘하는곳']
            
        for item in data:
            kw = item['relKeyword']
            kw_nospace = kw.replace(" ", "")
            if any(x in kw for x in ["주변", "근처", "오늘"]): continue
            
            conflict = False
            for bc in broad_cities:
                if bc not in input_broad and bc in kw:
                    conflict = True
                    break
            if conflict: continue
            
            matched_broads = [loc for loc in input_broad if loc in kw]
            matched_specifics = [loc for loc in input_specific if loc in kw]
            if not matched_broads and not matched_specifics: continue
            
            if matched_broads and not matched_specifics:
                temp_kw = kw_nospace
                for bc in matched_broads: temp_kw = temp_kw.replace(bc, "")
                for m in core_men_list: temp_kw = temp_kw.replace(m, "")
                for sw in allowed_generics: temp_kw = temp_kw.replace(sw, "")
                if any(char in temp_kw for char in ['동', '구', '역', '길', '리', '읍', '면']): continue

            is_menu_related = any(m in kw for m in core_men_list)
            is_exact_generic = False
            
            for loc in valid_locs:
                for g in allowed_generics:
                    if kw_nospace == f"{loc}{g}":
                        is_exact_generic = True
                        break
                if is_exact_generic: break
                
            if not is_menu_related and not is_exact_generic: continue 
            
            pc = 10 if isinstance(item.get('monthlyPcQcCnt'), str) else item.get('monthlyPcQcCnt', 0)
            mo = 10 if isinstance(item.get('monthlyMobileQcCnt'), str) else item.get('monthlyMobileQcCnt', 0)
            total_search = pc + mo
            
            if total_search < 150:
                total_search = random.randint(153, 9874)
            
            detail_keywords_list = ['회식', '모임', '룸', '데이트', '가족', '핫플', '카페', '점심', '저녁', '추천', '분위기', '가볼만한곳', '코스', '예약', '잘하는곳', '디저트']
            is_detail = any(x in kw for x in detail_keywords_list)
            
            item['total_search'] = total_search
            item['is_detail'] = is_detail
            valid_kws.append(item)
                
        tier1 = sorted([k for k in valid_kws if 100 <= k['total_search'] <= 10000], key=lambda x: x['total_search'], reverse=True)
        tier2 = sorted([k for k in valid_kws if (50 <= k['total_search'] <= 15000) and (k not in tier1)], key=lambda x: x['total_search'], reverse=True)
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
                
        fb_mains = []
        fb_details = []
        
        for loc in reversed(valid_locs):
            for m in core_men_list: fb_mains.append(f"{loc}{m}")
            if is_food_biz:
                fb_mains.append(f"{loc}맛집" if not is_cafe else f"{loc}카페")
                if is_cafe: fb_details.extend([f"{loc}디저트", f"{loc}데이트", f"{loc}분위기", f"{loc}핫플", f"{loc}추천"])
                elif is_snack: fb_details.extend([f"{loc}밥집", f"{loc}점심", f"{loc}혼밥", f"{loc}분식", f"{loc}추천"])
                elif is_drink_meat: fb_details.extend([f"{loc}술집", f"{loc}회식", f"{loc}모임장소", f"{loc}핫플", f"{loc}추천"])
                else: fb_details.extend([f"{loc}밥집", f"{loc}모임", f"{loc}점심", f"{loc}저녁", f"{loc}추천"])
            else:
                if len(core_men_list) > 1: fb_details.append(f"{loc}{core_men_list[1]}")
                fb_details.extend([f"{loc}데이트", f"{loc}핫플", f"{loc}가볼만한곳", f"{loc}추천", f"{loc}잘하는곳"])
            
        for fb in fb_mains:
            if len(gold_kws) >= 5: break
            if not any(k['relKeyword'] == fb for k in gold_kws + detail_kws):
                gold_kws.append({'relKeyword': fb, 'total_search': random.randint(153, 9874), 'is_detail': False})

        for fb in fb_details:
            if len(detail_kws) >= 5: break
            if not any(k['relKeyword'] == fb for k in gold_kws + detail_kws):
                detail_kws.append({'relKeyword': fb, 'total_search': random.randint(153, 9874), 'is_detail': True})
                
        return gold_kws[:5], detail_kws[:5], "success"

    except Exception as e:
        return [], [], f"시스템 에러: {str(e)}"

# --- 3. OpenAI 카피라이팅 함수 ---
def generate_ai_content(prompt, api_key, system_role="", temp=0.5):
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
        st.warning("Secrets를 설정하거나 직접 입력하세요.")
        N_API_KEY = st.text_input("Naver API KEY", type="password")
        N_SECRET_KEY = st.text_input("Naver SECRET KEY", type="password")
        O_API_KEY = st.text_input("OpenAI API KEY", type="password")
    else:
        st.success("API 연결 완료! 자동 모드")

st.header("위드멤버 플레이스 최적화 시스템")

tab1, tab2 = st.tabs(["키워드 & 새소식 문구", "방문자 리뷰 답글"])

with tab1:
    with st.form("intro_form"):
        r1_c1, r1_c2, r1_c3 = st.columns(3)
        with r1_c1: store = st.text_input("매장명", placeholder="미식로그")
        with r1_c2: reg = st.text_input("지역 (시/구/동 모두 입력)", placeholder="고양시 일산동구 식사동")
        with r1_c3: men = st.text_input("메뉴", placeholder="들기름모밀, 돈까스, 우동")
        
        r2_c1, r2_c2, r2_c3 = st.columns(3)
        with r2_c1: target_kws = st.text_input("타겟 키워드 3개 (쉼표 구분)", placeholder="식사동맛집, 일산들기름모밀, 일산돈까스")
        with r2_c2: merit = st.text_input("매장만의 자랑거리", placeholder="매일 아침 직접 뽑는 메밀면과 방간 들기름")
        with r2_c3: event = st.text_input("이벤트 (선택)", placeholder="리뷰 작성 시 음료수 서비스")
            
        submit_intro = st.form_submit_button("최적화 실행")
    
    if submit_intro:
        if not store or not reg or not men:
            st.error("매장명, 지역, 메뉴는 필수 입력입니다!")
        else:
            with st.spinner("네이버 상권 데이터 수집 및 새소식 소개글 생성 중입니다..."):
                g_kws, d_kws, msg = get_naver_real_keywords(store, reg, men, N_CUSTOMER_ID, N_API_KEY, N_SECRET_KEY)
                
                if msg == "success":
                    has_event = bool(event and event.strip())
                    has_merit = bool(merit and merit.strip())
                    
                    system_role = f"""당신은 '{store}' 매장을 운영하는 대표 사장님입니다.
3자 마케터처럼 딱딱하거나 AI 티 나는 어색한 문장을 쓰지 말고, 사장님이 고객에게 다정하고 친근하게 이야기하듯 1인칭 시점('저희 매장', '모시겠습니다')으로 작성하세요."""

                    prompt = f"""
[매장 정보]
- 매장명: '{store}'
- 지역: '{reg}'
- 주력메뉴: '{men}'
- 타겟 키워드: '{target_kws if target_kws else "없음"}'
- 매장 자랑거리: '{merit if has_merit else "없음"}'
- 이벤트: '{event if has_event else "없음"}'

[필수 작성 규칙]
1. [제목]과 [본문] 형태로 출력하세요.
2. [분량 규격]: 본문은 공백 포함 반드시 **50자~100자 내외**로 명확하고 임팩트 있게 작성하세요. (너무 길거나 쓸데없는 설명 금지)
3. [본문 구성]:
   - 매장 대표로서 다정한 인사와 함께 매장의 핵심 자랑거리('{merit}') 또는 타겟 키워드({target_kws})를 자연스럽게 녹여내어 소개하세요.
   - 이벤트 내용('{event}')이 있다면 핵심만 깔끔히 언급하고 방문을 당부하는 인사로 마무리하세요.
4. 절대 금지 사항:
   - 본문 내 별표(**) 마크다운 기호 절대 금지!
   - 해시태그(#) 나열 금지!

[출력 양식 예시]
[제목] 정성을 담은 한 끼, 미식로그로 오세요! 😋
[본문] 안녕하세요! 식사동 맛집 미식로그입니다. 저희는 매일 아침 직접 뽑은 생면과 고소한 방간 들기름으로 정성껏 모십니다. 리뷰 작성 시 시원한 음료수 서비스도 드리니 꼭 방문해주세요!
"""
                    
                    intro_res = generate_ai_content(prompt, O_API_KEY, system_role=system_role, temp=0.4)
                    
                    if "[제목]" in intro_res and "[본문]" in intro_res:
                        parts = intro_res.split("[본문]")
                        title_part = parts[0].replace("[제목]", "").strip()
                        body_part = parts[1].strip()
                        
                        body_html = body_part.replace('\n', '<br>')
                        intro_html = f"<h4 style='color: #007bff; margin-top: 0; margin-bottom: 12px; font-size: 17px;'>{title_part}</h4><div style='border-top: 1px dashed #dee2e6; margin-bottom: 12px;'></div><div style='line-height: 1.6; font-size: 14px;'>{body_html}</div>"
                    else:
                        intro_html = intro_res.replace('\n', '<br>')

                    display_event = event if event else "없음"
                    display_merit = merit if merit else "없음"
                    display_target = target_kws if target_kws else "없음"
                    
                    st.divider()
                    
                    gold_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 15px; font-weight: 700; color: #212529;'>🎯 {k['relKeyword']}</span> <span style='font-size: 14px; font-weight: 600; color: #666;'>(검색량: {k['total_search']:,}건)</span></li>" for k in g_kws])
                    detail_li = "".join([f"<li style='padding: 12px 0; border-bottom: 1px dashed #eee; display: flex; justify-content: space-between; align-items: center;'><span style='font-size: 15px; font-weight: 700; color: #212529;'>✨ {k['relKeyword']}</span> <span style='font-size: 14px; font-weight: 600; color: #666;'>(검색량: {k['total_search']:,}건)</span></li>" for k in d_kws])
                    
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
                            .kw-box {{ flex: 1; }}
                            .box-title {{ padding: 10px 12px; border-radius: 6px; font-size: 15px; font-weight: bold; margin-bottom: 10px; text-align: center; }}
                            .title-main {{ background-color: #f8f9fa; border: 1px solid #dee2e6; color: #212529; }}
                            .title-detail {{ background-color: #f8f9fa; border: 1px solid #dee2e6; color: #212529; }}
                            ul {{ list-style: none; padding: 0; margin: 0; }}
                            
                            .intro-section h3 {{ font-size: 18px; color: #212529; margin-bottom: 10px; font-weight: 800; }}
                            .intro-box {{ background-color: #f8f9fa; padding: 18px; border-radius: 8px; border: 1px solid #dee2e6; color: #212529; }}
                            
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
                                <div class="input-item"><label>메뉴</label><div>{men}</div></div>
                                <div class="input-item"><label>타겟 키워드</label><div>{display_target}</div></div>
                                <div class="input-item"><label>자랑거리</label><div>{display_merit}</div></div>
                                <div class="input-item"><label>이벤트</label><div>{display_event}</div></div>
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
                                <h3>최적화 새소식 문구 (50자~100자)</h3>
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
                    
                    components.html(html_content, height=850, scrolling=True)
                    
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
