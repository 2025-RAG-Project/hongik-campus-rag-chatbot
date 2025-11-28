import pandas as pd
import os
import shutil
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
import re
from pathlib import Path

# ============================================================================
# 환경변수 로드
# ============================================================================
load_dotenv()

# ============================================================================
# 설정
# ============================================================================
# 프로젝트 루트 디렉토리 기준
BASE_DIR = Path(__file__).parent
CSV_PATH = BASE_DIR / "build_vector_db" / "data" / "df_academic_board_master.csv"
CHROMA_DIR = BASE_DIR / "build_vector_db" / "chroma_db_enhanced"
COLLECTION_NAME = "hongik_data"

# ============================================================================
# 텍스트 정제 함수
# ============================================================================
def clean_text(t: str) -> str:
    """HTML 태그, 개행, 연속 공백 제거"""
    t = str(t)
    # HTML 태그 제거
    t = re.sub(r"<[^>]+>", " ", t)
    # 개행/탭 제거
    t = t.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    # 연속 공백 제거
    t = " ".join(t.split())
    return t


def normalize_date(date_str: str) -> str:
    """날짜 형식을 yyyy-mm-dd로 통일"""
    date_str = str(date_str)
    date_str = date_str.replace(".", "-")
    return date_str


def classify_category(title: str, content: str = "") -> str:
    """제목과 내용을 기반으로 카테고리 자동 분류 (챗봇 카테고리에 맞춤)"""
    title_lower = title.lower()
    content_lower = content.lower() if content else ""
    text = title_lower + " " + content_lower
    
    # 1순위: 개설 과목 (수강신청, 강의 관련)
    course_keywords = ["수강신청", "개설과목", "강의", "교과목", "과목", "수업", "강좌", 
                       "수강", "시간표", "수강편람", "강의계획서", "교양", "전공"]
    if any(keyword in text for keyword in course_keywords):
        return "개설 과목"
    
    # 2순위: 학과 공지 (특정 학과/학부 언급)
    department_keywords = [
        "디자인", "미술", "예술", "건축", "컴퓨터", "소프트웨어", "AI", "인공지능",
        "공학", "경영", "경제", "법학", "사범", "인문", "자연과학", "사회과학",
        "학과", "학부", "전공", "과사무실", "학과사무실"
    ]
    if any(keyword in text for keyword in department_keywords):
        return "학과 공지"
    
    # 3순위: 학교 공지 (전체 대상 공지)
    school_keywords = ["전체", "공지", "알림", "안내", "공고", "모집", "선발", 
                       "지원", "신청", "접수", "학사", "등록", "장학", "학자금",
                       "대학원", "석사", "박사", "입학", "졸업", "학위"]
    if any(keyword in text for keyword in school_keywords):
        return "학교 공지"
    
    # 기본값: 학교 공지
    return "학교 공지"


def get_subcategory(title: str, content: str = "") -> str:
    """세부 카테고리 분류 (학과명 등)"""
    text = (title + " " + content).lower()
    
    # 학과/학부 세부 분류
    if any(keyword in text for keyword in ["디자인", "미술", "예술"]):
        return "디자인예술경영학부"
    elif "대학원" in text or "석사" in text or "박사" in text:
        return "대학원"
    elif "건축" in text:
        return "건축학부"
    elif any(keyword in text for keyword in ["컴퓨터", "소프트웨어", "AI", "인공지능"]):
        return "컴퓨터공학부"
    elif "공학" in text:
        return "공과대학"
    elif "경영" in text or "경제" in text:
        return "경영대학"
    else:
        return "일반"

