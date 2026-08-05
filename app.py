import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import datetime

# 페이지 기본 설정
st.set_page_config(page_title="위드멤버 자동화 리포트 시스템", layout="wide")

# 사이드바 설정 (API 키 및 기본 정보)
st.sidebar.title("시스템 설정")
st.sidebar.write("API Key 관리")
naver_api = st.sidebar.text_input("Naver Search Ads API Key", type="password")
openai_api = st.sidebar.text_input("OpenAI API Key", type="password")
gemini_api = st.sidebar.text_input("Gemini API Key", type="password")

st.title("위드멤버 종합 마케팅 리포트 툴")
st.markdown("**1년 계약 (99만원) / 3개월 매출 보장제 클라이언트 관리 및 리포트 화면**")

# 탭 구성 (위드멤버 주요 서비스)
tab1, tab2, tab3 = st.tabs(["네이버 플레이스 SEO", "블로그 리뷰 검수", "숏폼 영상(릴스/쇼츠)"])

with tab1:
    st.header("네이버 플레이스 SEO 최적화")
    st.write("키워드 순위 및 트래픽 현황")
    df = pd.DataFrame({
        "키워드": ["강남 맛집", "강남역 카페", "서초구 회식"],
        "현재 순위": [3, 1, 5],
        "검색량": [15000, 22000, 8000]
    })
    st.dataframe(df, use_container_width=True)

with tab2:
    st.header("블로그 리뷰 추천 및 검수 리포트")
    st.write("업체에 맞는 최적화 블로그 후보 검수 현황")

with tab3:
    st.header("영상 콘텐츠 제작 및 배포")
    st.write("캡컷(CapCut) 편집 영상 인스타그램 릴스 / 유튜브 쇼츠 배포 내역")

st.divider()

# 리포트 캡처 영역
st.header("📈 클라이언트 전송용 리포트 캡처")
st.write("아래 버튼을 클릭하면 회색 테두리 안의 영역이 이미지로 저장됩니다.")

# HTML로 캡처될 대상(capture-area) 구성
report_html = f'''
<div id="capture-area" style="padding: 40px; background-color: white; border: 1px solid #ccc; border-radius: 8px;">
    <h2 style="color: #2c3e50; margin-bottom: 5px;">위드멤버 월간 마케팅 성과 리포트</h2>
    <p style="margin-top: 0; color: #555;"><strong>발행일:</strong> {datetime.date.today().strftime("%Y-%m-%d")}</p>
    <hr style="border: 1px solid #eee;">
    <h3>1. 네이버 플레이스 세팅 및 관리 (SEO최적화)</h3>
    <p>주요 키워드 상위 노출 및 유입량 증가 확인</p>
    <h3>2. 최적화 블로그 리뷰 배포</h3>
    <p>타겟 키워드 기반 블로그 리뷰 배포 완료 및 노출 최적화</p>
    <h3>3. 영상 콘텐츠 인게이지먼트</h3>
    <p>인스타그램 릴스 및 유튜브 쇼츠 통합 배포 완료</p>
    <br><br>
    <p style="text-align: right; color: gray; font-size: 18px;"><strong>위드멤버 이명욱 대표</strong></p>
</div>
'''
st.markdown(report_html, unsafe_allow_html=True)

# ---------------------------------------------------------
# [오류 해결 부분] 376번 줄에서 발생했던 문법 에러 수정 코드
# 파이썬 안에서 자바스크립트가 동작하도록 components.html 사용
# ---------------------------------------------------------
js_code = """
<div style="margin-top: 15px;">
    <button id="capture-btn" style="padding: 10px 20px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;">
        📸 리포트 캡처 및 이미지 다운로드
    </button>
</div>

<!-- html2canvas 라이브러리 로드 -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script>
    document.getElementById('capture-btn').addEventListener('click', function() {
        // Streamlit은 iframe 내부에서 실행되므로 window.parent.document로 접근해야 합니다.
        const element = window.parent.document.getElementById('capture-area');
        
        if(element) {
            html2canvas(element, { scale: 2 }).then(function(canvas) {
                const link = document.createElement('a');
                link.download = 'withmember_report.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            });
        } else {
            alert("캡처할 리포트 영역('capture-area')을 찾을 수 없습니다.");
        }
    });
</script>
"""
components.html(js_code, height=100)
