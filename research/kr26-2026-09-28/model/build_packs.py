#!/usr/bin/env python3
"""데이터 수집 결과(10/2)와 1단계 식별 결과(9/28)를 종목별 데이터 팩 data/pack/<code>.json으로 합친다."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 산업군 배정(총괄 조정): 이름 → (코드, 시장, 산업군)
UNIVERSE = {
    "SK하이닉스": ("000660", "KOSPI", "메모리·HBM밸류체인"),
    "삼성전자": ("005930", "KOSPI", "메모리·HBM밸류체인"),
    "한미반도체": ("042700", "KOSPI", "메모리·HBM밸류체인"),
    "와이씨": ("232140", "KOSDAQ", "메모리·HBM밸류체인"),
    "HPSP": ("403870", "KOSDAQ", "메모리·HBM밸류체인"),
    "이수페타시스": ("007660", "KOSPI", "AI하드웨어·디스플레이·검사장비·팹리스"),
    "사피엔반도체": ("452430", "KOSDAQ", "AI하드웨어·디스플레이·검사장비·팹리스"),
    "라온텍": ("418420", "KOSDAQ", "AI하드웨어·디스플레이·검사장비·팹리스"),
    "선익시스템": ("171090", "KOSDAQ", "AI하드웨어·디스플레이·검사장비·팹리스"),
    "고영": ("098460", "KOSDAQ", "AI하드웨어·디스플레이·검사장비·팹리스"),
    "현대차": ("005380", "KOSPI", "자동차·전장·SDV·부품"),
    "현대모비스": ("012330", "KOSPI", "자동차·전장·SDV·부품"),
    "현대오토에버": ("307950", "KOSPI", "자동차·전장·SDV·부품"),
    "화신": ("010690", "KOSPI", "자동차·전장·SDV·부품"),
    "퓨런티어": ("370090", "KOSDAQ", "자동차·전장·SDV·부품"),
    "삼성바이오로직스": ("207940", "KOSPI", "바이오·의료기기·진단"),
    "삼성에피스홀딩스": ("0126Z0", "KOSPI", "바이오·의료기기·진단"),
    "엘앤씨바이오": ("290650", "KOSDAQ", "바이오·의료기기·진단"),
    "바이오다인": ("314930", "KOSDAQ", "바이오·의료기기·진단"),
    "RFHIC": ("218410", "KOSDAQ", "우주항공·위성통신·5G6G·방산RF"),
    "인텔리안테크": ("189300", "KOSDAQ", "우주항공·위성통신·5G6G·방산RF"),
    "쎄트렉아이": ("099320", "KOSDAQ", "우주항공·위성통신·5G6G·방산RF"),
    "케이엠더블유": ("032500", "KOSDAQ", "우주항공·위성통신·5G6G·방산RF"),
    "서진시스템": ("178320", "KOSDAQ", "ESS·산업재·특수소재"),
    "한중엔시에스": ("107640", "KOSDAQ", "ESS·산업재·특수소재"),
    "에이치브이엠": ("295310", "KOSDAQ", "ESS·산업재·특수소재"),
}
ORDER = ["SK하이닉스", "삼성전자", "삼성바이오로직스", "삼성에피스홀딩스", "현대차", "현대모비스", "현대오토에버",
         "에이치브이엠", "사피엔반도체", "라온텍", "퓨런티어", "화신", "엘앤씨바이오", "바이오다인", "선익시스템",
         "서진시스템", "이수페타시스", "한중엔시에스", "RFHIC", "인텔리안테크", "쎄트렉아이", "HPSP",
         "케이엠더블유", "고영", "와이씨", "한미반도체"]


def main() -> None:
    v2 = {}
    for f in sorted((ROOT / "data/phase1/data_v2").glob("D_*.json")):
        d = json.loads(f.read_text())
        for s in d.get("stocks", []):
            v2[s["input_name"]] = s
    overrides = json.loads((ROOT / "data/final/p0_overrides.json").read_text())
    out = ROOT / "data/pack"
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for no, name in enumerate(ORDER, 1):
        code, market, group = UNIVERSE[name]
        b_path = ROOT / f"data/phase1/identify/B_{name}.json"
        b = json.loads(b_path.read_text()) if b_path.exists() else None
        b_useful = b is not None and b.get("confidence") != "낮음"
        new = v2.get(name)
        pack = {
            "no": no, "name": name, "code": code, "market": market, "group": group,
            "p0_krw": new.get("close") if new else None,
            "p0_date": new.get("close_date") if new else None,
            "p0_basis": "데이터 수집 에이전트가 확인한 KRX 정규장 종가(latest_2026_10_02.price_note 참조)",
            "latest_2026_10_02": new,
            "phase1_2026_09_28": b if b_useful else None,
            "note": "latest_2026_10_02는 10/2 기준 데이터 수집 결과, phase1_2026_09_28은 9/28 식별 에이전트 결과(검색이 이뤄진 종목만).",
        }
        if name in overrides:
            o = overrides[name]
            pack.update({"p0_krw": o["p0"], "p0_date": o["date"], "p0_basis": "총괄 조정 지정: " + o["basis"],
                         "p0_confidence": o["confidence"]})
        (out / f"{code}.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1))
        index.append({"no": no, "name": name, "code": code, "market": market, "group": group,
                      "p0": pack["p0_krw"], "p0_date": pack["p0_date"], "has_0928": b_useful})
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    for r in index:
        print(r)


if __name__ == "__main__":
    main()
