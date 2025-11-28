import streamlit as st
from datetime import datetime
import csv
import os
from pathlib import Path
from dotenv import load_dotenv
import uuid

# LangChain 관련 import
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import tool

# ============================================================================
# 페이지 설정 (가장 먼저!)
# ============================================================================
st.set_page_config(
    page_title="홍익대 RAG QnA 챗봇",
    page_icon="💬",
    layout="wide"
)

# ============================================================================
# 전역 설정
# ============================================================================
# 프로젝트 루트 디렉토리 기준
BASE_DIR = Path(__file__).parent
CHROMA_DIR = BASE_DIR / "build_vector_db" / "chroma_db_enhanced"  
COLLECTION_NAME = "hongik_data"

# 세션 히스토리 저장소
STORE = {}

# ============================================================================
# 세션 상태 초기화
# ============================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "feedback_mode" not in st.session_state:
    st.session_state.feedback_mode = {}

if "feedback_ids" not in st.session_state:
    st.session_state.feedback_ids = {}

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "rag_agent" not in st.session_state:
    st.session_state.rag_agent = None

if "selected_category" not in st.session_state:
    st.session_state.selected_category = "전체"

# ============================================================================
# 카테고리 설정
# ============================================================================
CATEGORIES = {
    "전체": None,  # 필터 없음
    "학교 공지": ["학교 공지"],
    "학과 공지": ["학과 공지"],
    "개설 과목": ["개설 과목"]
}

# ============================================================================
# 빠른 질문
# ============================================================================
QUICK_QUESTIONS = {
    "전체": [
        "최근 공지사항 알려줘",
        "이번 학기 주요 일정은?",
        "장학금 정보 알려줘"
    ],
    "학교 공지": [
        "학교 전체 공지사항 최근거 보여줘",
        "대학원 입학 정보 알려줘",
        "학사 일정 알려줘"
    ],
    "학과 공지": [
        "디자인학부 공지사항 알려줘",
        "건축학부 최근 소식은?",
        "컴퓨터공학부 공지 보여줘"
    ],
    "개설 과목": [
        "이번 학기 개설 과목 알려줘",
        "수강신청 일정은?",
        "교양 과목 추천해줘"
    ]
}

# ============================================================================
# 핵심 함수들
# ============================================================================

def get_session_history(session_id: str) -> ChatMessageHistory:
    """세션 ID에 해당하는 ChatMessageHistory 객체를 반환"""
    if session_id not in STORE:
        STORE[session_id] = ChatMessageHistory()
    return STORE[session_id]


