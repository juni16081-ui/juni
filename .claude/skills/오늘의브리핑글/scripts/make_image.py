"""요약 이미지(요약이미지.png): 3줄 요약 카드 3장 + 상승·하락 TOP5 표. 숫자는 data.json 문자열 그대로.

사용: python make_image.py --out <작업폴더>   (data.json·raw.json 필요, build_html 뒤에 실행)
함께 요약이미지.meta.json 을 저장한다(recheck.py 가 날짜·순위를 대조하는 용도).
색: 상승 빨강 / 하락 파랑(블로그 본문과 같음). 로고 없이 단순 아이콘.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = 1408
UP, DN = "#d62f2f", "#2f5fd6"
UPBG, DNBG = "#fdecec", "#eaf0fd"
NAVY, INK, GRAY, LINE, BG = "#1d3a8a", "#1f2937", "#6b7280", "#d5dbe3", "#f1f5fb"
import os


def _pick(paths):
    return next((p for p in paths if os.path.exists(p)), paths[0])


# 윈도우(맑은 고딕) 우선, 없으면 리눅스 한글 글꼴로 대체(굵은 글꼴이 없으면 같은 글꼴 사용)
F = _pick(["C:/Windows/Fonts/malgun.ttf",
           "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
           "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"])
FB = _pick(["C:/Windows/Fonts/malgunbd.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", F])
WD = "월화수목금토일"


def font(s, b=False):
    return ImageFont.truetype(FB if b else F, s)


def col(p):
    return UP if p.startswith("+") else DN


def arrow(d, cx, cy, size, up, color):
    h = size
    if up:
        d.polygon([(cx, cy - h), (cx - h, cy + h * 0.7), (cx + h, cy + h * 0.7)], fill=color)
    else:
        d.polygon([(cx, cy + h), (cx - h, cy - h * 0.7), (cx + h, cy - h * 0.7)], fill=color)


def ctext(d, xy, s, f, fill):
    d.text(xy, s, font=f, fill=fill, anchor="mm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", default="요약이미지.png")
    a = ap.parse_args()
    out = Path(a.out)
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    raw = json.loads((out / "raw.json").read_text(encoding="utf-8"))
    sec = {s["title"]: s for s in data["sections"]}
    rows = {}
    for s in data["sections"]:
        if s.get("columns") and s["columns"][0] == "종목":
            for r in s["rows"]:
                rows[r[0]] = r  # 이름 -> [이름, 종가, 전일대비, 최고가대비]
    pct = lambda name: rows[name][2]

    kinds = {it["name"]: {"KR": "한국", "US": "미국"}.get(it["kind"], "") for it in raw["items"].values()}
    for it in raw["crypto"].values():
        kinds[it["name"]] = "업비트"

    kr = raw["items"]["kospi"]["date"]
    us = raw["items"]["nasdaq"]["date"]
    md = lambda s: f"{int(s[5:7])}/{int(s[8:10])}"
    today = dt.date.fromisoformat(raw["kst_today"])

    top = sec["오늘 담은 종목 중 상승·하락 TOP5"]["rows"]
    ups = [(r[1], r[2]) for r in top if r[0].startswith("상승")]
    downs = [(r[1], r[2]) for r in top if r[0].startswith("하락")]

    H = 1010
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # ---- 제목 ----
    t1, t2 = "오늘의 증시 요약 & ", "TOP 5 종목"
    f = font(54, True)
    w1, w2 = d.textlength(t1, font=f), d.textlength(t2, font=f)
    x = (W - (w1 + w2)) / 2
    d.text((x, 52), t1, font=f, fill=NAVY, anchor="lm")
    d.text((x + w1, 52), t2, font=f, fill="#0f7a4a", anchor="lm")
    d.text((W - 36, 40), today.strftime("%Y.%m.%d ") + WD[today.weekday()] + "요일", font=font(26, True), fill=INK, anchor="rm")
    ctext(d, (W / 2, 100), f"한국 {md(kr)} 종가 · 미국 현지 {md(us)} 종가 기준", font(26), GRAY)

    # ---- 1. 3줄 요약 ----
    d.text((36, 150), "1. 오늘 3줄 요약", font=font(34, True), fill=INK, anchor="lm")
    sam, hyn = pct("삼성전자"), pct("SK하이닉스")
    soxl, soxx = pct("SOXL (3배)"), pct("SOXX")
    coins = [("비트코인 BTC", "BTC"), ("이더리움 ETH", "ETH"), ("리플 XRP", "XRP")]
    cp = [pct(n) for n, _ in coins]

    def word(p, up="올랐어요", dn="내렸어요"):
        return up if p.startswith("+") else dn

    # 카드 1
    if sam[0] == hyn[0]:
        b1 = f"삼성전자·SK하이닉스\n모두 {word(sam)}."
    else:
        b1 = "같은 반도체 종목인데\n방향이 달랐어요."
    c1 = dict(icon="KR", ic="#1d3a8a", head=f"삼성전자 {sam}", sub=f"SK하이닉스 {hyn}", up=sam.startswith("+"), body=b1, mixed=False)
    # 카드 2
    if soxl[0] == soxx[0]:
        b2 = f"SOXL {soxl}, SOXX {soxx}\n{word(soxx)}."
    else:
        b2 = "SOXL과 SOXX의\n방향이 달랐어요."
    c2 = dict(icon="US", ic="#0f7a4a", head="美 반도체 ETF " + ("상승" if soxx.startswith("+") else "하락"),
              sub=f"SOXL {soxl} / SOXX {soxx}", up=soxx.startswith("+"), body=b2, mixed=soxl[0] != soxx[0])
    # 카드 3
    same = len({p[0] for p in cp}) == 1
    if same:
        c3 = dict(icon="코인", ic="#f59e0b", head="가상화폐 " + ("상승" if cp[0].startswith("+") else "하락"),
                  sub="BTC · ETH · XRP", up=cp[0].startswith("+"), body=f"비트코인·이더리움·리플\n모두 {word(cp[0])}.", mixed=False)
    else:
        c3 = dict(icon="코인", ic="#f59e0b", head="가상화폐 엇갈림", sub="BTC · ETH · XRP", up=True, body="코인마다 방향이 달랐어요.", mixed=True)
    c3["note"] = "(업비트 현재가, 어제 오전 9시 대비)"

    cw, gap, cx0, cy0, ch = 432, 24, 32, 185, 215
    for i, c in enumerate([c1, c2, c3]):
        x0 = cx0 + i * (cw + gap)
        color = "#6b7280" if c["mixed"] else (UP if c["up"] else DN)
        bg = "#f3f4f6" if c["mixed"] else (UPBG if c["up"] else DNBG)
        d.rounded_rectangle((x0, cy0, x0 + cw, cy0 + ch), 22, fill="white", outline=color, width=3)
        d.rounded_rectangle((x0 + 3, cy0 + 3, x0 + cw - 3, cy0 + 100), 20, fill=bg)
        d.rectangle((x0 + 3, cy0 + 60, x0 + cw - 3, cy0 + 100), fill=bg)
        d.ellipse((x0 + 22, cy0 + 22, x0 + 82, cy0 + 82), fill=c["ic"])
        ctext(d, (x0 + 52, cy0 + 52), c["icon"], font(24 if len(c["icon"]) < 3 else 21, True), "white")
        hf = font(36, True)
        while d.textlength(c["head"], font=hf) > cw - 190:
            hf = font(hf.size - 2, True)
        d.text((x0 + 100, cy0 + 40), c["head"], font=hf, fill=color, anchor="lm")
        sf = font(24)
        while d.textlength(c["sub"], font=sf) > cw - 190:
            sf = font(sf.size - 2)
        d.text((x0 + 100, cy0 + 78), c["sub"], font=sf, fill=INK, anchor="lm")
        if not c["mixed"]:
            arrow(d, x0 + cw - 50, cy0 + 56, 20, c["up"], color)
        lines = c["body"].split("\n")
        by = cy0 + 130 if len(lines) > 1 else cy0 + 145
        for j, ln in enumerate(lines):
            ctext(d, (x0 + cw / 2, by + j * 36), ln, font(28), INK)
        if c.get("note"):
            ctext(d, (x0 + cw / 2, cy0 + ch - 22), c["note"], font(21), GRAY)

    # ---- 2. 표 ----
    ty = cy0 + ch + 40
    d.text((36, ty), "2. 오늘 담은 종목 중 가장 많이 오른 종목·내린 종목 5개씩", font=font(34, True), fill=INK, anchor="lm")
    y0, hh, rh = ty + 40, 56, 62
    Lx = 32
    Lc = [140, 90, 310, 160]
    Rx = Lx + sum(Lc)
    Rc = [140, 340, 164]

    def hdr(x, w, label, color):
        d.rectangle((x, y0, x + w, y0 + hh), fill=color, outline="white")
        ctext(d, (x + w / 2, y0 + hh / 2), label, font(28, True), "white")

    xs = Lx
    for w, lb in zip(Lc, ["구분", "순위", "종목", "등락률"]):
        hdr(xs, w, lb, UP)
        xs += w
    xs = Rx
    for w, lb in zip(Rc, ["구분", "종목", "등락률"]):
        hdr(xs, w, lb, DN)
        xs += w

    def namecell(x, w, y, nm):
        mk = kinds.get(nm, "")
        nf = font(29, True)
        while d.textlength(nm, font=nf) > w - 110:
            nf = font(nf.size - 2, True)
        d.text((x + 20, y), nm, font=nf, fill=INK, anchor="lm")
        if mk:
            d.text((x + 20 + d.textlength(nm, font=nf) + 8, y + 2), f"({mk})", font=font(22), fill=GRAY, anchor="lm")

    def pctcell(x, w, y, p):
        ctext(d, (x + w / 2 - 22, y), p, font(30, True), col(p))
        arrow(d, x + w - 24, y, 11, p.startswith("+"), col(p))

    for i in range(5):
        ry = y0 + hh + i * rh
        cy = ry + rh / 2
        # 왼쪽(상승)
        xs = Lx
        for j, w in enumerate(Lc):
            d.rectangle((xs, ry, xs + w, ry + rh), fill=UPBG if i % 2 == 0 else "white", outline=LINE)
            xs += w
        # 오른쪽(하락)
        xs = Rx
        for j, w in enumerate(Rc):
            d.rectangle((xs, ry, xs + w, ry + rh), fill=DNBG if i % 2 == 0 else "white", outline=LINE)
            xs += w
        if i < len(ups):
            ctext(d, (Lx + Lc[0] + Lc[1] / 2, cy), str(i + 1), font(30, True), INK)
            namecell(Lx + Lc[0] + Lc[1], Lc[2], cy, ups[i][0])
            pctcell(Lx + Lc[0] + Lc[1] + Lc[2], Lc[3], cy, ups[i][1])
        if i < len(downs):
            namecell(Rx + Rc[0], Rc[1], cy, downs[i][0])
            pctcell(Rx + Rc[0] + Rc[1], Rc[2], cy, downs[i][1])
    # 합친 구분 칸
    gh = rh * 5
    d.rectangle((Lx, y0 + hh, Lx + Lc[0], y0 + hh + gh), fill=UPBG, outline=LINE)
    ctext(d, (Lx + Lc[0] / 2, y0 + hh + gh / 2 - 22), "상승", font(34, True), UP)
    ctext(d, (Lx + Lc[0] / 2, y0 + hh + gh / 2 + 22), "TOP 5", font(34, True), UP)
    d.rectangle((Rx, y0 + hh, Rx + Rc[0], y0 + hh + gh), fill=DNBG, outline=LINE)
    ctext(d, (Rx + Rc[0] / 2, y0 + hh + gh / 2 - 22), "하락", font(34, True), DN)
    ctext(d, (Rx + Rc[0] / 2, y0 + hh + gh / 2 + 22), "TOP 5", font(34, True), DN)
    if len(ups) < 5:
        ctext(d, (Lx + Lc[0] + (sum(Lc) - Lc[0]) / 2, y0 + hh + len(ups) * rh + (5 - len(ups)) * rh / 2),
              f"상승 종목은 {len(ups)}개였어요", font(24), GRAY)

    fy = y0 + hh + gh + 36
    d.text((36, fy), "* 이 글에 담은 종목 중에서 뽑은 순위예요. 지수·금·레버리지 ETF는 뺐고, 기준 시각이 달라 참고용으로 봐 주세요.", font=font(24), fill=INK, anchor="lm")
    d.text((36, fy + 36), "출처: Yahoo Finance, 업비트", font=font(22), fill=GRAY, anchor="lm")
    img = img.crop((0, 0, W, int(fy + 70)))
    img.save(out / a.png)
    meta = {"kr_date": kr, "us_date": us, "today": raw["kst_today"], "size": list(img.size),
            "ups": [list(x) for x in ups], "downs": [list(x) for x in downs],
            "cards": [{"head": c["head"], "sub": c["sub"], "body": c["body"]} for c in (c1, c2, c3)]}
    (out / "요약이미지.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out / a.png, img.size)


if __name__ == "__main__":
    main()
