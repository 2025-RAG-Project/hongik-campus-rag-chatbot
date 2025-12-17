import streamlit as st
from datetime import datetime
import csv
from pathlib import Path
from dotenv import load_dotenv
import uuid
import json
import streamlit.components.v1 as components
from PIL import Image
import pickle
import math

# LangChain 관련 import
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain.storage import LocalFileStore, EncoderBackedStore
from langchain.retrievers import ParentDocumentRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

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
BASE_DIR = Path(__file__).parent
CHROMA_DIR = BASE_DIR / "build_vector_db" / "chroma_db"
DOCSTORE_DIR = BASE_DIR / "build_vector_db" / "docstore"
COLLECTION_NAME = "hongik_data"

# LLM 캐시 설정
LLM_CACHE_DIR = BASE_DIR / "build_vector_db" / "llm_cache"
LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LLM_CACHE_DB = LLM_CACHE_DIR / "llm_cache.db"

#  최신성(rencency) 가중치 리랭킹 파라미터
# - alpha가 클수록 "의미 유사도"를 더 중시
# - (1-alpha)가 클수록 "최근 문서"를 더 중시
RECENCY_ALPHA = 0.75
RECENCY_DECAY_DAYS = 360

#  assistant(챗봇) 아바타
try:
    HONGIK_AVATAR = Image.open("hongik_emblem.png")
except Exception:
    HONGIK_AVATAR = "🤖"

#  user(질문자) 아바타
try:
    USER_AVATAR = Image.open("mascot.png")
except Exception:
    USER_AVATAR = "👤"


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

if "rag_chain" not in st.session_state:
    st.session_state.rag_chain = None

if "retriever" not in st.session_state:
    st.session_state.retriever = None

if "selected_category" not in st.session_state:
    st.session_state.selected_category = "전체"

if "last_similarity" not in st.session_state:
    st.session_state.last_similarity = {}

# ============================================================================
# 카테고리
# ============================================================================
CATEGORIES = {
    "전체": None,
    "대학공지": "대학공지",
    "학과공지": "학과공지",
    "교과목/수강": "교과목/수강"
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
    "대학공지": [
        "학교 전체 공지사항 최근거 보여줘",
        "대학원 입학 정보 알려줘",
        "학사 일정 알려줘"
    ],
    "학과공지": [
        "디자인학부 공지사항 알려줘",
        "건축학부 최근 소식은?",
        "컴퓨터공학부 공지 보여줘"
    ],
    "교과목/수강": [
        "이번 학기 개설 과목 알려줘",
        "수강신청 일정은?",
        "교양 과목 추천해줘"
    ]
}

# ============================================================================
# UI Helper
# ============================================================================