@st.cache_resource
def initialize_rag_agent():
    """RAG 에이전트 초기화 (ChromaDB + LangChain)"""
    try:
        # 환경변수 로드
        load_dotenv()
        
        # ChromaDB 경로 검증
        if not CHROMA_DIR.exists():
            st.error(f"❌ ChromaDB를 찾을 수 없습니다: {CHROMA_DIR}")
            st.info("💡 먼저 `python build_vector_db.py`를 실행해주세요!")
            return None
        
        # LLM 초기화
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # ChromaDB 연결
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )
        
        # ChromaDB 검색 Tool 정의 (유사도 포함)
        @tool
        def search_db_tool(query: str) -> str:
            """홍익대 게시판 데이터베이스를 검색합니다. 공지사항, 모집정보 등을 찾을 때 사용하세요."""
            # 선택된 카테고리 가져오기
            selected_category = st.session_state.get("selected_category", "전체")
            
            # 카테고리 필터 적용
            if selected_category == "전체":
                # 필터 없이 전체 검색
                results = vectorstore.similarity_search_with_score(query, k=3)
            else:
                # 선택된 카테고리로 필터링
                all_results = vectorstore.similarity_search_with_score(query, k=10)
                results = []
                
                for doc, score in all_results:
                    doc_category = doc.metadata.get('category', '')
                    # 선택된 카테고리와 일치하는 문서만
                    if doc_category == selected_category:
                        results.append((doc, score))
                        if len(results) >= 3:
                            break
            
            if not results:
                return f"'{selected_category}' 카테고리에서 검색 결과가 없습니다."
            
            # 검색 결과를 문자열로 변환
            context = []
            similarity_scores = []
            
            for i, (doc, score) in enumerate(results, 1):
                metadata = doc.metadata
                similarity = 1 / (1 + score)
                similarity_scores.append(similarity)
                
                # subcategory 정보 추가 표시
                subcategory = metadata.get('subcategory', '미분류')
                
                context.append(
                    f"[결과 {i}] (유사도: {similarity:.2%})\n"
                    f"제목: {metadata.get('title', '제목 없음')}\n"
                    f"날짜: {metadata.get('date', '날짜 없음')}\n"
                    f"분류: {metadata.get('category', '미분류')} - {subcategory}\n"
                    f"URL: {metadata.get('url', 'URL 없음')}\n"
                    f"내용: {doc.page_content[:300]}...\n"
                )
            
            # 평균 유사도 계산하여 세션에 저장
            avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0
            if "last_similarity" not in st.session_state:
                st.session_state.last_similarity = {}
            
            st.session_state.last_similarity["score"] = avg_similarity
            st.session_state.last_similarity["scores"] = similarity_scores
            
            return "\n\n".join(context)
        
        tools = [search_db_tool]
        
        # Prompt 정의
        prompt = ChatPromptTemplate.from_messages([
            ('system', '''당신은 홍익대학교 학사 정보 안내 챗봇입니다.

역할:
- 학생들의 질문에 친절하고 정확하게 답변합니다
- 제공된 도구(데이터베이스 검색)를 활용하여 최신 정보를 제공합니다
- 검색 결과에 URL이 있다면 반드시 포함하여 안내합니다

답변 규칙:
1. 질문과 관련된 정보를 데이터베이스에서 검색합니다
2. 검색 결과를 바탕으로 명확하고 구조화된 답변을 제공합니다
3. 여러 결과가 있을 경우 간략히 요약하여 제시합니다
4. URL은 "자세한 내용: [URL]" 형식으로 안내합니다
5. 검색 결과가 없으면 솔직하게 알려줍니다
'''),
            MessagesPlaceholder(variable_name='history'),
            ('human', "{input}"),
            MessagesPlaceholder(variable_name='agent_scratchpad')
        ])
        
        # Agent 생성
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            handle_parsing_errors=True
        )
        
        # 메모리 적용
        runnable = RunnableWithMessageHistory(
            agent_executor,
            get_session_history,
            input_messages_key='input',
            history_messages_key='history'
        )
        
        return runnable
        
    except Exception as e:
        st.error(f"RAG 에이전트 초기화 실패: {str(e)}")
        return None


