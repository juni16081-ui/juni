"""고정 종목 시세 수집 (야후 파이낸스 일봉 + 업비트) -> raw.json

사용: python fetch.py --out <작업폴더> [--now 2026-11-04T08:00]   (--now는 한국 시간, 시험용)

규칙
- 아침 발행 기준: 장이 아직 안 끝난 오늘 봉은 버리고 마지막 '완성된' 봉을 종가로 쓴다.
- 한국: 15:45 이전이면 오늘 봉 제외 / 미국: 현지 16:10 이전이면 오늘 봉 제외 / 환율·금: 한국 오늘 날짜 봉 제외.
- 1년 최고가 = 최근 1년 일봉 고가의 최댓값.
- 못 받은 값은 None으로 두고 지어내지 않는다.
"""
import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

H = {"User-Agent": "Mozilla/5.0"}

# (키, 표시 이름, 야후 심볼, 종류)  종류: KR / US / FX / GOLD
ITEMS = [
    ("kospi", "코스피", "^KS11", "KR"),
    ("kosdaq", "코스닥", "^KQ11", "KR"),
    ("nasdaq", "나스닥", "^IXIC", "US"),
    ("sp500", "S&P500", "^GSPC", "US"),
    ("samsung", "삼성전자", "005930.KS", "KR"),
    ("hynix", "SK하이닉스", "000660.KS", "KR"),
    ("nvda", "엔비디아 NVDA", "NVDA", "US"),
    ("soxx", "SOXX", "SOXX", "US"),
    ("soxl", "SOXL (3배)", "SOXL", "US"),
    ("spy", "SPY", "SPY", "US"),
    ("qqq", "QQQ", "QQQ", "US"),
    ("qld", "QLD (2배)", "QLD", "US"),
    ("tqqq", "TQQQ (3배)", "TQQQ", "US"),
    ("tsla", "테슬라 TSLA", "TSLA", "US"),
    ("aapl", "애플 AAPL", "AAPL", "US"),
    ("mstr", "스트래티지 MSTR", "MSTR", "US"),
    ("usdkrw", "원/달러 환율", "KRW=X", "FX"),
    ("gold", "금 선물 1온스", "GC=F", "GOLD"),
    # 금요일 배당 섹션
    ("schd", "SCHD", "SCHD", "US"),
    ("jepq", "JEPQ", "JEPQ", "US"),
    ("qqqi", "QQQI", "QQQI", "US"),
    ("ko", "코카콜라 KO", "KO", "US"),
    ("o", "리얼티인컴 O", "O", "US"),
    ("kodex", "KODEX 200타겟위클리커버드콜", "498400.KS", "KR"),
]

UPBIT = [("btc", "비트코인 BTC", "KRW-BTC"), ("eth", "이더리움 ETH", "KRW-ETH"), ("xrp", "리플 XRP", "KRW-XRP")]


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20))


def fetch_yahoo(key, name, sym, kind, now_utc, kst_today):
    r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d")["chart"]["result"][0]
    m, q = r["meta"], r["indicators"]["quote"][0]
    off = m.get("gmtoffset", 0)
    bars = []
    for t, c, h, lo in zip(r["timestamp"], q["close"], q["high"], q["low"]):
        if c is None:
            continue
        d = (dt.datetime.fromtimestamp(t, dt.timezone.utc) + dt.timedelta(seconds=off)).date().isoformat()
        bars.append((d, c, h, lo))
    dropped = False
    local = now_utc + dt.timedelta(seconds=off)
    ld, lt = local.date().isoformat(), local.time()
    last = bars[-1][0]
    if kind == "KR":
        dropped = last == ld and lt < dt.time(15, 45)
    elif kind == "US":
        dropped = last == ld and lt < dt.time(16, 10)
    else:
        dropped = last >= kst_today
    if dropped:
        bars = bars[:-1]
    d, close, hi, lo = bars[-1]
    return dict(
        key=key, name=name, symbol=sym, kind=kind, date=d, close=close,
        prev=bars[-2][1], prev_date=bars[-2][0],
        hi52=max(b[2] for b in bars if b[2] is not None),
        dayhigh=hi, daylow=lo, dropped_partial=dropped,
        meta_price=m.get("regularMarketPrice"), short_name=m.get("shortName"),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--now", help="한국 시간 시험용: 2026-11-04T08:00")
    a = ap.parse_args()

    if a.now:
        kst = dt.datetime.fromisoformat(a.now)
        now_utc = (kst - dt.timedelta(hours=9)).replace(tzinfo=dt.timezone.utc)
    else:
        now_utc = dt.datetime.now(dt.timezone.utc)
    kst_now = now_utc + dt.timedelta(hours=9)
    kst_today = kst_now.date().isoformat()

    out = {"kst_now": kst_now.strftime("%Y-%m-%d %H:%M"), "kst_today": kst_today, "items": {}, "crypto": {}, "errors": []}
    for key, name, sym, kind in ITEMS:
        try:
            out["items"][key] = fetch_yahoo(key, name, sym, kind, now_utc, kst_today)
        except Exception as e:  # 못 받은 종목은 비워 두고 알린다
            out["errors"].append(f"{name}({sym}): {e}")
    try:
        mk = ",".join(m for _, _, m in UPBIT)
        rows = {x["market"]: x for x in get(f"https://api.upbit.com/v1/ticker?markets={mk}")}
        for key, name, m in UPBIT:
            x = rows[m]
            out["crypto"][key] = dict(
                key=key, name=name, close=x["trade_price"], prev=x["prev_closing_price"],
                hi52=x["highest_52_week_price"], upbit_rate=x["signed_change_rate"] * 100,
            )
    except Exception as e:
        out["errors"].append(f"업비트: {e}")

    p = Path(a.out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {p / 'raw.json'}  (종목 {len(out['items'])}개, 코인 {len(out['crypto'])}개)")
    for e in out["errors"]:
        print("오류:", e)


if __name__ == "__main__":
    main()
