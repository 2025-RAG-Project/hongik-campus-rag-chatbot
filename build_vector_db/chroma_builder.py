import pandas as pd
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
import os
import shutil
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

CSV_PATH = "build_vector_db/data/df_academic_board_master.csv"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "hongik_data"

# Chroma DB가 이미 존재하는 경우 삭제
if os.path.exists(CHROMA_DIR):
    shutil.rmtree(CHROMA_DIR)

def build_chroma_db():

    # 1. csv 파일 읽기
    df = pd.read_csv(CSV_PATH)

    # 2-1. search_text가 없는 row 제거
    df = df.dropna(subset=["search_text"]).reset_index(drop=True)

    # 2-2. search_text를 texts로 구성
    texts = df["search_text"].tolist()

    # 2-3. metadata 생성
    metadatas = []
    for _, row in df.iterrows():
        metadatas.append({
            "title": row["title"],
            "url": row["url"],
            "date": row["date"]
        })

    # 3. 임베딩 모델 준비
    emb = OpenAIEmbeddings(model="text-embedding-3-large")

    # 4. Chroma DB 생성
    vectorstore = Chroma.from_texts(
        texts=texts,
        embedding=emb,
        metadatas=metadatas,
        persist_directory=CHROMA_DIR,
        collection_name=COLLECTION_NAME   

    )

    print("Chroma Vector DB 구축 완료")
    print(f"총 저장된 벡터 수: {len(texts)}")

if __name__ == "__main__":
    build_chroma_db()