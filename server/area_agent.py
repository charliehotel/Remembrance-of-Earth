"""골목의 연대기: 선택 영역 리포트에 대한 후속 질문 답변(AI).

리포트 자체는 AI 없이 server/analysis.py 가 만든다. 사용자가 영역을 고른 뒤 질문을 덧붙였을 때만 여기로 온다.
  1. (질문이 '왜·이유'를 묻는 경우에만) 웹 검색(Liner Search)으로 외부 맥락을 찾는다. 계산 수치와 섞지 않고 W 근거로 따로 둔다.
  2. 모델(Liner Model)이 질문의 관점(focus)을 고르고, 리포트의 사실 목록(F)과 웹 근거(W)만으로 2~4문장 답을 쓴다.
  3. 코드가 답 속 숫자를 사실 목록·웹 근거·질문의 숫자와 대조해, 어긋난 문장은 버린다.
"""
import re
import analysis, liner, region

REL = region.LOCAL_RE   # 검색 결과가 이 일대 이야기인지 가르는 최소 기준
WHY = re.compile(r"왜|이유|때문|원인|배경|무슨 일|어떻게 된|영향")
FOCUS = ["overview", "composition", "survival", "history", "none"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["focus", "answer", "used_facts", "web_ids"],
          "properties": {"focus": {"type": "string", "enum": FOCUS}, "answer": {"type": "string"},
                         "used_facts": {"type": "array", "items": {"type": "string"}}, "web_ids": {"type": "array", "items": {"type": "string"}}}}

SYSTEM = (f"너는 {region.R['area_intro']}의 인허가 기록과 로드뷰 간판 관측으로 만든 '골목의 연대기' 리포트를 설명하는 분석 도우미다. "
          "사용자가 고른 영역의 계산 결과(사실 F0, F1…)와, 있으면 웹 근거(W0…)가 주어진다. 규칙: "
          "(1) 사실 목록에서 답할 수 있는 질문(업종 변화, 영업 기간, 자리 교체, 업종 구성 등)에는 반드시 구체적인 수치로 답한다. '알 수 없다'·'단정할 수 없다'로 시작하거나 답을 피하지 않는다. "
          "통계가 정확하지 않은 점은 답 끝에 한 문장으로 덧붙인다(기록 기준, 범위로 표시, 관측 없는 업소가 많음, 표본 수). 증감 범위가 0을 포함하지 않으면 방향이 확실하다고 말하고, 0을 포함하면 방향이 불확실하다고 말한다. "
          "'최근 10년'은 2015→2025 변화, '최근 20년'은 2005→2025 변화 사실을 쓴다. 가장 크게 변한 업종은 사실에 적힌 '가장 크게 는/준 업종'과 변화 범위를 근거로 말한다. "
          "(2) 숫자는 사실 목록에 적힌 것만, 적힌 그대로(범위는 범위로) 쓴다. 새 수치를 만들거나 반올림·평균·합산하지 않는다. 표본 부족이라고 된 항목은 수치를 말하지 않고 표본이 부족하다고 한다. "
          "(3) 원인은 웹 근거(W)가 있을 때만, 그 근거를 인용해 '~라는 보도가 있다'처럼 쓴다. 원인을 묻지 않은 질문에서는 웹 근거나 원인을 언급하지 않는다. 원인을 물으면 먼저 사실 목록의 변화를 수치로 한두 문장 말한 뒤, 웹 근거가 있으면 그 원인을 '~라는 보도가 있다'로 덧붙인다. 근거가 없으면 이유는 확인되지 않았다고 한다. "
          "(4) 예측·창업 추천·매출·임대료·유동인구는 데이터에 없으니 답할 수 없다고 하고, 대신 답할 수 있는 것을 제안한다. 사실 목록으로 답할 수 있는 질문에는 이 규칙을 쓰지 않는다. "
          "(5) focus는 질문이 가장 가까운 관점 하나: composition(업종 구성·업종별 증감·시기별 어떤 업종이 많았나·상권이 왜 변했나), survival(업종별 영업 기간·생존율·얼마나 버텼나), "
          "history(가게 교체 주기·자리가 바뀐 횟수·폐업 뒤 다음 개업까지의 공백·공실), overview(업소 수·영업 중/폐업 수·근거 등급·데이터 신뢰도·영역 전체 요약). "
          "none은 데이터에 없는 질문(예측·추천·매출·임대료·유동인구·맛·날씨 등)일 때만 쓴다. 업소 수나 근거 등급을 묻는 질문은 none이 아니라 overview다. "
          "(6) answer는 한국어 2~4문장. used_facts에는 근거로 쓴 F id, web_ids에는 인용한 W id만 넣는다.")

