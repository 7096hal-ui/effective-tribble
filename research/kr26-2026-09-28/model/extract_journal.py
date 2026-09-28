#!/usr/bin/env python3
"""워크플로 journal.jsonl에서 에이전트 결과를 꺼내 data/<phase>/ 아래 JSON 파일로 저장한다.

사용: python3 extract_journal.py <phase_dir> <journal.jsonl> [<journal.jsonl> ...]
각 result는 label(예: 'B:SK하이닉스')을 파일명으로 쓴다.
"""
import json
import re
import sys
from pathlib import Path


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    labels = {}
    for jpath in sys.argv[2:]:
        for line in Path(jpath).read_text().splitlines():
            j = json.loads(line)
            if j.get("type") == "started":
                labels[j["key"]] = j.get("label") or j["agentId"]
            elif j.get("type") == "result":
                label = labels.get(j["key"], j.get("agentId", "unknown"))
                name = re.sub(r"[^\w가-힣.-]+", "_", label)
                (out / f"{name}.json").write_text(json.dumps(j["result"], ensure_ascii=False, indent=1))
                print("saved", name)


if __name__ == "__main__":
    main()