def render_copy_button(content: str, idx: int):
    js_text = json.dumps(content)
    copy_html = f"""
    <html>
    <body>
      <button onclick="copyText_{idx}()"
              style="font-size:0.7rem;padding:3px 10px;
                     border-radius:6px;border:1px solid #ccc;
                     background:#fff;cursor:pointer;">
        복사
      </button>

      <script>
        const textToCopy_{idx} = {js_text};

        function copyText_{idx}() {{
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(textToCopy_{idx}).then(() => {{
                    alert("복사되었습니다");
                }}).catch(err => {{
                    fallbackCopy_{idx}();
                }});
            }} else {{
                fallbackCopy_{idx}();
            }}
        }}

        function fallbackCopy_{idx}() {{
            const ta = document.createElement("textarea");
            ta.value = textToCopy_{idx};
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
    components.html(copy_html, height=60, width=120)


def render_sources_box(sources: list):
    if not sources:
        return

    src_html = """
    <div style="
        font-size:0.75rem;
        color:#555;
        margin-top:0.35rem;
        margin-bottom:0.4rem;
        padding:0.4rem 0.6rem;
        background-color:#f5f6fa;
        border-radius:6px;
        border:1px solid #e0e3ec;
    ">
      <div style="font-weight:600; margin-bottom:0.2rem;">출처</div>
    """
    for s in sources:
        src_html += f"· {s}<br>"
    src_html += "</div>"
    st.markdown(src_html, unsafe_allow_html=True)


# ============================================================================
# Scoring (Recency / Similarity)
# ============================================================================

def calculate_recency_weight(date_str: str, decay_days: int = RECENCY_DECAY_DAYS) -> float:
    """
    날짜 기반 최신성 가중치 (0.1~1.0)
    - date_str: "YYYY-MM-DD" 또는 "YYYY.MM.DD" 가정
    """
    try:
        if date_str in ["상시", "날짜미상", None, ""]:
            return 1

        normalized_date = str(date_str).replace(".", "-").strip()
        doc_date = datetime.strptime(normalized_date, "%Y-%m-%d")
        today = datetime.now()
        days_old = (today - doc_date).days

        weight = math.exp(-days_old / decay_days)
        return max(0.1, min(1.0, weight))
    except Exception:
        return 0.5


def _extract_parent_id(metadata: dict):
    if not metadata:
        return None
    for key in ("doc_id", "parent_id", "parent", "document_id"):
        val = metadata.get(key)
        if val:
            return val
    return None


def _score_to_similarity(score):
    try:
        return 1 / (1 + float(score))
    except Exception:
        return 0.5


def get_confidence_level(similarity: float) -> tuple:
    if similarity >= 0.8:
        return "매우 높음 ⭐⭐⭐", "🟢", "success"
    elif similarity >= 0.6:
        return "높음 ⭐⭐", "🟡", "info"
    elif similarity >= 0.4:
        return "보통 ⭐", "🟠", "warning"
    else:
        return "낮음", "🔴", "error"


def display_confidence_badge(similarity: float):
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


# ============================================================================
# Feedback
# ============================================================================

def save_feedback(feedback_data, is_update=False, feedback_id=None):
    """피드백을 CSV 파일로 저장하고 feedback_id를 반환"""
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
                        row["feedback_text"] = feedback_data.get("feedback_text", "")
                        row["updated_at"] = datetime.now().isoformat()
                        row["edit_count"] = str(int(row.get("edit_count", 0)) + 1)
                    feedbacks.append(row)

        with open(feedback_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(feedbacks)

        return feedback_id

    new_id = str(uuid.uuid4())
    row = {
        "feedback_id": new_id,
        "timestamp": feedback_data.get("timestamp", datetime.now().isoformat()),
        "question": feedback_data.get("question", ""),
        "answer": feedback_data.get("answer", ""),
        "feedback_type": feedback_data.get("feedback_type", ""),
        "feedback_text": feedback_data.get("feedback_text", ""),
        "edit_count": 0,
        "updated_at": ""
    }

    file_exists = feedback_file.exists()
    with open(feedback_file, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return new_id


# ============================================================================
# RAG Init
# ============================================================================

@st.cache_resource
def initialize_rag_system():
    """ParentDocumentRetriever 기반 RAG 시스템 초기화"""
    try:
        load_dotenv()
        set_llm_cache(SQLiteCache(database_path=str(LLM_CACHE_DB)))

        if not CHROMA_DIR.exists():
            st.error(f"❌ ChromaDB를 찾을 수 없습니다: {CHROMA_DIR}")
            st.info("💡 먼저 벡터DB 구축 스크립트를 실행해주세요!")
            return None, None

        if not DOCSTORE_DIR.exists():
            st.error(f"❌ Docstore를 찾을 수 없습니다: {DOCSTORE_DIR}")
            return None, None

        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

        vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(CHROMA_DIR)
        )

        fs = LocalFileStore(str(DOCSTORE_DIR))
        docstore = EncoderBackedStore(
            store=fs,
            key_encoder=lambda x: x,
            value_serializer=pickle.dumps,
            value_deserializer=pickle.loads
        )

        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=50,
            separators=["\n\n", "\n", " ", ""]
        )

        retriever = ParentDocumentRetriever(
            vectorstore=vectorstore,
            docstore=docstore,
            child_splitter=child_splitter,
            parent_splitter=None
        )

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)

        prompt = ChatPromptTemplate.from_messages([
            ('system', '''당신은 홍익대학교 학사 정보 안내 챗봇입니다.

역할:
- 학생들의 질문에 친절하고 정확하게 답변합니다
- 제공된 참고 문서를 바탕으로 최신 정보를 제공합니다
- 검색 결과에 URL이 있다면 반드시 포함하여 안내합니다

참고 문서 활용 방법:
- 각 문서에는 제목, 날짜, 분류, 학과, URL, 내용이 포함되어 있습니다
- 여러 문서가 있을 때는 날짜가 최근인 정보를 우선적으로 안내하세요

답변 규칙:
1. 참고 문서의 제목과 날짜를 언급하여 신뢰성을 높입니다
2. 여러 결과가 있을 경우 각각을 구분하여 간략히 요약합니다
3. URL은 "자세한 내용: [URL]" 형식으로 반드시 안내합니다
4. 검색 결과가 없거나 관련 정보가 없으면 솔직하게 알려줍니다
5. 이전 대화 내용을 참고하여 맥락에 맞는 답변을 제공합니다
'''),
            MessagesPlaceholder(variable_name="history"),
            ('human', '질문: {question}\n\n참고 문서:\n{context}'),
        ])

        chain = prompt | llm | StrOutputParser()
        return chain, retriever

    except Exception as e:
        st.error(f"RAG 시스템 초기화 실패: {str(e)}")
        return None, None


# ============================================================================
# Retrieval + Recency Re-rank
# ============================================================================

def get_filtered_documents(retriever, query: str, category_filter: str = None, k: int = 50):
    """
    카테고리 필터를 Chroma 검색에 직접 적용
    child 검색(score 포함) → parent 복원
    의미유사도 + 최신성 가중치로 리랭크
    반환: (docs, avg_semantic_similarity)
    """
    try:
        vectorstore = retriever.vectorstore
        docstore = retriever.docstore

        chroma_filter = None
        if category_filter and category_filter != "전체":
            chroma_filter = {"notice_type": category_filter}

        # 1) child 검색 (score 포함)
        child_results = vectorstore.similarity_search_with_score(
            query,
            k=k * 5,                 # 리랭크/중복 제거 고려 넉넉히
            filter=chroma_filter
        )
        if not child_results:
            return [], 0.0

        # 2) parent별 best semantic similarity 수집 + parent id 순서
        parent_id_to_best_sim = {}
        parent_ids = []
        for child_doc, score in child_results:
            pid = _extract_parent_id(child_doc.metadata)
            if not pid:
                # parent id가 아예 없다면 child를 parent 취급 fallback
                pid = f"__child__:{hash(child_doc.page_content)}"

            sim = _score_to_similarity(score)

            if pid not in parent_id_to_best_sim:
                parent_id_to_best_sim[pid] = sim
                parent_ids.append(pid)
            else:
                parent_id_to_best_sim[pid] = max(parent_id_to_best_sim[pid], sim)

            if len(parent_ids) >= (k * 3):
                break

        # 3) parent 로드
        loaded = docstore.mget(parent_ids)
        parent_docs = []
        parent_meta = []  # (doc, semantic_sim)
        for pid, doc in zip(parent_ids, loaded):
            if doc is None:
                continue
            parent_docs.append(doc)
            parent_meta.append((doc, parent_id_to_best_sim.get(pid, 0.5)))

        # docstore miss가 많으면 child fallback
        if not parent_docs:
            fallback_docs = [d for d, _ in child_results[:k]]
            avg_sim = sum([_score_to_similarity(s) for _, s in child_results[:k]]) / max(1, len(fallback_docs))
            return fallback_docs, avg_sim

        # 4) 최신성 가중치로 리랭크
        scored = []
        for doc, sem_sim in parent_meta:
            md = doc.metadata or {}
            rec = calculate_recency_weight(md.get("date"), decay_days=RECENCY_DECAY_DAYS)
            final_score = (RECENCY_ALPHA * sem_sim) + ((1 - RECENCY_ALPHA) * rec)
            scored.append((final_score, sem_sim, rec, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:k]
        top_docs = [d for _, _, _, d in top]

        # 신뢰도 배지는 "의미 유사도" 평균으로 유지 (최신성은 정렬에만 반영)
        avg_semantic_similarity = sum([sem for _, sem, _, _ in top]) / max(1, len(top))

        # (디버그/확장용) 리랭크 점수도 같이 보관 가능
        st.session_state.last_rerank_debug = [
            {
                "title": (doc.metadata or {}).get("title", ""),
                "date": (doc.metadata or {}).get("date", ""),
                "semantic": sem,
                "recency": rec,
                "final": fin
            }
            for fin, sem, rec, doc in top
        ]

        return top_docs, avg_semantic_similarity

    except Exception as e:
        st.error(f"문서 검색 중 오류 발생: {str(e)}")
        return [], 0.0


def get_answer_stream(chain, retriever, query: str, history: list, category_filter: str = None):
    """스트리밍 방식 답변 생성 (최신성 리랭크 반영)"""
    context_docs, avg_similarity = get_filtered_documents(retriever, query, category_filter, k=20)

    if not context_docs:
        yield "검색 결과가 없습니다. 질문을 더 구체적으로 입력해주세요."
        return

    context_parts = []
    for idx, doc in enumerate(context_docs, 1):
        metadata = doc.metadata or {}
        context_part = f"""[문서 {idx}]
