"""보고서 속 인용을 원문과 기계적으로 대조한다.

사용: python3 run/check_quotes.py 파일1.md [파일2.md ...]

- 따옴표(" " “ ” ‘ ’ ' ')와 낫표(「 」) 안의 문자열을 인용 후보로 뽑는다.
- 원문의 행 경계는 보고서에서 ' / ' 또는 '/' 로 표시될 수 있으므로 그 경우도 허용한다.
- 생략 부호(…, ...)로 이어 붙인 인용은 조각별로 확인한다.
- 판정: OK(원문에 그대로 있음) / OK-slash(행 경계를 / 로 표시) / PART(생략 조각은 모두 있음)
        / MISS(원문에 없음) / TITLE(제목·인용 출처 표기)
- 규약 검사: 인용 1회 120자 이내, 원문 2행 이내.
MISS는 '오류 확정'이 아니라 사람이 확인할 의심 목록이다(요약·가상 변형일 수 있음).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = {
    "건": (ROOT / "originals/poem_A.txt").read_text(encoding="utf-8"),
    "여": (ROOT / "originals/poem_B.txt").read_text(encoding="utf-8"),
}
TITLES = {"건축", "여행의 미래", "파이드로스"}
PAIRS = [("“", "”"), ("‘", "’"), ("「", "」"), ('"', '"'), ("'", "'")]


def candidates(text):
    out = []
    for o, c in PAIRS:
        pat = re.escape(o) + r"([^" + re.escape(o + c) + r"\n]{1,400}?)" + re.escape(c)
        for m in re.finditer(pat, text):
            out.append((m.start(), m.group(1)))
    out.sort()
    return out


def line_span(src, q):
    i = src.find(q)
    if i < 0:
        return None
    return src[i:i + len(q)].count("\n") + 1


def check(q):
    if q in TITLES:
        return "TITLE", None, None
    for key, src in SRC.items():
        if q in src:
            return "OK", key, line_span(src, q)
        for sep in (" / ", "/", " // "):
            if sep in q:
                q2 = q.replace(sep, "\n")
                if q2 in src:
                    return "OK-slash", key, line_span(src, q2)
    pieces = [p.strip(" ,") for p in re.split(r"…+|\.\.\.(?!\.)|\(…\)|\[…\]", q) if p.strip(" ,")]
    if len(pieces) > 1:
        for key, src in SRC.items():
            norm = lambda p: p.replace(" / ", "\n").replace("/", "\n")
            if all(p in src or norm(p) in src for p in pieces):
                return "PART", key, None
    return "MISS", None, None


def main(paths):
    total_bad = 0
    for p in paths:
        text = pathlib.Path(p).read_text(encoding="utf-8")
        rows = []
        for pos, q in candidates(text):
            if len(q.strip()) < 2:
                continue
            status, key, span = check(q)
            flags = []
            if status != "TITLE" and len(q) > 120:
                flags.append(f"LEN>{120}({len(q)})")
            if span and span > 2:
                flags.append(f"LINES>{2}({span})")
            rows.append((status, key, q, flags))
        bad = [r for r in rows if r[0] == "MISS" or r[3]]
        total_bad += len(bad)
        counts = {}
        for r in rows:
            counts[r[0]] = counts.get(r[0], 0) + 1
        print(f"== {p}: {counts}")
        for status, key, q, flags in rows:
            if status == "MISS" or flags:
                print(f"   [{status}{'/' + key if key else ''}] {' '.join(flags)} «{q}»")
    return total_bad


if __name__ == "__main__":
    main(sys.argv[1:])
