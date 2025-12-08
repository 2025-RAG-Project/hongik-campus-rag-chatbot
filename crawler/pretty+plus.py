import json

in_path = "univ_board.jsonl"
out_path = "univ_board_pretty.json"

data = []
with open(in_path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        data.append(json.loads(line))

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


##final 파일
src_path = "univ_board_pretty.json"     # 원래 [ {...}, {...} ] 형태 파일
wrapped_path = "univ_board_prettier.json" # {"ie":[...]} 로 쓴 임시 파일

with open(src_path, "r", encoding="utf-8") as f:
    data_list = json.load(f)   # 리스트로 읽힘

wrapped = {"univ_Notice": data_list}

with open(wrapped_path, "w", encoding="utf-8") as f:
    json.dump(wrapped, f, ensure_ascii=False, indent=2)


wrapped_path = "univ_board_prettier.json"  # {"ie":[...]} 형태
other_path = "depart_Courses+Notice.json"         # 원래 {} 형태 json
output_path = "final_merged.json"       # 최종 결과

# 1) univ 래핑된 파일 읽기
with open(wrapped_path, "r", encoding="utf-8") as f:
    univ_obj = json.load(f)   # {"univ":[...]} 형태

# 2) 기존 {} json 읽기
with open(other_path, "r", encoding="utf-8") as f:
    base_obj = json.load(f)  # 예: {"meta":..., "data":[...]}

# 3) 두 객체를 합치기 (키 기준으로 병합)
#    같은 키가 없다고 가정하면 그냥 이렇게 해도 됨
merged = { **base_obj, **univ_obj }

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)



#######################################################################
import json

# 1. 기존 JSON 읽기
with open("final_merged.json", "r", encoding="utf-8") as f:
    data = json.load(f)

dept_notice = data.get("department_Notice", {})

# 2. 각 학과별로 구조 변환
for dept_name, item_list in dept_notice.items():
    # item_list는 원래 [~~~] 형태라고 가정
    if not isinstance(item_list, list):
        # 이미 변환된 형태거나 리스트가 아니면 스킵
        continue

    # item 내 요소 개수
    count = len(item_list)

    # date 최소/최대값 계산 (문자열 기준 비교)
    # date 키가 없는 경우는 제외
    dates = [item.get("date") for item in item_list if "date" in item]

    if dates:
        min_date = min(dates)
        max_date = max(dates)
    else:
        min_date = None
        max_date = None

    # 새로운 구조로 교체
    dept_notice[dept_name] = {
        "chunk_meta": {
            "count": count,
            "min_date": min_date,
            "max_date": max_date
        },
        "item": item_list
    }

# 3. 다시 data에 반영
data["department_Notice"] = dept_notice

# 4. 결과를 새로운 파일로 저장
with open("final_merged.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
