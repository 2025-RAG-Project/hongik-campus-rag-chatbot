import pandas as pd
import os
import shutil
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
import re

load_dotenv()

CSV_PATH = "build_vector_db/data/df_academic_board_master.csv"
CHROMA_DIR = "build_vector_db/chroma_db_enhanced" # 경로 명시
COLLECTION_NAME = "hongik_data"

# csv파일의 search_text 컬럼을 벡터화하여 chromadb에 저장
# search_text에 대해서 주변 searching이 쉽도록 전처리 진행

# === 텍스트 정제 함수 ===
def clean_text(t: str):
    t = str(t)

    # HTML 태그 제거 (대비용)
    t = re.sub(r"<[^>]+>", " ", t)

    # 개행/탭 제거
    t = t.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # 연속 공백 제거
    t = " ".join(t.split())

    return t



#  === 날짜 정규화: yyyy-mm-dd ===
def normalize_date(date_str: str):
    date_str = str(date_str)
    date_str = date_str.replace(".", "-")
    return date_str


# === Chroma DB 구축 ===
def build_chroma_db():

    # 기존 DB가 있다면 삭제하고 진행
    if os.path.exists(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR)

    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["search_text"]).reset_index(drop=True)

    texts = []
    metadatas = []

    for _, row in df.iterrows():

        title = clean_text(row["title"])
        content = clean_text(row["search_text"])
        date = normalize_date(row["date"])

        # 학부/카테고리 추출 가능하면 넣어주기 (없으면 빈 값)
        # TODO : 학과명 추가(학부)
        category = ""
        if "디자인" in title:
            category = "디자인예술경영학부"
        elif "대학원" in title:
            category = "대학원"
        # (룰 추가하기)

        # 최적의 벡터 텍스트 구성
        final_text = (
            f"제목: {title}\n"
            f"날짜: {date}\n"
            f"카테고리: {category}\n"
            f"내용: {content}"
        )

        texts.append(final_text)

        metadatas.append({
            "title": title,
            "url": row["url"],
            "date": date,
            "category": category
        })

    # 임베딩 모델
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    # Chroma 구축
    vectorstore = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        persist_directory=CHROMA_DIR,
        collection_name=COLLECTION_NAME
    )

    print("Chroma Vector DB (Enhanced) 구축 완료")
    print(f"총 벡터 수: {len(texts)}")
    print(f"저장 위치: {CHROMA_DIR}")


if __name__ == "__main__":
    build_chroma_db()