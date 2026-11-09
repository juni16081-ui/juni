"""raw.json -> data.json(+검증.txt). 표·순위·요약·태그를 숫자에서 바로 만든다.

사용: python make_data.py --out <작업폴더> [--dividend auto|on|off]
  배당 섹션: auto = 발행일(한국)이 금요일이면 넣음.
제목·도입 문구는 필요하면 클로드가 data.json에서 다듬는다(숫자는 건드리지 않는다).
"""
import argparse
import datetime as dt
import json
from pathlib import Path

NA = "확인 필요"
LEVER = {"soxl", "qld", "tqqq"}
NOT_RANKED = {"kospi", "kosdaq", "nasdaq", "sp500", "usdkrw", "gold"} | LEVER
GROUPS = {
    "idx_kr": ["kospi", "kosdaq"], "idx_us": ["nasdaq", "sp500"],
    "semi_kr": ["samsung", "hynix"], "semi_us": ["nvda", "soxx", "soxl"],
    "us": ["spy", "qqq", "qld", "tqqq", "tsla", "aapl", "mstr"],
    "div": ["schd", "jepq", "qqqi", "ko", "o", "kodex"],
}
COLS = ["종목", "종가", "전일 대비", "1년 최고가 대비"]
MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def pct(a, b):
    return (a - b) / b * 100


def sp(x):
    return f"{x:+.2f}%"