# ============================================================================
# ChromaDB 구축
# ============================================================================
def build_chroma_db():
    """CSV 파일을 벡터 데이터베이스로 변환"""
    
    print("="*60)
    print("🚀 ChromaDB 구축 시작")
    print("="*60)
    
    # 1. 경로 검증
    if not CSV_PATH.exists():
        print(f"❌ CSV 파일을 찾을 수 없습니다: {CSV_PATH}")
        print(f"💡 파일을 다음 경로에 배치해주세요:")
        print(f"   {CSV_PATH}")
        return
    
    # 2. 기존 DB 삭제
    if CHROMA_DIR.exists():
        print(f"🗑️  기존 DB 삭제 중: {CHROMA_DIR}")
        shutil.rmtree(CHROMA_DIR)
    
    # 3. CSV 읽기
    print(f"\n📖 CSV 파일 읽는 중: {CSV_PATH}")
    try:
        df = pd.read_csv(CSV_PATH, encoding='utf-8')
    except UnicodeDecodeError:
        print("⚠️  UTF-8 인코딩 실패, cp949로 재시도...")
        df = pd.read_csv(CSV_PATH, encoding='cp949')
    
    # 필수 컬럼 확인
    required_columns = ['title', 'search_text', 'date', 'url']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"❌ 필수 컬럼이 없습니다: {missing_columns}")
        print(f"📋 현재 컬럼: {list(df.columns)}")
        return
    
    df = df.dropna(subset=["search_text"]).reset_index(drop=True)
    print(f"✅ 총 {len(df)}개의 데이터 로드됨")
    
    # 4. 데이터 변환
    print("\n🔄 데이터 변환 중...")
    texts = []
    metadatas = []
    
    for idx, row in df.iterrows():
        # 진행상황 표시
        if idx % 10 == 0:
            print(f"   처리 중: {idx}/{len(df)} ({idx/len(df)*100:.1f}%)")
        
        title = clean_text(row["title"])
        content = clean_text(row["search_text"])
        date = normalize_date(row["date"])
        
        # 메인 카테고리 (챗봇용)
        category = classify_category(title, content)
        
        # 서브 카테고리 (학과명 등)
        subcategory = get_subcategory(title, content)
        
        # 벡터화할 최종 텍스트
        final_text = (
            f"제목: {title}\n"
            f"날짜: {date}\n"
            f"카테고리: {category}\n"
            f"소속: {subcategory}\n"
            f"내용: {content}"
        )
        
        texts.append(final_text)
        metadatas.append({
            "title": title,
            "url": row["url"],
            "date": date,
            "category": category,        # 메인 카테고리 (학교 공지/학과 공지/개설 과목)
            "subcategory": subcategory   # 세부 카테고리 (학과명 등)
        })
    
    print(f"✅ 데이터 변환 완료: {len(texts)}개")
    
    # 카테고리 분포 출력
    from collections import Counter
    category_counts = Counter([m['category'] for m in metadatas])
    print("\n📊 카테고리 분포:")
    for cat, count in category_counts.items():
        print(f"   {cat}: {count}개")
    
    subcategory_counts = Counter([m['subcategory'] for m in metadatas])
    print("\n📊 학과/소속 분포:")
    for subcat, count in subcategory_counts.most_common(10):
        print(f"   {subcat}: {count}개")
    
    # 5. 벡터화 및 ChromaDB 생성
    print("\n🤖 OpenAI로 벡터화 중... (시간이 걸릴 수 있습니다)")
    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        
        # ChromaDB 폴더 생성
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        
        vectorstore = Chroma.from_texts(
            texts=texts,
            embedding=embeddings,
            metadatas=metadatas,
            persist_directory=str(CHROMA_DIR),
            collection_name=COLLECTION_NAME
        )
        
        print("\n" + "="*60)
        print("✅ ChromaDB 구축 완료!")
        print("="*60)
        print(f"📊 총 벡터 수: {len(texts)}")
        print(f"📁 저장 위치: {CHROMA_DIR}")
        print(f"📦 컬렉션명: {COLLECTION_NAME}")
        print("="*60)
        print("\n💡 다음 단계: streamlit run app.py")
        
    except Exception as e:
        print(f"\n❌ 벡터화 실패: {str(e)}")
        print("💡 OpenAI API 키를 확인해주세요:")
        print("   1. .env 파일이 있는가?")
        print("   2. OPENAI_API_KEY=sk-... 형식이 맞는가?")
        return


# ============================================================================
# 메인 실행
# ============================================================================
if __name__ == "__main__":
    try:
        build_chroma_db()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()