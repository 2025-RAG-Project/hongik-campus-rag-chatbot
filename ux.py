import streamlit as st
from datetime import datetime
import json
import streamlit.components.v1 as components

# ================================
# 0. 기본 설정
# ================================
st.set_page_config(
    page_title="홍익대 학사 AI 챗봇 UX",
    layout="wide"
)

HONGIK_BLUE = "#003C8F"
HONGIK_BG = "#F4F6FB"
HONGIK_LOGO_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/9/9d/"
    "Hongik_University_emblem.png"
)

# ================================
# 1. CSS
# ================================
st.markdown(
    f"""
    <style>

    body {{
        background-color: {HONGIK_BG};
    }}

    /* 메인 영역: 제목 안 잘리도록 */
    .block-container {{
        padding-top: 2.8rem !important;
        padding-bottom: 1.2rem;
        background-image: url("{HONGIK_LOGO_URL}");
        background-repeat: no-repeat;
        background-position: calc(100% - 60px) 160px;
        background-size: 80px;
    }}

    /* 사이드바 컨테이너: 파란 배경 + 패딩 최소화 */
    [data-testid="stSidebar"] > div:first-child {{
        background-color: rgba(0, 60, 143, 0.12) !important;
        padding-top: 0.25rem !important;
        padding-bottom: 0.25rem !important;
    }}

    /* 사이드바 전체 글자/줄간격 축소 */
    [data-testid="stSidebar"] * {{
        font-size: 0.9rem !important;
        line-height: 1.2 !important;
    }}

    /* 사이드바 제목 크기/마진 축소 */
    [data-testid="stSidebar"] h2 {{
        font-size: 1.0rem !important;
        margin-top: 0.15rem !important;
        margin-bottom: 0.25rem !important;
    }}

    [data-testid="stSidebar"] h3 {{
        font-size: 0.95rem !important;
        margin-top: 0.15rem !important;
        margin-bottom: 0.25rem !important;
    }}

    /* 일반 텍스트/구분선 마진 줄이기 */
    [data-testid="stSidebar"] p {{
        margin-top: 0.05rem !important;
        margin-bottom: 0.18rem !important;
    }}

    [data-testid="stSidebar"] hr {{
        margin-top: 0.3rem !important;
        margin-bottom: 0.3rem !important;
    }}

    /* 채팅 말풍선 */
    .chat-wrapper {{
        padding: 0.1rem 0.1rem;
    }}

    .chat-message {{
        display: flex;
        margin-bottom: 0.6rem;
    }}

    .chat-message.user {{
        justify-content: flex-end;
    }}

    .chat-message.assistant {{
        justify-content: flex-start;
    }}

    .chat-bubble {{
        max-width: 80%;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        font-size: 0.95rem;
        line-height: 1.5;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
    }}

    .chat-bubble-user {{
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        color: #222222;
    }}

    .chat-bubble-assistant {{
        background-color: #FFFFFF;
        border: 1.5px solid {HONGIK_BLUE};
        color: #111111;
    }}

    .chat-meta-right {{
        font-size: 0.7rem;
        color: #888888;
        margin-top: 0.1rem;
        text-align: right;
        margin-right: 0.2rem;
    }}

    /* 출처 박스 */
    .source-box {{
        font-size: 0.7rem;
        color: #555;
        margin-top: 0.25rem;
        margin-bottom: 1.0rem;
        padding: 0.4rem 0.6rem;
        background-color: #f5f6fa;
        border-radius: 8px;
        border: 1px solid #e0e3ec;
    }}

    .source-box-title {{
        font-weight: 600;
        margin-bottom: 0.1rem;
    }}

    .quick-questions-label {{
        font-size: 0.76rem;
        color: #444;
        margin-top: 0.35rem;
        margin-bottom: 0.12rem;
    }}

    /* 빠른질문 버튼: 아주 작게 + 마진 최소화 */
    button[title="qq"] {{
        font-size: 0.6rem !important;
        padding: 0.14rem 0.36rem !important;
        border-radius: 10px !important;
        margin-bottom: 0.18rem !important;
    }}

    /* 입력창 네모 스타일 */
    [data-testid="stChatInput"] textarea {{
        border-radius: 8px !important;
        border: 1px solid #d0d7e2 !important;
        background-color: #F7F8FB !important;
        color: #222 !important;
    }}

    [data-testid="stChatInput"] button {{
        border-radius: 8px !important;
        border: 1px solid #d0d7e2 !important;
        background-color: #F7F8FB !important;
    }}

    </style>
    """,
    unsafe_allow_html=True,
)

