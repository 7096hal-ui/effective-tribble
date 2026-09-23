# poetry-review — 「건축」·「여행의 미래」 병렬 에이전트 비교 비평

**먼저 읽을 것: [`final_report.md`](final_report.md)**

| 파일 | 내용 |
|---|---|
| `originals/poem_A.txt`, `poem_B.txt` | 원문. 수정 없이 옮겼고 로컬에서는 읽기 전용으로 두었다. 작품 A는 「건축」, 작품 B는 「여행의 미래」다. |
| `originals/numbered_*.txt` | 참고용 행 번호 사본. 위치 표지는 [건NN], [여NN]이다. |
| `criteria.md` | 본평가 전에 고정한 비교 규약이다(축 A~F, 기본 가중치). |
| `reports/reading_A.md`, `reading_B.md` | 1차 독립 정독 보고서. |
| `reports/judge_1.md`, `judge_2.md` | 1차 독립 비교 심사 보고서. 두 심사자는 작품 제시 순서를 서로 반대로 받았다. |
| `issues.md` | 쟁점 대조(6개)와 인용·사실 대조. |
| `reports/hypothesis_A.md`, `hypothesis_B.md`, `evidence_audit.md` | 2차 작업: 양쪽 우위 가설 검사와 근거 감사. |
| `reports/reread/T*.md` | 표적 재독 1회(축 B·C·E, 제시 순서 반전). |
| `synthesis.md` | 조정자 종합: 반론 처리와 최종 축별 판단표. |
| `revisions.md` | 수정 이력 R1~R8. 판정 부호가 역전된 경위도 포함한다. |
| `robustness.md` | 가중치 설정 14개, 축 판단 경계, 대안 독해, 중복 반영 가능성 점검. |
| `faults.md` | 시별 결함(등급·철회 조건). |
| `audit.md` | 자기 판정 감사. |
| `run_log.md` | 실행 형태, 입력 격리, 도구 사용 검증 기록. |
| `run/` | 프롬프트 생성기, 실제로 보낸 프롬프트, 워크플로 스크립트, 원시 결과 JSON, 인용 대조기, 강건성 계산기. |

`*.original_overlimit.md`는 분량 상한을 넘은 원본 보고서다. 판정에는 압축본을 썼고, 원본은 보존용으로 남겨 두었다.