제목: {metadata.get('title', '제목 없음')}
날짜: {metadata.get('date', '날짜 없음')}
분류: {metadata.get('notice_type', '미분류')}
학과: {metadata.get('department', '해당없음')}
URL: {metadata.get('url', 'URL 없음')}

내용:
{doc.page_content}
"""
        context_parts.append(context_part)

    context = '\n\n---\n\n'.join(context_parts)

    st.session_state.last_similarity = {
        "score": avg_similarity,
        "docs": context_docs
    }

    for chunk in chain.stream({
        "question": query,
        "context": context,
        "history": history
    }):
        yield chunk


# ============================================================================
# Main interaction
# ============================================================================

def process_question(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        if st.session_state.rag_chain is None or st.session_state.retriever is None:
            chain, retriever = initialize_rag_system()
            st.session_state.rag_chain = chain
            st.session_state.retriever = retriever

        if st.session_state.rag_chain is None:
            raise Exception("RAG 시스템을 초기화할 수 없습니다.")

        # 최근 5개 히스토리
        history = []
        for msg in st.session_state.messages[-6:-1]:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                history.append(("user", content))
            else:
                history.append(("assistant", content))

        category_filter = st.session_state.get("selected_category", "전체")
        if category_filter == "전체":
            category_filter = None

        response_placeholder = st.empty()
        full_response = ""

        for chunk in get_answer_stream(
            st.session_state.rag_chain,
            st.session_state.retriever,
            prompt,
            history,
            category_filter
        ):
            full_response += chunk
            response_placeholder.markdown(full_response + "▌")

        response_placeholder.markdown(full_response)

        similarity_score = st.session_state.last_similarity.get("score", 0.0)
        retrieved_docs = st.session_state.last_similarity.get("docs", [])

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "similarity": similarity_score,
            "docs": retrieved_docs
        })

    except Exception as e:
        error_message = f"죄송합니다. 오류가 발생했습니다: {str(e)}"
        st.session_state.messages.append({
            "role": "assistant",
            "content": error_message,
            "similarity": None,
            "docs": []
        })


# ============================================================================
# UI
# ============================================================================

with st.sidebar:
    st.title("🎓 홍익대 QnA 챗봇")
    st.markdown("---")

    st.subheader("🏷️ 카테고리 필터")
    selected = st.radio(
        "검색 범위를 선택하세요",
        options=list(CATEGORIES.keys()),
        index=list(CATEGORIES.keys()).index(st.session_state.selected_category),
        key="category_radio"
    )
    if selected != st.session_state.selected_category:
        st.session_state.selected_category = selected
        st.rerun()

    st.markdown("---")

    st.subheader("⚡ 빠른 질문")
    quick_qs = QUICK_QUESTIONS.get(st.session_state.selected_category, [])
    for q in quick_qs:
        if st.button(q, key=f"quick_{q}", use_container_width=True):
            st.session_state.pending_question = q
            st.rerun()

    st.markdown("---")

    if st.button("🔄 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.feedback_mode = {}
        st.session_state.feedback_ids = {}
        st.session_state.last_similarity = {}
        st.session_state.pop("last_rerank_debug", None)
        st.rerun()

    st.markdown("---")
    st.caption(f"세션 ID: {st.session_state.session_id[:8]}...")
    st.caption("📊 RAG: ParentDocumentRetriever + Recency Re-rank")


st.title("💬 홍익대학교 학사정보 챗봇")
st.markdown(f"**현재 카테고리**: {st.session_state.selected_category}")
st.markdown("---")

# 대화 내역 표시
for idx, message in enumerate(st.session_state.messages):
    role = message["role"]

    # 아바타 적용: assistant는 HONGIK_AVATAR, user는 USER_AVATAR
    if role == "assistant":
        chat_ctx = st.chat_message("assistant", avatar=HONGIK_AVATAR)
    elif role == "user":
        chat_ctx = st.chat_message("user", avatar=USER_AVATAR)
    else:
        chat_ctx = st.chat_message(role)

    with chat_ctx:
        st.markdown(message["content"])
        
        # 어시스턴트 메시지에만 버튼 표시
        if role == "assistant":
            # 신뢰도 표시
            similarity = message.get("similarity")
            if similarity is not None:
                display_confidence_badge(similarity)
            
            
            docs = message.get("docs", [])
            if docs:
                sources = []
                for doc in docs[:3]:
                    md = doc.metadata or {}
                    title = md.get("title", "제목 없음")
                    url = md.get("url", "")
                    date = md.get("date", "")
                    notice_type = md.get("notice_type", "")

                    source_text = f"{title}"
                    if date:
                        source_text += f" ({date})"
                    if notice_type:
                        source_text += f" [{notice_type}]"
                    if url:
                        source_text += f" - {url}"
                    sources.append(source_text)

                render_sources_box(sources)
            
            
            
            
            if idx not in st.session_state.feedback_mode:
                # 왼쪽 여백, 👍, 👎, 복사, 오른쪽 여백
                spacer_l, col1, col2, col3, spacer_r = st.columns(
                    [0.1, 0.3, 0.3, 0.3, 4]
                )
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
                with col3:
                    render_copy_button(message["content"], idx)
            else:
                feedback_info = st.session_state.feedback_mode[idx]
                feedback_type = feedback_info["type"]
                
                if feedback_info["submitted"]:
                    st.success("✅ 피드백이 저장되었습니다. 감사합니다! 🙏")
                    st.info(
                        f"**{'만족' if feedback_type == 'satisfied' else '불만족'}** 선택\n\n"
                        f"**의견:** {feedback_info['text'] if feedback_info['text'] else '(없음)'}"
                    )
                    
                    spacer_l, col1, col2, col3, spacer_r = st.columns(
                        [0.1, 0.5, 0.5, 0.4, 5]
                    )
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
                    with col3:
                        render_copy_button(message["content"], idx)
                else:
                    feedback_text = st.text_area(
                        f"{'만족하신 점' if feedback_type == 'satisfied' else '불만족하신 점'}을 자세히 알려주세요 (선택사항):",
                        value=feedback_info["text"],
                        key=f"feedback_text_{idx}",
                        height=100
                    )
                    
                    spacer_l, col1, col2, col3, spacer_r = st.columns(
                        [0.1, 0.5, 0.5, 0.4, 5]
                    )
                    with col1:
                        if st.button("✅ 완료", key=f"submit_{idx}"):
                            feedback_data = {
                                "timestamp": datetime.now().isoformat(),
                                "question": st.session_state.messages[idx - 1]["content"] if idx > 0 else "",
                                "answer": message["content"],
                                "feedback_type": feedback_type,
                                "feedback_text": feedback_text
                            }
                            
                            is_update = idx in st.session_state.feedback_ids
                            feedback_id = st.session_state.feedback_ids.get(idx)
                            
                            if is_update:
                                save_feedback(
                                    feedback_data,
                                    is_update=True,
                                    feedback_id=feedback_id
                                )
                            else:
                                save_feedback(feedback_data, is_update=False)
                                st.session_state.feedback_ids[idx] = feedback_data.get(
                                    "feedback_id"
                                )
                            
                            st.session_state.feedback_mode[idx]["text"] = feedback_text
                            st.session_state.feedback_mode[idx]["submitted"] = True
                            st.rerun()
                    with col2:
                        if st.button("❌ 취소", key=f"cancel_{idx}"):
                            del st.session_state.feedback_mode[idx]
                            st.rerun()
                    with col3:
                        render_copy_button(message["content"], idx)

            # 여기서 출처 박스 렌더링 (항상 버튼 아래)
            sources = message.get("sources", [])
            render_sources_box(sources)


if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None
    process_question(question)
    st.rerun()

if prompt := st.chat_input("궁금한 점을 물어보세요..."):
    process_question(prompt)
    st.rerun()

if len(st.session_state.messages) == 0:
    with st.chat_message("assistant", avatar=HONGIK_AVATAR):
        st.markdown("""
        안녕하세요! 홍익대학교 학사정보 챗봇입니다. 🎓
        
        **도움이 필요하신가요?**
        - 왼쪽 사이드바에서 카테고리를 선택하세요
        - 빠른 질문 버튼을 눌러보세요
        - 또는 직접 질문을 입력해주세요!

        무엇을 도와드릴까요?
        """)
