"""소상공인시장진흥공단 상가(상권)정보 분기 스냅샷(전국·서울 CSV 또는 ZIP)에서 창천동 업소만 뽑아 data/semas/ 에 쓴다.

입력: data/raw/semas_history/ (또는 data/raw/) 안의 파일. 이름에 기준일(YYYYMMDD 또는 YYYYMM)이 들어 있어야 한다.
  예) 소상공인시장진흥공단_상가(상권)정보_20160930.csv, 상가(상권)정보_20151231.zip, ..._서울_202610.csv
출력: data/semas/changcheon_YYYYMMDD.csv (작아서 저장소에 올린다. 원본은 data/raw/ 라서 올라가지 않는다)
  열: asof, id, name, branch, jibun, floor, lcls, mcls, scls, lon, lat
옛 스냅샷은 열 이름·인코딩이 다를 수 있어 몇 가지 후보를 시도한다.
사용: python3 scripts/extract_semas.py [파일 또는 폴더 ...]
"""
import csv, io, re, sys, zipfile, unicodedata, calendar
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/semas"; OUT.mkdir(exist_ok=True)
csv.field_size_limit(10 ** 8)

def asof_of(name):
    n = unicodedata.normalize("NFC", name)
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", n)
    if m: return m.group(1)
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", n)
    if m:                                   # 월 기준 파일은 그 달 말일로 본다
        y, mo = int(m.group(1)[:4]), int(m.group(1)[4:]); return f"{y}{mo:02d}{calendar.monthrange(y, mo)[1]:02d}"
    return None

COLS = {"id": ["상가업소번호", "상가업소 번호"], "name": ["상호명", "상호"], "branch": ["지점명"], "ldong": ["법정동명", "법정동"], "jibun_addr": ["지번주소", "지번 주소"],
        "bun": ["지번본번지"], "bu": ["지번부번지"], "floor": ["층정보", "층"], "lcls": ["상권업종대분류명", "상권업종대분류"], "mcls": ["상권업종중분류명", "상권업종중분류"],
        "scls": ["상권업종소분류명", "상권업종소분류"], "lon": ["경도"], "lat": ["위도"]}

def open_text(path):
    """(이름, 새 바이너리 스트림을 여는 함수) 목록. 인코딩을 바꿔 다시 읽을 수 있도록 매번 새로 연다."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z: names = sorted(n for n in z.namelist() if n.lower().endswith(".csv"))
        for n in names: yield n, (lambda n=n: zipfile.ZipFile(path).open(n))
    else:
        yield path.name, (lambda: open(path, "rb"))

def extract(path):
    asof = asof_of(path.name)
    if not asof: print(f"  건너뜀(기준일을 알 수 없음): {path.name}"); return
    out = []
    for member, opener in open_text(path):
        res = None
        for enc in ("utf-8-sig", "cp949"):
            n_before = len(out)
            try:
                tw = io.TextIOWrapper(opener(), encoding=enc, newline=""); rd = csv.reader(tw); head = [h.strip() for h in next(rd)]
                idx = {k: next((head.index(c) for c in cands if c in head), None) for k, cands in COLS.items()}
                if idx["name"] is None: continue
                for r in rd:
                    g = lambda k: (r[idx[k]].strip() if idx[k] is not None and idx[k] < len(r) else "")
                    ld, addr = g("ldong"), g("jibun_addr")
                    if "창천동" not in (ld + " " + addr): continue
                    if "서대문" not in addr and addr: continue          # 같은 이름의 다른 동 제외(주소가 있을 때)
                    jb = ""
                    if g("bun"): jb = str(int(g("bun") or 0)) + (f"-{int(g('bu'))}" if int(g("bu") or 0) else "")
                    else:
                        m = re.search(r"창천동\s*(\d+)(?:-(\d+))?", addr); jb = (m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")) if m else ""
                    f = g("floor"); f = "B" + f[1:] if f.startswith("-") else f
                    out.append({"asof": asof, "id": g("id"), "name": g("name"), "branch": g("branch"), "jibun": jb, "floor": f,
                                "lcls": g("lcls"), "mcls": g("mcls"), "scls": g("scls"), "lon": g("lon"), "lat": g("lat")})
                res = enc; break
            except UnicodeDecodeError:
                del out[n_before:]; continue                      # 인코딩이 틀렸으면 그때까지 읽은 것을 버리고 다음 인코딩으로
        if res is None: print(f"  열을 읽지 못함: {path.name}:{member}")
    if not out: print(f"  창천동 업소 0건: {path.name}"); return
    dst = OUT / f"changcheon_{asof}.csv"
    with open(dst, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(f"  {path.name} → {dst.name}: 창천동 {len(out)}곳")

if __name__ == "__main__":
    targets = [Path(a) for a in sys.argv[1:]] or [ROOT / "data/raw/semas_history", ROOT / "data/raw"]
    files = []
    for t in targets:
        if t.is_dir():
            files += [p for p in sorted(t.iterdir()) if p.is_file() and re.search(r"상가|상권", unicodedata.normalize("NFC", p.name)) and p.suffix.lower() in (".csv", ".zip")]
        elif t.exists(): files.append(t)
    if not files: sys.exit("처리할 파일이 없습니다. data/raw/semas_history/ 에 스냅샷 파일을 넣어 주세요.")
    for p in files: extract(p)
