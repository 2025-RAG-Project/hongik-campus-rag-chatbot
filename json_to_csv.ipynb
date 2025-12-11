#---------------import json file--------------------
import json

file_path='/content/final_merged.json'
with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)


#-----------------'department_Courses' -> 'df_courses'---------------
import pandas as pd

# 1. 데이터를 담을 빈 리스트 생성
rows = []

# 2. 이중 반복문으로 데이터 추출
for dept_name, content in data['department_Courses'].items():
    # 각 학과의 item 리스트를 하나씩 꺼냄
    items = content['item'] 
    
    for item in items:
        # 각 행(row)을 딕셔너리로 구성
        row = {
            'department': dept_name,  # 학과명
            'index': item['index'],   # item 안의 index
            'text': item['text']      # item 안의 text
        }
        rows.append(row)

# 3. 리스트를 데이터프레임으로 변환 (컬럼 자동 생성)
df_courses = pd.DataFrame(rows)
df_courses['index']=[f'course_{i+1}' for i in range(len(df_courses))]

# 4. 줄바꿈(\n)을 기준으로 텍스트를 분리
split_data = df_courses['text'].str.split('\n')

# 5. 첫 번째 줄(인덱스 0) -> title 컬럼
df_courses['title'] = split_data.str[0]

# 6. 두 번째 줄(인덱스 1) -> date 컬럼
df_courses['date'] = split_data.str[1]

df_courses['content']=split_data.str[2:]

df_courses['url']=''
df_courses['attachments']=''

df_courses.drop(columns=['text'], inplace=True)


#-----------------'department_Notice' -> 'df_courses'---------------
notice_rows = []

# 1. 모든 학과 공지사항 순회
for dept_name, content in data['department_Notice'].items():
    
    # item이 존재하는지 확인
    if 'item' in content and content['item']:
        for item in content['item']:
            
            # (1) attachments 리스트를 문자열로 합치기
            att_list = item.get('attachments', [])
            if att_list:
                attachments_str = ', '.join([str(x) for x in att_list])
            else:
                attachments_str = ''

            # (2) 행 데이터 생성
            row = {
                'department': dept_name,       
                'date': item.get('date'),      
                'title': item.get('title'),    
                'url': item.get('url'),        
                'attachments': attachments_str, 
                'content': item.get('content') 
            }
            notice_rows.append(row)

# 2. 데이터프레임 생성
df_notice = pd.DataFrame(notice_rows)

# 3. [추가] 'index' 컬럼 생성 (notice_1, notice_2 ...)
# 0부터 시작하는 인덱스(i)에 1을 더해서 생성합니다.
df_notice['index'] = [f'notice_{i+1}' for i in range(len(df_notice))]

# 4. [추가] 'index'를 맨 앞 컬럼으로 순서 변경
cols = ['index'] + [c for c in df_notice.columns if c != 'index']
df_notice = df_notice[cols]


#-----------------'univ_Notice' -> 'df_courses'---------------
notice_rows = []
target_list = []

# 1. data['univ_Notice'] 리스트를 돌면서 'items' 키가 있는 딕셔너리 찾기
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

# 4. 인덱스 ID 추가 (notice_1, notice_2 ...)
df_univ['index'] = [f'univ_notice_{i+1}' for i in range(len(df_univ))]

# 5. 컬럼 순서 정리 (ID를 맨 앞으로)
cols = ['index'] + [c for c in df_univ.columns if c != 'index']
df_univ = df_univ[cols]
df_univ['department'] = '대학 전체'


#---------------df merging--------------------
df_json_to_csv = pd.concat([df_courses, df_notice, df_univ], axis=0)


#---------------df store to csv--------------------
df_json_to_csv.to_csv('df_json_to_csv.csv', index=False)
