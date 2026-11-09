"""만든 뒤 재확인 (필수 1회). raw.json 을 다시 계산해 data.json·브리핑.html 과 대조한다.

사용: python recheck.py --out <작업폴더>      끝에 PASS / FAIL 과 문제 목록을 출력하고 재확인.txt 로 저장.
확인 항목
 1) 표의 모든 종가·전일 대비·1년 최고가 대비를 raw.json 에서 다시 계산해 일치하는지
 2) 요약·해설 문장 속 %가 표에 있는 값인지 (지어낸 숫자 방지)
 3) '확인 필요' 칸 / 금지 표현(전망·지지·저항·매수·매도·폭락·대박·충격 등)
 4) 구조: 필수 섹션 순서, AI 표기, 투자 권유 아님 문구, 해시태그 수, 제목 형식
 5) 브리핑.html 이 data.json 과 같은 내용을 담고 있는지(표·제목·태그)
 6) 요약이미지.png: 있는지, data.json 보다 새것인지, 날짜가 raw.json·본문 기준 시각과 같은지, 순위·%가 재계산과 같은지
"""
import argparse
import json
import re
from pathlib import Path

BAN = ["전망", "예상", "지지", "저항", "돌파", "매수", "매도", "추천", "폭락", "대박", "충격", "급등", "급락", "체크포인트",
       "것으로 보여", "영향으로", "때문에", "분할", "비중", "개인적으로"]
NA = "확인 필요"
ORDER = ["3줄 요약", "상승·하락 TOP5", "지수", "반도체", "미국 지수·기술주·개별주", "코인"]


def pct(a, b):
    return (a - b) / b * 100