def save_feedback(feedback_data, is_update=False, feedback_id=None):
    """피드백을 CSV 파일로 저장"""
    feedback_dir = Path("data/feedbacks")
    feedback_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y%m%d")
    feedback_file = feedback_dir / f"feedback_{today}.csv"
    
    fieldnames = [
        "feedback_id", "timestamp", "question", "answer", 
        "feedback_type", "feedback_text", "edit_count", "updated_at"
    ]
    
    if is_update and feedback_id:
        feedbacks = []
        if feedback_file.exists():
            with open(feedback_file, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("feedback_id") == feedback_id:
                        row["feedback_text"] = feedback_data["feedback_text"]
                        row["updated_at"] = datetime.now().isoformat()
                        row["edit_count"] = str(int(row.get("edit_count", 0)) + 1)
                    feedbacks.append(row)
        
        with open(feedback_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(feedbacks)
    else:
        feedback_data["feedback_id"] = f"{feedback_data['timestamp']}_{id(feedback_data)}"
        feedback_data["edit_count"] = 0
        feedback_data["updated_at"] = ""
        
        file_exists = feedback_file.exists()
        with open(feedback_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(feedback_data)


def copy_to_clipboard(text, button_id):
    """텍스트를 복사 가능한 형태로 표시"""
    with st.expander("📋 복사하기", expanded=False):
        st.code(text, language=None)
        st.caption("위 텍스트 박스의 우측 상단 복사 아이콘을 클릭하세요")


def get_confidence_level(similarity: float) -> tuple:
    """유사도 점수를 기반으로 신뢰도 레벨 반환"""
    if similarity >= 0.8:
        return "매우 높음 ⭐⭐⭐", "🟢", "success"
    elif similarity >= 0.6:
        return "높음 ⭐⭐", "🟡", "info"
    elif similarity >= 0.4:
        return "보통 ⭐", "🟠", "warning"
    else:
        return "낮음", "🔴", "error"


def display_confidence_badge(similarity: float):
    """신뢰도 배지 표시"""
    confidence_text, emoji, alert_type = get_confidence_level(similarity)
    
    if alert_type == "success":
        st.success(f"{emoji} **답변 신뢰도: {confidence_text}** ({similarity:.1%})")
    elif alert_type == "info":
        st.info(f"{emoji} **답변 신뢰도: {confidence_text}** ({similarity:.1%})")
    elif alert_type == "warning":
        st.warning(f"{emoji} **답변 신뢰도: {confidence_text}** ({similarity:.1%})")
    else:
        st.error(f"{emoji} **답변 신뢰도: {confidence_text}** ({similarity:.1%})")
        st.caption("💡 검색 결과와 질문의 유사도가 낮습니다. 질문을 더 구체적으로 해보세요.")


def process_question(prompt):
    """질문 처리 및 응답 생성 (RAG)"""
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    try:
        # RAG 에이전트가 없으면 초기화
        if st.session_state.rag_agent is None:
            st.session_state.rag_agent = initialize_rag_agent()
        
        if st.session_state.rag_agent is None:
            raise Exception("RAG 에이전트를 초기화할 수 없습니다.")
        
        # 유사도 초기화
        if "last_similarity" not in st.session_state:
            st.session_state.last_similarity = {}
        st.session_state.last_similarity["score"] = None
        
        # RAG 에이전트 실행
        config = {"configurable": {"session_id": st.session_state.session_id}}
        result = st.session_state.rag_agent.invoke(
            {"input": prompt}, 
            config=config
        )
        
        response = result.get("output", "응답을 생성할 수 없습니다.")
        
        # 메시지와 유사도 함께 저장
        similarity_score = st.session_state.last_similarity.get("score")
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response,
            "similarity": similarity_score  # 유사도 저장
        })
        
    except Exception as e:
        error_message = f"죄송합니다. 오류가 발생했습니다: {str(e)}"
        st.session_state.messages.append({
            "role": "assistant", 
            "content": error_message,
            "similarity": None
        })

# ============================================================================
# UI 렌더링
# ============================================================================

# 타이틀
st.title("💬 홍익대 RAG 기반 QnA 챗봇")
st.markdown("---")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    
    # DB 연결 상태
    if CHROMA_DIR.exists():
        st.success("✅ ChromaDB 연결됨")
        st.caption(f"📁 {CHROMA_DIR}")
    else:
        st.error("❌ ChromaDB를 찾을 수 없습니다")
        st.caption(f"📁 {CHROMA_DIR}")
        st.info("💡 `python build_vector_db.py` 실행 필요")
    
    st.markdown("---")
    
    # 카테고리 필터
    st.subheader("🏷️ 카테고리 필터")
    selected_category = st.radio(
        "검색 범위 선택:",
        options=list(CATEGORIES.keys()),
        index=0,
        key="category_radio"
    )
    
    # 카테고리 변경 시 세션에 저장
    if st.session_state.selected_category != selected_category:
        st.session_state.selected_category = selected_category
        st.info(f"📌 '{selected_category}' 카테고리가 선택되었습니다")
    
    # 선택된 카테고리 설명
    if selected_category == "전체":
        st.caption("💡 모든 카테고리에서 검색합니다")
    elif selected_category == "학교 공지":
        st.caption("💡 학교 전체 공지사항을 검색합니다")
    elif selected_category == "학과 공지":
        st.caption("💡 각 학과별 공지사항을 검색합니다")
    elif selected_category == "개설 과목":
        st.caption("💡 수강신청 및 강의 관련 정보를 검색합니다")
    
    st.markdown("---")
    
    # 대화 초기화 버튼
    if st.button("🔄 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.feedback_mode = {}
        st.session_state.feedback_ids = {}
        st.session_state.pending_question = None
        if st.session_state.session_id in STORE:
            STORE[st.session_state.session_id].clear()
        st.rerun()
    
    st.markdown("---")
    
    # 빠른 질문 버튼
    st.subheader("⚡ 빠른 질문")
    
    # 선택된 카테고리에 맞는 질문 표시
    category_questions = QUICK_QUESTIONS.get(st.session_state.selected_category, QUICK_QUESTIONS["전체"])
    
    for question in category_questions:
        if st.button(f"💭 {question}", use_container_width=True):
            st.session_state.pending_question = question
            st.rerun()
    
    st.markdown("---")
    
    # 시스템 정보
    st.caption("📁 시스템 정보")
    st.caption(f"세션 ID: {st.session_state.session_id[:8]}...")
    
    feedback_dir = Path("data/feedbacks")
    if feedback_dir.exists():
        feedback_files = list(feedback_dir.glob("*.csv"))
        st.caption(f"📊 피드백: {len(feedback_files)}개 파일")
    else:
        st.caption("📝 피드백 없음")

# 초기 안내 메시지
if len(st.session_state.messages) == 0:
    st.info(f"""
    👋 **안녕하세요! 홍익대학교 학사 정보 안내 챗봇입니다.**
    
    현재 선택된 카테고리: **{st.session_state.selected_category}**
    
    저는 홍익대 게시판 데이터를 기반으로 질문에 답변해드립니다.
    
    📌 **카테고리별 검색:**
    - **전체**: 모든 정보 검색
    - **학교 공지**: 학교 전체 공지사항
    - **학과 공지**: 각 학과별 공지사항  
    - **개설 과목**: 수강신청 및 강의 정보
    
    💡 **Tip:** 왼쪽 사이드바에서 카테고리를 선택하면 더 정확한 검색이 가능합니다!
    """)

# 빠른 질문 처리
if st.session_state.pending_question:
    process_question(st.session_state.pending_question)
    st.session_state.pending_question = None
    st.rerun()

# 대화 내역 표시
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # 어시스턴트 메시지에만 버튼 표시
        if message["role"] == "assistant":
            # 신뢰도 표시
            similarity = message.get("similarity")
            if similarity is not None:
                display_confidence_badge(similarity)
            
            if idx not in st.session_state.feedback_mode:
                col1, col2, col3 = st.columns([1, 17, 4])
                with col1:
                    if st.button("👍", key=f"like_{idx}"):
                        st.session_state.feedback_mode[idx] = {
                            "type": "satisfied",
                            "text": "",
                            "submitted": False
                        }
                        st.rerun()
                with col2:
                    if st.button("👎", key=f"dislike_{idx}"):
                        st.session_state.feedback_mode[idx] = {
                            "type": "unsatisfied",
                            "text": "",
                            "submitted": False
                        }
                        st.rerun()
                
                copy_to_clipboard(message["content"], idx)
            else:
                feedback_info = st.session_state.feedback_mode[idx]
                feedback_type = feedback_info["type"]
                
                if feedback_info["submitted"]:
                    st.success("✅ 피드백이 저장되었습니다. 감사합니다! 🙏")
                    st.info(f"**{'만족' if feedback_type == 'satisfied' else '불만족'}** 선택\n\n**의견:** {feedback_info['text'] if feedback_info['text'] else '(없음)'}")
                    
                    col1, col2, col3 = st.columns([1, 8, 4])
                    with col1:
                        if st.button("✏️ 수정", key=f"edit_{idx}"):
                            st.session_state.feedback_mode[idx]["submitted"] = False
                            st.rerun()
                    with col2:
                        if st.button("🗑️ 삭제", key=f"delete_{idx}"):
                            del st.session_state.feedback_mode[idx]
                            if idx in st.session_state.feedback_ids:
                                del st.session_state.feedback_ids[idx]
                            st.rerun()
                else:
                    feedback_text = st.text_area(
                        f"{'만족하신 점' if feedback_type == 'satisfied' else '불만족하신 점'}을 자세히 알려주세요 (선택사항):",
                        value=feedback_info["text"],
                        key=f"feedback_text_{idx}",
                        height=100
                    )
                    
                    col1, col2 = st.columns([1, 12])
                    with col1:
                        if st.button("✅ 완료", key=f"submit_{idx}"):
                            feedback_data = {
                                "timestamp": datetime.now().isoformat(),
                                "question": st.session_state.messages[idx-1]["content"] if idx > 0 else "",
                                "answer": message["content"],
                                "feedback_type": feedback_type,
                                "feedback_text": feedback_text
                            }
                            
                            is_update = idx in st.session_state.feedback_ids
                            feedback_id = st.session_state.feedback_ids.get(idx)
                            
                            if is_update:
                                save_feedback(feedback_data, is_update=True, feedback_id=feedback_id)
                            else:
                                save_feedback(feedback_data, is_update=False)
                                st.session_state.feedback_ids[idx] = feedback_data.get("feedback_id")
                            
                            st.session_state.feedback_mode[idx]["text"] = feedback_text
                            st.session_state.feedback_mode[idx]["submitted"] = True
                            st.rerun()
                    with col2:
                        if st.button("❌ 취소", key=f"cancel_{idx}"):
                            del st.session_state.feedback_mode[idx]
                            st.rerun()

# 사용자 입력
if prompt := st.chat_input("질문을 입력하세요..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("답변을 생성하고 있습니다..."):
            process_question(prompt)
    
    st.rerun()

# 푸터
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray; font-size: 0.8em;'>홍익대 RAG 기반 QnA 챗봇 | Powered by OpenAI & ChromaDB</div>",
    unsafe_allow_html=True
)