# ================================
# 2. 세션 상태 초기화
# ================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "안녕하세요! 홍익대학교 학사 AI 챗봇입니다\n\n"
                "저는 다음과 같은 질문에 답변할 수 있습니다:\n\n"
                "- 학사 일정 및 공지사항\n"
                "- 졸업 요건 및 학점 관련\n"
                "- 개설 과목 정보\n"
                "- 학과 공지사항\n\n"
                "예시 질문:\n"
                "- 졸업학점이 몇 학점인가요?\n"
                "- 이번 학기 복수전공 신청 기간은?\n"
                "- 산업공학과 전공필수 과목 알려줘\n"
                "- 최근 학사 공지 보여줘\n\n"
                "궁금한 점을 자유롭게 질문해주세요!"
            ),
            "timestamp": datetime.now().strftime("%H:%M"),
            "sources": [
                "홍익대학교 학사공지",
                "홍익대학교 학사일정",
                "각 학과(예: 산업공학과) 홈페이지"
            ],
        }
    ]

if "feedback" not in st.session_state:
    st.session_state.feedback = []

if "fb_choice" not in st.session_state:
    st.session_state.fb_choice = {}

if "quick_question" not in st.session_state:
    st.session_state.quick_question = None

# ================================
# 3. 사이드바
# ================================
with st.sidebar:
    st.markdown("## 봇이름")
    st.caption("홍익대 학사 챗봇")
    st.markdown("---")

    st.markdown("### 카테고리 필터")
    category = st.radio(
        "",
        ["전체", "학교 공지", "학과 공지", "개설 과목"],
        index=0,
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### 새 채팅")
    if st.button("대화 초기화"):
        st.session_state.messages = st.session_state.messages[:1]
        st.session_state.feedback = []
        st.session_state.fb_choice = {}
        st.session_state.quick_question = None
        st.rerun()

    st.markdown("---")
    st.markdown("### 빠른질문")
    st.markdown(
        "<div class='quick-questions-label'>자주 묻는 질문</div>",
        unsafe_allow_html=True,
    )

    qq_list = [
        "졸업학점이 몇 학점인가요?",
        "이번 학기 복수전공 신청 기간은?",
        "산업공학과 전공필수 과목 알려줘",
        "최근 학사 공지 보여줘",
        "수강신청 일정 알려줘",
    ]

    for i, q in enumerate(qq_list):
        if st.button(q, key=f"qq_{i}", help="qq"):
            st.session_state.quick_question = q
            st.rerun()

# ================================
# 4. 메시지 렌더링 함수
# ================================
def render_message(msg: dict, idx: int):
    role = msg.get("role", "assistant")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")
    sources = msg.get("sources", None)

    wrapper_class = "assistant" if role == "assistant" else "user"
    bubble_class = (
        "chat-bubble chat-bubble-assistant"
        if role == "assistant"
        else "chat-bubble chat-bubble-user"
    )

    safe_content = content.replace("\n", "<br>")

    html = f"""
    <div class="chat-wrapper">
        <div class="chat-message {wrapper_class}">
            <div class="{bubble_class}">
                {safe_content}
            </div>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)

    if role == "assistant":
        choice_key = f"msg_{idx}"
        already = st.session_state.fb_choice.get(choice_key, None)

        col1, col2, col3 = st.columns([1.2, 1.2, 3])

        # 👍 / 👎 — 각 답변당 1회만
        with col1:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("👍", key=f"up_{idx}", disabled=already is not None):
                    st.session_state.feedback.append(
                        {"answer": content, "feedback": "up"}
                    )
                    st.session_state.fb_choice[choice_key] = "up"
                    st.rerun()
            with c2:
                if st.button("👎", key=f"down_{idx}", disabled=already is not None):
                    st.session_state.feedback.append(
                        {"answer": content, "feedback": "down"}
                    )
                    st.session_state.fb_choice[choice_key] = "down"
                    st.rerun()

        # 📋 복사 버튼
        with col2:
            js_text = json.dumps(content)

            copy_html = f"""
            <html>
            <body>
              <button onclick="copyText()" 
                      style="font-size:0.7rem;padding:3px 10px;border-radius:6px;border:1px solid #ccc;background:#fff;">
                복사
              </button>

              <script>
                const textToCopy = {js_text};

                function copyText() {{
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(textToCopy).then(() => {{
                            alert("복사되었습니다");
                        }}).catch(err => {{
                            fallbackCopy();
                        }});
                    }} else {{
                        fallbackCopy();
                    }}
                }}

                function fallbackCopy() {{
                    const ta = document.createElement("textarea");
                    ta.value = textToCopy;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand("copy");
                    document.body.removeChild(ta);
                    alert("복사되었습니다");
                }}
              </script>
            </body>
            </html>
            """

            components.html(copy_html, height=40)

        with col3:
            st.markdown(
                f"<div class='chat-meta-right'>{timestamp}</div></div>",
                unsafe_allow_html=True,
            )

        # 🔎 출처 박스
        if sources:
            src_html = "<div class='source-box'><div class='source-box-title'>출처</div>"
            for s in sources:
                src_html += f"· {s}<br>"
            src_html += "</div>"
            st.markdown(src_html, unsafe_allow_html=True)

    else:
        st.markdown(
            f"<div class='chat-meta-right'>{timestamp}</div></div>",
            unsafe_allow_html=True,
        )

# ================================
# 5. 상단 타이틀 + 채팅 영역
# ================================
st.markdown("## 홍익대학교 학사 AI 챗봇")
st.caption("학사 일정 · 졸업 요건 · 개설 과목 · 공지사항 관련 질문을 도와드립니다.")
st.markdown("")

chat_area = st.container()
with chat_area:
    for i, msg in enumerate(st.session_state.messages):
        render_message(msg, i)

st.markdown("---")

# ================================
# 6. 데모 답변 생성 로직 (출처 포함)
# ================================
def build_demo_reply(user_text: str, category: str) -> dict:
    now = datetime.now().strftime("%H:%M")

    cat_msg = ""
    if category != "전체":
        cat_msg = f"\n\n(현재 선택된 카테고리: {category} 기준 안내입니다.)"

    t = user_text
    sources = []

    if "졸업" in t:
        ans = (
            "홍익대학교 졸업 학점은 전공/교양/자유선택으로 나뉘며, "
            "소속 학과와 입학 연도에 따라 기준이 다를 수 있습니다.\n"
            "정확한 기준은 학사요람과 학과 홈페이지의 졸업요건 안내를 확인해 주세요."
        )
        sources = [
            "홍익대학교 학사요람(졸업요건 안내)",
            "각 학과 홈페이지 졸업요건 안내"
        ]
    elif "복수전공" in t:
        ans = (
            "복수전공 신청 기간은 매 학기 학사공지로 안내되며,\n"
            "학사공지에서 '복수전공 신청' 키워드로 검색하면 확인할 수 있습니다."
        )
        sources = [
            "홍익대학교 학사공지 - 복수전공 신청 안내",
            "교무처 공지사항"
        ]
    elif ("전공필수" in t) or ("개설 과목" in t):
        ans = (
            "전공필수 및 개설 과목 정보는 학과 홈페이지 또는 수강편람에서 확인할 수 있습니다.\n"
            "학기별 개설 여부는 달라질 수 있으니 최신 정보를 확인해주세요."
        )
        sources = [
            "해당 학과 홈페이지 교과과정 안내",
            "홍익대학교 수강편람"
        ]
    elif ("공지" in t) or ("공지사항" in t):
        ans = (
            "최근 학사 공지는 학교 홈페이지 > 학사공지에서 최신순으로 확인할 수 있습니다."
        )
        sources = [
            "홍익대학교 홈페이지 - 학사공지"
        ]
    elif ("수강신청" in t) or ("신청 일정" in t):
        ans = (
            "수강신청 일정은 학사일정 및 학사공지에서 함께 안내됩니다.\n"
            "정확한 일정은 반드시 공식 공지를 확인해주세요."
        )
        sources = [
            "홍익대학교 학사일정",
            "홍익대학교 학사공지 - 수강신청 일정 안내"
        ]
    else:
        ans = (
            f"'{user_text}' 라는 질문을 받았습니다.\n"
            "현재는 UX 데모 버전으로, 실제 데이터 연동은 되어 있지 않습니다."
        )
        sources = [
            "홍익대학교 공식 홈페이지",
            "학사 관련 안내 페이지"
        ]

    return {
        "role": "assistant",
        "content": ans + cat_msg,
        "timestamp": now,
        "sources": sources,
    }

# ================================
# 7. 입력 처리
# ================================
user_text_to_send = None

if st.session_state.quick_question:
    user_text_to_send = st.session_state.quick_question
    st.session_state.quick_question = None

chat_input = st.chat_input("질문을 입력하고 Enter를 눌러주세요.")
if chat_input:
    user_text_to_send = chat_input.strip()

if user_text_to_send:
    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_text_to_send,
            "timestamp": datetime.now().strftime("%H:%M"),
        }
    )
    st.session_state.messages.append(build_demo_reply(user_text_to_send, category))
    st.rerun()