def money(it):
    k, v = it["key"], it["close"]
    if k in ("kospi", "kosdaq", "nasdaq", "sp500"):
        return f"{v:,.2f}"
    if k == "usdkrw":
        return f"{v:,.2f}원"
    if it.get("symbol", "").endswith(".KS") or k in ("btc", "eth", "xrp"):
        return f"{v:,.0f}원"
    return f"${v:,.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    raw = json.loads((out / "raw.json").read_text(encoding="utf-8"))
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    page = (out / "브리핑.html").read_text(encoding="utf-8") if (out / "브리핑.html").exists() else ""
    fails, warns = [], []

    items = {}
    for it in list(raw["items"].values()) + list(raw["crypto"].values()):
        items[it["name"]] = it
    ov = out / "override.json"
    if ov.exists():
        for k, v in json.loads(ov.read_text(encoding="utf-8")).items():
            if k in raw["items"]:
                items[raw["items"][k]["name"]].update(v)

    valid_pcts = set()
    checked = 0
    for s in data["sections"]:
        cols, rows = s.get("columns"), s.get("rows")
        if not rows:
            continue
        for r in rows:
            if cols[0] == "구분":  # TOP5
                name, shown = r[1], r[2]
                it = items.get(name)
                if not it:
                    fails.append(f"TOP5: 알 수 없는 종목 {name}")
                    continue
                calc = f"{pct(it['close'], it['prev']):+.2f}%"
                checked += 1
                if shown != calc:
                    fails.append(f"TOP5 {name}: 표 {shown} / 재계산 {calc}")
                valid_pcts.add(shown)
                continue
            name = r[0]
            it = items.get(name)
            if not it:
                fails.append(f"{s['title']}: 알 수 없는 종목 {name}")
                continue
            exp = [money(it), f"{pct(it['close'], it['prev']):+.2f}%", f"{pct(it['close'], it['hi52']):+.2f}%"]
            checked += 1
            for label, shown, calc in zip(cols[1:], r[1:], exp):
                if NA in shown:
                    fails.append(f"{name} {label}: 확인 필요")
                elif shown != calc:
                    fails.append(f"{name} {label}: 표 {shown} / 재계산 {calc}")
                valid_pcts.add(shown)
    # 원화 표기 "(+33,000원)" 같은 건 쓰지 않으므로 % 토큰만 비교
    text_lines = [l for s in data["sections"] for l in s.get("commentary", [])] + data.get("intro", []) + data.get("basis", [])
    text_lines += data.get("title_candidates", []) + [data.get("title", "")]
    for line in text_lines:
        for tok in re.findall(r"[+-]\d+\.\d+%", line):
            if tok not in valid_pcts:
                fails.append(f"문장 속 숫자가 표에 없음: {tok} ← {line[:40]}")
    for line in text_lines:
        for w in BAN:
            if w in line:
                fails.append(f"금지 표현 '{w}': {line[:50]}")

    titles = [re.sub(r"^\d+\.\s*", "", s["title"]) for s in data["sections"]]
    pos = []
    for need in ORDER:
        hit = [i for i, t in enumerate(titles) if need in t]
        if not hit:
            fails.append(f"필수 섹션 없음: {need}")
        else:
            pos.append(hit[0])
    if pos != sorted(pos):
        fails.append("섹션 순서가 규칙과 다름")
    if "금" not in " ".join(titles):
        fails.append("금(환율·금) 섹션 없음")
    if "AI" not in data.get("ai_note", ""):
        fails.append("AI 활용 표기 없음")
    if not any("투자 권유가 아니라" in l for l in data.get("intro", [])):
        fails.append("'투자 권유가 아니라…' 문구 없음")
    n = len(data.get("tags", []))
    if not 10 <= n <= 18:
        warns.append(f"해시태그 {n}개 (15개 안팎 권장)")
    if len(data.get("title_candidates", [])) < 3:
        warns.append("제목 후보가 3개 미만")
    if not re.search(r"\(\d+/\d+ 시황\)", data.get("title", "")):
        warns.append("추천 제목이 '(M/D 시황)' 형식이 아님")

    # HTML 이 data.json 을 그대로 담았는지
    if not page:
        fails.append("브리핑.html 이 없음")
    else:
        import html as H
        flat = H.unescape(re.sub(r"<[^>]+>", "", page))
        for s in data["sections"]:
            for r in s.get("rows", []) or []:
                for c in r:
                    if str(c) not in flat:
                        fails.append(f"HTML에 없는 칸: {c}")
        if H.unescape(data["title"]) not in flat:
            fails.append("HTML에 제목 없음")
        if "<ol" in page or "<li>1." in page:
            fails.append("번호 목록(ol) 사용됨 — 붙여넣기 문제")
    # 요약 이미지 (요약이미지.png + 요약이미지.meta.json)
    png, mp = out / "요약이미지.png", out / "요약이미지.meta.json"
    if not png.exists() or not mp.exists():
        fails.append("요약이미지.png(또는 meta) 없음 — make_image.py 를 실행해야 함")
    else:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if png.stat().st_mtime + 1 < (out / "data.json").stat().st_mtime:
            fails.append("요약이미지.png 가 data.json 보다 오래됨 — 다시 만들어야 함")
        kd, ud = raw["items"]["kospi"]["date"], raw["items"]["nasdaq"]["date"]
        if meta["kr_date"] != kd or meta["us_date"] != ud or meta["today"] != raw["kst_today"]:
            fails.append(f"이미지 날짜 불일치: 이미지 {meta['kr_date']}/{meta['us_date']}/{meta['today']} / raw {kd}/{ud}/{raw['kst_today']}")
        md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"
        basis = " ".join(data.get("basis", []))
        for lab, d in (("한국", kd), ("미국", ud)):
            if md(d) not in basis:
                fails.append(f"본문 기준 시각 줄에 {lab} 기준일 {md(d)} 이 없음(이미지와 본문 날짜 불일치 가능)")
        top = next((x for x in data["sections"] if "TOP5" in x["title"]), None)
        want_up = [[r[1], r[2]] for r in top["rows"] if r[0].startswith("상승")] if top else []
        want_dn = [[r[1], r[2]] for r in top["rows"] if r[0].startswith("하락")] if top else []
        if meta["ups"] != want_up or meta["downs"] != want_dn:
            fails.append("이미지 TOP5 가 data.json TOP5 와 다름")
        for nm, shown in meta["ups"] + meta["downs"]:
            it = items.get(nm)
            if not it or shown != f"{pct(it['close'], it['prev']):+.2f}%":
                fails.append(f"이미지 TOP5 {nm}: 이미지 {shown} / 재계산 다름")
        ps = [float(x[1].rstrip("%")) for x in meta["ups"]]
        ds = [float(x[1].rstrip("%")) for x in meta["downs"]]
        if ps != sorted(ps, reverse=True) or ds != sorted(ds):
            fails.append("이미지 TOP5 정렬이 올바르지 않음")
        if any(not x[1].startswith("+") for x in meta["ups"]) or any(not x[1].startswith("-") for x in meta["downs"]):
            fails.append("이미지 상승/하락 칸에 부호가 반대인 값이 있음")
        for c in meta["cards"]:
            for tok in re.findall(r"[+-]\d+\.\d+%", c["head"] + " " + c["sub"]):
                if tok not in valid_pcts:
                    fails.append(f"이미지 카드 숫자가 표에 없음: {tok}")
    for e in raw.get("errors", []):
        warns.append(f"수집 오류: {e}")

    lines = [f"재확인한 표 행: {checked}개", ""]
    lines += ["[실패]"] + (fails or ["없음"]) + ["", "[주의]"] + (warns or ["없음"]) + ["", "결과: " + ("FAIL" if fails else "PASS")]
    (out / "재확인.txt").write_text("\n".join(lines), encoding="utf-8")
    print("결과:", "FAIL" if fails else "PASS", f"(행 {checked}개, 실패 {len(fails)}, 주의 {len(warns)})")


if __name__ == "__main__":
    main()
