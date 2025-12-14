# main.py
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
# from example import fewshot_examples
from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache
import pickle
from langchain.storage import LocalFileStore
from langchain.storage import EncoderBackedStore
from langchain.retrievers import ParentDocumentRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

#LLM cache는 Vecot DB와 다른 파일을 사용해야 함.
database_path = r"C:\Users\82103\Desktop\수업 및 과제\복수전공-산업데이터공학과\파이썬데이터분석\RAG_LangChain_Project\db_folder_전달\db_folder_전달\docstore\llm_cache.db"
set_llm_cache(SQLiteCache(database_path=database_path))
#persist_directory(CHROMA_DIR)=.sqlite3 파일이 있는 폴더
CHROMA_DIR=r"C:\Users\82103\Desktop\수업 및 과제\복수전공-산업데이터공학과\파이썬데이터분석\RAG_LangChain_Project\db_folder_전달\db_folder_전달\chroma_db\chroma_db"
DOCSTORE_DIR = r"C:\Users\82103\Desktop\수업 및 과제\복수전공-산업데이터공학과\파이썬데이터분석\RAG_LangChain_Project\db_folder_전달\db_folder_전달\docstore"


def load_vector_store():
    # 1. 임베딩 설정 (구축할 때와 똑같은 모델이어야 함)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    # 2. Vector Store (검색용 DB) 불러오기
    vectorstore = Chroma(
        collection_name="hongik_data",
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR
    )

    # 3. Doc Store (원본 저장소) 불러오기
    #    구축할 때 사용한 pickle 방식 그대로 다시 설정해줘야 합니다.
    fs = LocalFileStore(DOCSTORE_DIR)
    docstore = EncoderBackedStore(
        store=fs,
        key_encoder=lambda x: x,
        value_serializer=pickle.dumps,
        value_deserializer=pickle.loads
    )

    # 4. Splitter 설정 (구축 때와 동일하게)
    #    PDR 객체를 다시 만들 때 필요합니다.
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n\n", "\n", " ", ""]
    )

    # 5. 두 저장소를 연결하여 Retriever 재구성
    #chroma_db -> 작은 텍스트 조각
    #docstore -> 읽고 싶은 원본 전체 텍스트
    #-> 텍스트 조각으로 검색 -> 원본 전체 텍스트에서 결과 불러오기
    retriever = ParentDocumentRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        child_splitter=child_splitter,
        parent_splitter=None
    )

    return retriever


def create_chain(retriever):  # [수정됨] 인자 이름 변경
    # [수정됨] 모델 이름 확인 (gpt-5-mini -> gpt-4o-mini)
    llm = ChatOpenAI(model='gpt-5-mini', streaming=True)

    output_parser = StrOutputParser()

    # [수정됨] ParentDocumentRetriever는 이미 리트리버입니다. .as_retriever() 삭제!
    # retriever = vector_store.as_retriever()  <-- 이 줄 삭제

    prompt = ChatPromptTemplate.from_messages([
        ('system', '당신은 홍익대학교 학생들을 위한 친절한 비서 입니다. 사용자의 질문을 바탕으로 아래 참고 문서를 참고해서 답변합니다.'),
        MessagesPlaceholder(variable_name="history"),
        ('human', '질문 : {question}\n\n참고 문서\n{context}'),
    ])

    chain = prompt | llm | output_parser

    # retriever를 그대로 반환
    return chain, retriever


def get_answer(chain, retriever, query, history):
    context_docs = retriever.invoke(query)
    llm_answer = chain.invoke({
        "question": query,
        "context": '\n\n'.join([doc.page_content for doc in context_docs]),
        'history': history
    })
    return llm_answer


def get_answer_stream(chain, retriever, query, history):
  context_docs = retriever.invoke(query)
  for chunk in chain.stream({
    "question" : query,
    "context" : '\n\n'.join([doc.page_content for doc in context_docs]),
    'history' : history
    }):
    yield chunk