NUM = re.compile(r"\d+(?:\.\d+)?")
LIMIT_WORDS = re.compile(r"기록 기준|범위|관측|표본|한계|불확실|추정|가정")

def _nums(text): return set(NUM.findall(text))

def verify(answer, allowed):
    """문장 단위로 숫자를 검사해, 허용되지 않은 숫자가 든 문장은 버린다. 반환: (남긴 답, 버린 문장 수, 전체 문장 수)"""
    sents = re.findall(r"(?:[^.!?。]|(?<=\d)\.(?=\d))+(?:[.!?。]+|$)", answer.replace("\n", " "))   # 소수점(7.3)에서는 문장을 끊지 않는다
    keep, dropped, total = [], 0, 0
    for s in (x.strip() for x in sents if x.strip()):
        total += 1
        if _nums(s) - allowed: dropped += 1
        else: keep.append(s)
    return " ".join(keep), dropped, total

def ask(rep, text):
    fx = analysis.facts(rep)
    if not fx: return {"answer": "이 영역에는 조사된 업소 기록이 없어 답할 내용이 없습니다.", "focus": "none", "web": {"used": False, "reason": "자료 없음"}, "dropped": 0, "model": "", "cost_usd": 0}
    MDL, SCH = ("Liner Model", "Liner Search") if liner.provider() == "liner" else ("테스트용 프록시 모델", "테스트용 프록시 검색")
    web = {"used": False, "n": 0, "label": SCH, "reason": "원인을 묻는 질문이 아니라 웹 검색은 쓰지 않음", "evidence": []}
    if WHY.search(text):
        try:
            res = liner.search(f'{region.R["web_context"]} {text}'[:120], 5)
        except Exception as e:
            res = []; web["reason"] = f"웹 검색 실패({str(e)[:60]})"
        kept = [x for x in res if REL.search(f"{x.get('title', '')} {x.get('desc', '')}")]   # 신촌과 무관한 결과는 근거로 쓰지 않는다
        web.update(used=True, n=len(kept), found=len(res), reason=f"원인을 묻는 질문이라 외부 보도·자료를 찾음(검색 {len(res)}건 중 신촌 일대 관련 {len(kept)}건만 사용)")
        for i, x in enumerate(kept): x["id"] = f"W{i}"; web["evidence"].append(x)
    ev = web["evidence"]
    user = (f"질문: {text}\n\n[리포트 사실]\n" + "\n".join(f"{i} | {t}" for i, t in fx) +
            "\n\n[웹 근거]\n" + ("\n".join(f"{e['id']} | {e['title'][:80]} | {e['desc'][:200]} | {e['date']}" for e in ev) if ev else ("(웹 근거를 찾지 못함)" if web["used"] else "(웹 검색 안 함)")))
    res, model, cost = liner.chat_json(SYSTEM, user, SCHEMA, "area_answer", 900)
    allowed = _nums(text)
    for _, t in fx: allowed |= _nums(t)
    ok_w = {e["id"] for e in ev}
    web_ids = [i for i in res["web_ids"] if i in ok_w]
    for e in ev:
        if e["id"] in web_ids: allowed |= _nums(e["title"] + " " + e["desc"])
    answer, dropped, total = verify(res["answer"], allowed)
    if not answer: answer = "계산된 표를 기준으로 직접 확인해 주세요. 답변 속 숫자를 검증하지 못해 설명을 생략했습니다."
    limit_added = False
    if res["focus"] != "none" and NUM.search(answer) and not LIMIT_WORDS.search(answer):   # 모델이 한계 언급을 빠뜨리면 코드가 계산값으로 덧붙인다
        n_rec = rep["overview"]["evidence"].get(analysis.EV_REC, 0)
        answer += f" 이 수치는 기록 기준이며, 폐업 시점이 불확실한 '기록만' 업소 {n_rec}곳은 범위로 계산했습니다."; limit_added = True
    ok_f = {i for i, _ in fx}
    return {"answer": answer, "focus": res["focus"], "used_facts": [i for i in res["used_facts"] if i in ok_f], "web_ids": web_ids,
            "web": {**web, "label": SCH}, "dropped": dropped, "sentences": total, "limit_added": limit_added, "raw": res["answer"], "model": model, "cost_usd": round(cost, 5) if cost else 0, "mdl": MDL}
