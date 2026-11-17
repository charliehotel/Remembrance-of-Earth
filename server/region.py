"""대상 동네 설정. config/region.json 한 파일에 동네 이름·검색어·지도 중심을 모아 두고, 서버와 스크립트가 여기서 읽는다.
다른 동네로 옮길 때는 이 파일을 바꾸고 데이터 파이프라인(README '다른 동네에 적용하기')을 돌린다."""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "config/region.json"
R = json.loads(CONF.read_text(encoding="utf-8"))
ID, GU, DONG = R["id"], R["gu"], R["dong"]
LOCAL_RE = re.compile("|".join(map(re.escape, R["local_words"])))
GU_STEM = GU.replace("구", "")            # 주소에 '서대문'이 들어 있는지 볼 때 쓴다
def in_region(ldong, addr):
    """법정동명·지번주소가 이 동네인가. 주소가 있으면 구 이름까지 맞아야 한다(같은 이름의 다른 구 동 제외)."""
    return DONG in f"{ldong} {addr}" and (not addr or GU_STEM in addr)
