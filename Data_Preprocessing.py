import pandas as pd
import json

def create_rag_dataframe_from_json(file_path: str, folder_name: str) -> pd.DataFrame:
    
    # 1. JSON 파일 로드
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    board_data = data[folder_name]
    df = pd.DataFrame(board_data)

    
    # 2. 첨부파일 정보를 텍스트로 변환하는 내부 함수
    def format_attachments_for_rag(attachments):
        if not attachments:
            return ""
        
        attachment_texts = []
        for att in attachments:
            # 파일 이름과 URL을 포함하여 하나의 정보를 구성합니다.
            text = f"[첨부파일명: {att.get('name', '이름 없음')}, URL: {att.get('url', 'URL 없음')}]"
            attachment_texts.append(text)
            
        return " ".join(attachment_texts)

    
    # 3. 첨부파일 정보에 대한 텍스트 컬럼 생성
    if 'attachments' in df.columns:
        df['attachment_text'] = df['attachments'].apply(format_attachments_for_rag)
    else:
        df['attachment_text'] = ""

    
    # 4. 최종 검색용 텍스트 컬럼 ('search_text') 생성
    # 필요한 모든 정보를 하나의 검색 문서로 통합합니다.
    df['search_text'] = (
        df['title'] + 
        " [날짜: " + df['date'] + "] " + 
        df['content'] + 
        " [첨부파일 정보: " + df['attachment_text'] + "]"
    )

    
    # 5. 불필요한 중간 컬럼 삭제 및 최종 DataFrame 반환
    df_preprocessed = df.drop(columns=['attachments', 'attachment_text'], errors='ignore')
    return df_preprocessed
