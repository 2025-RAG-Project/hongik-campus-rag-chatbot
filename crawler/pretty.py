import json

in_path = "academic_board.jsonl"
out_path = "academic_board_pretty.json"

data = []
with open(in_path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        data.append(json.loads(line))

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
