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
other_path = "courses_departNotice.json"         # 원래 {} 형태 json
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