import streamlit as st
from google import genai

# 웹페이지 기본 설정
st.set_page_config(page_title="AI 마케팅 자동화 툴", page_icon="🚀", layout="centered")

# 위드멤버 맞춤형 메인 타이틀
st.title("🚀 위드멤버 AI 마케팅 자동화 툴")
st.markdown("소상공인 대표님들의 시간과 에너지를 아껴주는 마법의 도구입니다.")

# 🚨 [중요] 아래 빈칸에 대표님의 진짜 API 키를 넣어주세요! 
MY_API_KEY = "여기에_대표님의_API_키를_붙여넣으세요"

# API 클라이언트 및 모델 세팅 (자동 적용)
try:
    client = genai.Client(api_key=st.secrets["MY_API_KEY"])
except Exception as e:
    st.error("API 키가 올바르지 않습니다. 코드 안에 API 키를 정확히 넣었는지 확인해 주세요!")
    st.stop()

MODEL_ID = 'gemini-2.5-flash'

# 두 개의 탭으로 기능 분리
tab1, tab2 = st.tabs(["✍️ 리뷰 답글 생성기", "📰 플레이스 소식 자동 기획"])

# 1번 탭: 리뷰 답글 생성기
with tab1:
    st.subheader("1. AI 리뷰 답글 생성기")
    st.write("고객이 남긴 리뷰를 복사해서 아래에 붙여넣어 주세요.")
    
    review_text = st.text_area("고객 리뷰 텍스트:", height=150, placeholder="예: 비 오는 날 해물파전에 막걸리 먹었는데 진짜 바삭하고 맛있었어요!")
    
    if st.button("✨ 맞춤형 답글 생성하기", type="primary"):
        if review_text:
            with st.spinner("사장님의 정성을 듬뿍 담아 작성 중입니다..."):
                prompt = f"""
                당신은 매장에 애정이 가득하고 고객을 소중히 여기는 센스 있는 사장님입니다.
                다음 고객의 리뷰를 분석해서, 방문에 대한 감사와 메뉴에 대한 공감,
                그리고 다음에 또 오고 싶게 만드는 따뜻한 맞춤형 장문 답글을 작성해주세요.
                
                [고객 리뷰]: {review_text}
                
                [조건]
                - 기계적인 느낌 없이 자연스럽고 진정성 있는 말투 (해요체/하십시오체 자연스럽게 혼용)
                - 고객이 언급한 메뉴, 맛, 감정 포인트를 답글에 반드시 포함할 것
                - 플레이스의 매력을 은근히 어필하여 다른 방문자의 체류 시간을 늘릴 것
                - 300자 내외로 작성
                - ⭐️ 문장 중간중간 내용에 어울리는 친근한 이모티콘(😊, 💖, 👍, ㅠㅠ 등)을 아주 자연스럽고 풍부하게 섞어서 작성할 것
                """
                try:
                    response = client.models.generate_content(model=MODEL_ID, contents=prompt)
                    st.success("완료되었습니다! 아래 텍스트를 복사해서 사용하세요.")
                    st.text_area("생성된 답글:", response.text, height=200)
                except Exception as e:
                    st.error(f"오류가 발생했습니다. API 키나 인터넷 연결을 확인해 주세요. ({e})")
        else:
            st.warning("리뷰 내용을 먼저 입력해 주세요.")

# 2번 탭: 플레이스 소식 기획기
with tab2:
    st.subheader("2. 플레이스 소식 탭 자동 기획기")
    st.write("오늘의 날씨, 요일, 그리고 홍보하고 싶은 키워드를 입력해 주세요.")
    
    col1, col2 = st.columns(2)
    with col1:
        weather = st.text_input("오늘 날씨", placeholder="예: 비 오는, 화창한")
    with col2:
        day = st.text_input("오늘 요일", placeholder="예: 수, 금")
        
    keyword = st.text_input("핵심 키워드", placeholder="예: 해물파전, 막걸리 조합")
    
    if st.button("📝 매력적인 소식 글 작성하기", type="primary"):
        if weather and day and keyword:
            with st.spinner("검색 노출(SEO)에 유리한 글을 작성 중입니다..."):
                prompt = f"""
                네이버 플레이스 '소식' 탭에 주 1회 올릴 홍보 글을 작성해주세요.
                
                [상황]: {weather} 날씨의 {day}요일
                [핵심 키워드]: {keyword}
                
                [조건]
                - 고객의 방문 호기심을 자극하는 매력적인 카피라이팅
                - 네이버 검색에 잘 노출되도록(SEO) 자연스러운 키워드 배치
                - 글의 마무리는 오늘 하루 방문을 환영하는 따뜻한 인사말
                - 하단에 검색에 유리한 추천 해시태그 5개 포함
                - 분량은 띄어쓰기 포함 400자 이내
                """
                try:
                    response = client.models.generate_content(model=MODEL_ID, contents=prompt)
                    st.success("완료되었습니다! 사진과 함께 플레이스에 업로드하세요.")
                    st.text_area("생성된 소식 텍스트:", response.text, height=250)
                except Exception as e:
                    st.error(f"오류가 발생했습니다. API 키나 인터넷 연결을 확인해 주세요. ({e})")
        else:

            st.warning("날씨, 요일, 키워드를 모두 채워주세요.")
