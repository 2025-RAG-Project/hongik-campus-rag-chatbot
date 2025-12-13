import pandas as pd
import os
import shutil
import re
import ast
import pickle # 파이썬 객체 압축용
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# PDR 관련
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import LocalFileStore, EncoderBackedStore

load_dotenv()

CSV_PATH = "build_vector_db/data/df_json_to_csv.csv"
CHROMA_DIR = "build_vector_db/chroma_db" # 벡터(검색용) 저장경로
DOCSTORE_DIR = "build_vector_db/docstore" # 원본(참조용) 저장경로
COLLECTION_NAME = "hongik_data"


# 전처리 함수
def clean_text(t: str):
    if pd.isna(t): return "" # NaN 처리 추가
    t = str(t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    t = " ".join(t.split())
    return t

def normalize_date(date_str: str):
    if pd.isna(date_str): return "날짜미상"
    date_str = str(date_str)
    date_str = date_str.replace(".", "-")
    return date_str

# Chroma DB 구축 함수
def build_chroma_db():

    # 1. 기존 DB 삭제
    if os.path.exists(CHROMA_DIR): shutil.rmtree(CHROMA_DIR)
    if os.path.exists(DOCSTORE_DIR): shutil.rmtree(DOCSTORE_DIR)

    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["content"]).reset_index(drop=True)

    # 2. Splitter 설정

    # [Child] 검색용 작은 조각
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n\n", "\n", " ", ""] # 문단 -> 줄 -> 단어 순으로 split
    )

    # [Parent] 원본 저장용
    parent_splitter = None # 게시글 하나를 통째로 쓰기 위해

    # 3. 저장소 설정
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    # [Vector Store] 자식(벡터) 조각 저장 (Chroma)
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR
    )
    # [Doc Store] 부모(원본) 저장 (LocalFileStore)
    fs = LocalFileStore(DOCSTORE_DIR)
    docstore = EncoderBackedStore(
        store=fs,
        key_encoder=lambda x: x,
        value_serializer=pickle.dumps,
        value_deserializer=pickle.loads
    )
    
    # 4. PDR 생성
    retriever = ParentDocumentRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        child_splitter=child_splitter,
        parent_splitter=parent_splitter
    )

    # 5. 문서 객체 생성 (전처리 및 메타데이터)
    parent_docs = []
    for _, row in df.iterrows():
        title = clean_text(row["title"])
        raw_content = clean_text(row["content"])
        department = str(row["department"])
        
        # attachment 파싱
        has_attachment = False
        attachment_names = []
        raw_attachments = str(row["attachments"])
        if not pd.isna(raw_attachments):
            try:
                parsed_data = ast.literal_eval(str(raw_attachments))
                if isinstance(parsed_data, (dict,tuple)):
                    parsed_data = [parsed_data] if isinstance(parsed_data,dict) else list(parsed_data)

                seen_names = set()
                for item in parsed_data:
                    if isinstance(item, dict) and 'name' in item:
                        name = item['name']
                        if name not in seen_names:
                            attachment_names.append(name)
                            seen_names.add(name)
                if attachment_names:
                    has_attachment = True
            except (ValueError, SyntaxError):
                if isinstance(raw_attachments, str) and len(raw_attachments) > 5:
                    attachment_names.append(raw_attachments[:50] + "...")
                    has_attachment = True
        attachment_name_str = ", ".join(attachment_names) if attachment_names else "없음"    

        # index칼럼에서 notice_type 추출하기
        raw_index = str(row["index"]) # 'univ_notice_100'
        if "_" in raw_index:
            notice_type_code = raw_index.rsplit("_", 1)[0]
        else:
            notice_type_code = "general"
        type_mapping = {
            "course": "교과목/수강",
            "notice" : "학과공지",
            "univ_notice": "대학공지"
        }
        notice_type_kr = type_mapping.get(notice_type_code, notice_type_code)

        # Date 처리
        final_date = "날짜미상"
        course_id = "해당없음"
        if notice_type_code == "course":
            course_id = str(row["date"]).strip()
            final_date = "상시"
        else:
            final_date = normalize_date(row["date"])
            course_id = "해당없음"
        
        # 메타데이터 구성
        metadata = {
            "title": title, # 게시글 제목
            "url": row["url"], # 원본 링크
            "date": final_date, # 날짜
            "course_id": course_id, # 교과목 - 학수번호
            "department": department, # 학과명
            "notice_type": notice_type_kr, # 공지구분 (대학공지, 학과공지, 교과목/수강)
            "has_attachment": has_attachment, # 첨부파일 유무
            "attachment_name_str": attachment_name_str[:200], # 파일명 목록
            "original_id": raw_index # [관리용] 원본 게시글 id
        }
        
        doc = Document(page_content=raw_content, metadata=metadata)
        parent_docs.append(doc)
    

    print(f"처리할 원본 문서 수: {len(parent_docs)}")
    print("PDR 인덱싱 처리중 (자동으로 자식 쪼개기 및 저장)...")

    # openai 토큰수 제한 때문에 batch_size를 100으로 설정
    batch_size = 100 
    
    try:
        from tqdm import tqdm
        iterator = tqdm(range(0, len(parent_docs), batch_size), desc="Indexing")
    except ImportError:
        iterator = range(0, len(parent_docs), batch_size)

    for i in iterator:
        batch = parent_docs[i : i + batch_size]
        try:
            retriever.add_documents(batch, ids=None)
            # tqdm이 없을 때만 로그 출력
            if not isinstance(iterator, tqdm): 
                print(f"   - {i} ~ {i+len(batch)} 번째 문서 저장 완료")
        except Exception as e:
            print(f"⚠️ {i}번째 배치 처리 중 에러 발생: {e}")

    print("✅ PDR 구축 완료!")
    print(f"📂 벡터DB 위치: {CHROMA_DIR}")
    print(f"📂 문서저장소 위치: {DOCSTORE_DIR}")

if __name__ == "__main__":
    build_chroma_db()