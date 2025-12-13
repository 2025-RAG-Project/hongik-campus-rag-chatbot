import json
import pandas as pd

def load_data(file_path):
    """JSON 파일을 불러오는 함수"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_attachments(item):
    """첨부파일 리스트를 문자열로 변환하는 헬퍼 함수"""
    att_list = item.get('attachments', [])
    if att_list:
        return ', '.join([str(x) for x in att_list])
    return ''

def process_courses(data):
    """학과 강좌(department_Courses) 데이터를 처리하여 DataFrame 반환"""
    rows = []
    # 데이터 추출
    for dept_name, content in data.get('department_Courses', {}).items():
        items = content.get('item', [])
        for item in items:
            rows.append({
                'department': dept_name,
                'index': item.get('index'),
                'text': item.get('text')
            })

    if not rows:
        return pd.DataFrame()

    df_courses = pd.DataFrame(rows)
    
    # ID 생성
    df_courses['index'] = [f'course_{i+1}' for i in range(len(df_courses))]

    # 텍스트 전처리 (제목, 날짜, 내용 분리)
    split_data = df_courses['text'].str.split('\n')
    df_courses['title'] = split_data.str[0]
    df_courses['date'] = split_data.str[1]
    
    # 내용은 나머지 줄을 다시 합쳐서 저장 (CSV 저장 시 리스트보다 문자열이 안전함)
    df_courses['content'] = split_data.str[2:].apply(lambda x: '\n'.join(x) if isinstance(x, list) else '')
    
    df_courses['url'] = ''
    df_courses['attachments'] = ''
    
    # 불필요한 원본 텍스트 컬럼 삭제
    df_courses.drop(columns=['text'], inplace=True)
    
    return df_courses

def process_dept_notices(data):
    """학과 공지사항(department_Notice) 데이터를 처리하여 DataFrame 반환"""
    rows = []
    for dept_name, content in data.get('department_Notice', {}).items():
        items = content.get('item', [])
        if items:
            for item in items:
                rows.append({
                    'index': '', # 나중에 일괄 부여
                    'department': dept_name,
                    'date': item.get('date'),
                    'title': item.get('title'),
                    'url': item.get('url'),
                    'attachments': parse_attachments(item),
                    'content': item.get('content')
                })
    
    df_notice = pd.DataFrame(rows)
    
    if not df_notice.empty:
        df_notice['index'] = [f'notice_{i+1}' for i in range(len(df_notice))]
        
    return df_notice

def process_univ_notices(data):
    notice_rows = []
    target_list = []

    # 1. data['univ_Notice'] 리스트를 돌면서 'items' 키가 있는 딕셔너리 찾기
    if 'univ_Notice' in data:
        for entry in data['univ_Notice']:
            if 'items' in entry:
                target_list = entry['items']
                break  # 찾았으면 반복문 종료

    # 2. 찾은 item 리스트 순회
    if target_list:
        for item in target_list:
            
            # attachments (리스트 -> 문자열 변환)
            att_list = item.get('attachments', [])
            if att_list:
                attachments_str = ', '.join([str(x) for x in att_list])
            else:
                attachments_str = ''

            row = {
                'date': item.get('date'),
                'title': item.get('title'),
                'url': item.get('url'),
                'attachments': attachments_str,
                'content': item.get('content')
            }
            notice_rows.append(row)

    # 3. 데이터프레임 생성
    df_univ = pd.DataFrame(notice_rows)
    
    # 데이터가 비어있지 않다면 후처리 진행
    if not df_univ.empty:
        # 4. 인덱스 ID 추가 (univ_notice_1, univ_notice_2 ...)
        df_univ['index'] = [f'univ_notice_{i+1}' for i in range(len(df_univ))]

        # 5. 컬럼 순서 정리 (ID를 맨 앞으로)
        cols = ['index'] + [c for c in df_univ.columns if c != 'index']
        df_univ = df_univ[cols]

        # 6. department 컬럼 생성 (요청하신 로직 그대로)
        departments = []
        for content in df_univ['content']:
            split_data = content.split('\n')
            # 두 번째 줄(인덱스 1)을 이용하여 부서명 생성
            dept_result = f"대학전체_{split_data[1]}" 
            departments.append(dept_result)

        # 7. department 컬럼 할당
        df_univ['department'] = departments

    return df_univ

def main():
    # 1. 파일 경로 설정 및 로드
    file_path = '/content/final_merged.json'
    data = load_data(file_path)
    print("데이터 로드 완료")

    # 2. 각 섹션별 데이터프레임 변환
    df_courses = process_courses(data)
    df_notice = process_dept_notices(data)
    df_univ = process_univ_notices(data)

    print(f"강좌 데이터: {len(df_courses)}건")
    print(f"학과 공지: {len(df_notice)}건")
    print(f"학교 공지: {len(df_univ)}건")

    # 3. 데이터프레임 병합 (공통 컬럼 기준)
    # 컬럼 순서를 맞추기 위해 reindex 혹은 concat 시 자동 정렬 이용
    all_dfs = [df_courses, df_notice, df_univ]
    df_final = pd.concat(all_dfs, axis=0, ignore_index=True, sort=False)

    # index 컬럼을 맨 앞으로 오게 정렬
    if 'index' in df_final.columns:
        cols = ['index'] + [c for c in df_final.columns if c != 'index']
        df_final = df_final[cols]

    # 4. CSV 저장
    output_path = 'df_json_to_csv.csv'
    df_final.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"파일 저장 완료: {output_path}")

    # 결과 미리보기
    return df_final.head()

# 실행
if __name__ == "__main__":
    df_result = main()