def md(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def prev_weekday(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def money(it):
    k, v = it["key"], it["close"]
    if k in ("kospi", "kosdaq", "nasdaq", "sp500"):
        return f"{v:,.2f}"
    if k == "usdkrw":
        return f"{v:,.2f}원"
    if it.get("symbol", "").endswith(".KS"):
        return f"{v:,.0f}원"
    if k in ("btc", "eth", "xrp"):
        return f"{v:,.0f}원"
    return f"${v:,.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dividend", default="auto", choices=["auto", "on", "off"])
    a = ap.parse_args()
    out = Path(a.out)
    raw = json.loads((out / "raw.json").read_text(encoding="utf-8"))
    today = dt.date.fromisoformat(raw["kst_today"])
    show_div = a.dividend == "on" or (a.dividend == "auto" and today.weekday() == 4)

    missing, notes = [], []
    rows = {}  # key -> dict(name, close_s, chg, hi, row, rank_ok)

    # 원/달러 환율: 야후 일봉은 서울 마감 기준이 아니라 전일 대비가 틀릴 수 있다.
    # 확인된 값을 <작업폴더>/override.json 에 {"usdkrw": {"close": 1341.0, "prev": 1346.0}} 로 주면 그 값을 쓴다.
    ov_path = out / "override.json"
    ov = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    if "usdkrw" in raw["items"]:
        fxi = raw["items"]["usdkrw"]
        if "usdkrw" in ov:
            fxi.update(ov["usdkrw"])
            notes.append("원/달러 환율: override.json 수동 입력값 사용")
        else:
            del raw["items"]["usdkrw"]  # 확인된 값이 없으면 이번 글에서 뺀다
            notes.append("원/달러 환율: 야후 일봉이 서울 마감 기준과 달라 이번 글에서 뺐어요(override.json으로 값을 주면 포함)")

    def add(it, label=None):
        k, name = it["key"], it["name"]
        try:
            chg = pct(it["close"], it["prev"])
            hi = pct(it["close"], it["hi52"])
            r = [name, money(it), sp(chg), sp(hi)]
        except Exception:
            chg = hi = None
            r = [name, NA, NA, NA]
            missing.append(name)
        rows[k] = dict(name=name, chg=chg, hi=hi, row=r, it=it)

    for it in raw["items"].values():
        add(it)
    for it in raw["crypto"].values():
        add(it)
        # 업비트가 알려 주는 등락률과 직접 계산한 값을 맞춰 본다
        if rows[it["key"]]["chg"] is not None and abs(rows[it["key"]]["chg"] - it["upbit_rate"]) > 0.02:
            notes.append(f'{it["name"]}: 계산 {rows[it["key"]]["chg"]:+.2f}% vs 업비트 {it["upbit_rate"]:+.2f}% 불일치')
    for e in raw.get("errors", []):
        missing.append(e)
    # 종가가 메타 가격과 5% 넘게 다르면 확인 표시 (봉을 버리지 않은 경우만)
    for it in raw["items"].values():
        mp = it.get("meta_price")
        if mp and not it["dropped_partial"] and it["kind"] in ("KR", "US") and abs(pct(it["close"], mp)) > 0.5:
            notes.append(f'{it["name"]}: 일봉 종가 {it["close"]} vs 출처 현재가 {mp} 차이 큼 (장중일 수 있음)')

    def table(keys, label):
        rs = []
        for k in keys:
            if k in rows:
                rs.append(rows[k]["row"])
        return dict(title=label, columns=COLS, rows=rs)

    def has(keys):
        return [k for k in keys if k in rows and rows[k]["chg"] is not None]

    # ---- 기준 시각 / 휴장 ----
    kr_dates = {raw["items"][k]["date"] for k in ("kospi", "kosdaq", "samsung", "hynix") if k in raw["items"]}
    us_dates = {raw["items"][k]["date"] for k in ("nasdaq", "sp500", "nvda") if k in raw["items"]}
    exp = prev_weekday(today).isoformat()
    kr_d = max(kr_dates) if kr_dates else None
    us_d = max(us_dates) if us_dates else None
    basis = []
    if kr_d:
        basis.append(f"한국 주식·지수: {md(kr_d)} 장 마감 종가")
        if kr_d < exp:
            basis.append(f"한국은 {md(exp)} 휴장이라 직전 거래일({md(kr_d)}) 종가를 썼어요.")
    if us_d:
        basis.append(f"미국 주식·지수: 미국 현지 {md(us_d)} 종가")
        if us_d < exp:
            basis.append(f"미국은 {md(exp)} 휴장이라 직전 거래일({md(us_d)}) 종가를 썼어요.")
    if raw["crypto"]:
        basis.append(f"코인: 업비트 {raw['kst_now'][5:16].replace('-', '/')} 현재가 (전일 종가는 어제 오전 9시 가격)")
    fx = raw["items"].get("usdkrw")
    gd = raw["items"].get("gold")
    if fx or gd:
        dd = (fx or gd)["date"]
        gm = ""
        if gd and gd.get("short_name"):
            for en, n in MONTHS.items():
                if en in gd["short_name"].split():
                    gm = f"{n}월물, "
        basis.append(f"{'환율·금' if fx else '금'}: {md(dd)} 종가 (금은 {gm}선물 가격이에요)" if fx else f"금: {md(dd)} 종가 ({gm}선물 가격이에요)")
    basis.append("'1년 최고가 대비'는 지난 1년 중 가장 높았던 가격보다 지금 가격이 몇 % 낮은지(높은지)를 뜻해요.")

    # ---- TOP5 ----
    show_keys = [k for g, ks in GROUPS.items() if g != "div" or show_div for k in ks] + ["btc", "eth", "xrp"]
    pool = [k for k in show_keys if k in rows and k not in NOT_RANKED and rows[k]["chg"] is not None]
    ups = sorted([k for k in pool if rows[k]["chg"] > 0], key=lambda k: -rows[k]["chg"])[:5]
    downs = sorted([k for k in pool if rows[k]["chg"] < 0], key=lambda k: rows[k]["chg"])[:5]
    top_rows = [[f"상승 {i}위", rows[k]["name"], sp(rows[k]["chg"])] for i, k in enumerate(ups, 1)]
    top_rows += [[f"하락 {i}위", rows[k]["name"], sp(rows[k]["chg"])] for i, k in enumerate(downs, 1)]

    def short(k):
        n = rows[k]["name"]
        return n if n.startswith("KODEX") else n.split(" ")[0]

    # ---- 3줄 요약 ----
    summary = []
    if has(["kospi", "kosdaq"]) == ["kospi", "kosdaq"]:
        summary.append(f'한국 증시는 코스피 {sp(rows["kospi"]["chg"])}, 코스닥 {sp(rows["kosdaq"]["chg"])}였어요.')
    if has(["nasdaq", "sp500"]) == ["nasdaq", "sp500"]:
        summary.append(f'미국 증시는 나스닥 {sp(rows["nasdaq"]["chg"])}, S&P500 {sp(rows["sp500"]["chg"])}였어요.')
    bits = []
    if ups:
        bits.append(f'가장 많이 오른 종목은 {rows[ups[0]]["name"]}({sp(rows[ups[0]]["chg"])})')
    if downs:
        bits.append(f'가장 많이 내린 종목은 {rows[downs[0]]["name"]}({sp(rows[downs[0]]["chg"])})')
    if bits:
        summary.append(", ".join(bits) + "예요.")

    # ---- 해설(숫자 반복 없이 비교만) ----
    def bigger(a, b, unit):
        if a not in rows or b not in rows or rows[a]["chg"] is None or rows[b]["chg"] is None:
            return None
        big, small = (a, b) if abs(rows[a]["chg"]) >= abs(rows[b]["chg"]) else (b, a)
        return f'{rows[big]["name"].split(" ")[0]}의 변동이 {rows[small]["name"].split(" ")[0]}보다 컸어요.'

    def lowhigh(k):
        it = raw["items"].get(k)
        if not it or it.get("dayhigh") is None or it.get("daylow") is None:
            return None
        return f'{rows[k]["name"]}는 하루 동안 {it["daylow"]:,.0f}원~{it["dayhigh"]:,.0f}원 사이에서 움직였어요.'

    def best_worst(keys):
        ks = has(keys)
        if not ks:
            return []
        ks = sorted(ks, key=lambda k: rows[k]["chg"])
        res = []
        if rows[ks[-1]]["chg"] > 0:
            res.append(f'가장 많이 오른 건 {short(ks[-1])}예요.')
        if rows[ks[0]]["chg"] < 0:
            res.append(f'가장 많이 내린 건 {short(ks[0])}예요.')
        return res

    sections = [
        dict(title="3줄 요약", commentary=summary),
        dict(title="오늘 담은 종목 중 상승·하락 TOP5", columns=["구분", "종목", "전일 대비"], rows=top_rows,
             commentary=["이 글에 담은 종목 중에서 뽑은 순위예요.",
                         ("지수, 환율, 금" if "usdkrw" in rows else "지수, 금") + ", 레버리지 ETF(SOXL·QLD·TQQQ)는 순위에서 뺐어요.",
                         "시장마다 기준 시각이 달라서 참고용으로만 봐 주세요."]),
    ]
    s = table(GROUPS["idx_kr"] + GROUPS["idx_us"], "지수")
    s["commentary"] = [x for x in (bigger("kospi", "kosdaq", ""), bigger("nasdaq", "sp500", "")) if x]
    sections.append(s)

    s = table(GROUPS["semi_kr"] + GROUPS["semi_us"], "반도체")
    s["commentary"] = [x for x in (lowhigh("samsung"), lowhigh("hynix")) if x]
    s["commentary"].append("SOXL은 반도체 지수 하루 움직임의 3배를 목표로 하는 레버리지 ETF예요.")
    sections.append(s)

    s = table(GROUPS["us"], "미국 지수·기술주·개별주")
    s["commentary"] = best_worst([k for k in GROUPS["us"] if k not in LEVER]) + [
        "QLD(2배)와 TQQQ(3배)는 나스닥100 지수 하루 움직임의 2배·3배를 목표로 하는 레버리지 ETF예요."]
    sections.append(s)

    s = table(["btc", "eth", "xrp"], "코인 (업비트, 원화)")
    s["commentary"] = best_worst(["btc", "eth", "xrp"])
    sections.append(s)

    s = table(["usdkrw", "gold"], "환율·금" if "usdkrw" in rows else "금")
    fx_c = rows.get("usdkrw", {}).get("chg")
    cm = []
    if fx_c is None:
        pass
    elif fx_c > 0:
        cm.append("환율이 올랐다는 건 달러 1개를 사는 데 원화가 더 필요해졌다는 뜻이에요.")
    elif fx_c is not None and fx_c < 0:
        cm.append("환율이 내렸다는 건 달러 1개를 사는 데 필요한 원화가 줄었다는 뜻이에요.")
    cm.append("금은 선물 가격(달러)이라 국내 금 시세와는 달라요.")
    s["commentary"] = cm
    sections.append(s)

    if show_div:
        s = table(GROUPS["div"], "배당 ETF·배당주")
        s["commentary"] = best_worst(GROUPS["div"])
        sections.append(s)

    # ---- 제목 ----
    movers = sorted(pool, key=lambda k: -abs(rows[k]["chg"]))[:2]
    title = ""
    if len(movers) == 2:
        a_, b_ = movers
        same = (rows[a_]["chg"] > 0) == (rows[b_]["chg"] > 0)
        word = "동반 상승" if same and rows[a_]["chg"] > 0 else "동반 하락" if same else "방향이 갈렸어요"
        title = f'{short(a_)} {sp(rows[a_]["chg"])}, {short(b_)} {sp(rows[b_]["chg"])} {word} ({today.month}/{today.day} 시황)'

    cands = [title] if title else []
    if has(["kospi", "kosdaq", "nasdaq"]) == ["kospi", "kosdaq", "nasdaq"]:
        cands.append(f'{today.month}/{today.day} 시황 | 코스피 {sp(rows["kospi"]["chg"])}, 코스닥 {sp(rows["kosdaq"]["chg"])}, 나스닥 {sp(rows["nasdaq"]["chg"])}')
    if ups and downs:
        cands.append(f'{short(ups[0])} {sp(rows[ups[0]]["chg"])}, {short(downs[0])} {sp(rows[downs[0]]["chg"])}… {today.month}/{today.day} 시황 한눈에')

    base = ["코스피", "삼성전자주가", "SK하이닉스주가", "엔비디아", "SOXL", "비트코인", "나스닥", "S&P500", "미국주식", "반도체"]
    if "usdkrw" in rows:
        base.insert(6, "원달러환율")
    tags = [f"{today.month}월{today.day}일시황"] + [short(k).replace(" ", "") for k in movers] + base
    seen, uniq = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            uniq.append(t)

    data = dict(
        date=f"{today.month}월 {today.day}일", title=title, title_candidates=cands,
        heading="오늘의 브리핑",
        intro=["지난 거래일 시장에서 어떤 자산이 얼마나 움직였는지 숫자만 모아 정리했어요.",
               "투자 권유가 아니라 공개된 시세를 옮겨 적은 글이에요."],
        basis=basis, sections=sections,
        ai_note="이 글은 AI의 도움을 받아 공개된 시세 자료를 정리해 작성했어요.",
        tags=uniq[:15],
    )
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    rep = ["[확인 필요]"] + (missing or ["없음"]) + ["", "[주의]"] + (notes or ["없음"]) + ["", "[종가·전일 종가 원본]"]
    for k, r in rows.items():
        it = r["it"]
        rep.append(f'{it["name"]}: 종가 {it["close"]} / 전일 {it["prev"]} / 1년 최고 {it["hi52"]} -> {r["chg"] if r["chg"] is None else round(r["chg"], 2)}%')
    (out / "검증.txt").write_text("\n".join(rep), encoding="utf-8")
    print(f"data.json 저장 (배당 섹션: {'있음' if show_div else '없음'})")
    print("확인 필요:", missing or "없음")
    print("주의:", notes or "없음")


if __name__ == "__main__":
    main()
