"""등락률·고점 대비·원화 환산 계산기.

예) python calc.py --price 246500 --prev 242000 --high 380000
    python calc.py --price 4059.96 --fx 1342.23   (달러 -> 원화)
"""
import argparse


def pct(a, b):
    return (a - b) / b * 100


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--prev", type=float, help="전일 종가")
    p.add_argument("--high", type=float, help="52주 고점")
    p.add_argument("--fx", type=float, help="원/달러 환율 (달러 가격 -> 원화 환산)")
    a = p.parse_args()

    if a.prev:
        print(f"전일 대비: {a.price - a.prev:+,.2f} ({pct(a.price, a.prev):+.2f}%)")
    if a.high:
        print(f"고점 대비: {pct(a.price, a.high):+.2f}%")
    if a.fx:
        print(f"원화 환산: {a.price * a.fx:,.0f}원")


if __name__ == "__main__":
    main()
