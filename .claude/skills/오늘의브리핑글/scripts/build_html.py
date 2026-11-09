"""data.json -> 브리핑.html (네이버 에디터 붙여넣기용 인라인 스타일).

사용: python build_html.py <data.json> [출력.html]

번호 제목("1. 3줄 요약")은 번호 목록(<ol>)이 아니라 굵은 일반 문단으로 만든다.
'확인 필요' 칸이 있으면 맨 위 상자에 빨간 글씨로 알린다.
"""
import html
import json
import re
import sys
from pathlib import Path

TH = "background:#f2f4f6;border-bottom:1px solid #e5e7eb;padding:12px 10px;text-align:center;font-weight:bold"
TD = "border-bottom:1px solid #e5e7eb;padding:12px 10px;text-align:center"
NA = "확인 필요"

SCRIPT = """<script>
function cp(id){var e=document.getElementById(id),r=document.createRange();r.selectNodeContents(e);
var s=getSelection();s.removeAllRanges();s.addRange(r);
var ok=false;try{ok=document.execCommand('copy')}catch(x){}
alert(ok?'복사됐어요. 네이버 에디터에서 Ctrl+V 하세요.':'복사가 막혔어요. 선택된 부분을 Ctrl+C 로 복사하세요.');}
</script>"""


def esc(s):
    return html.escape(str(s))


def wrap(line, width=24):
    """긴 문장에 부드러운 줄바꿈(<br>)을 넣는다. 쉼표 뒤를 먼저, 없으면 띄어쓰기 기준 약 24자."""
    line = str(line)
    if ", " in line and len(line) <= 34:  # 쉼표로 이어진 두 덩어리가 한 줄에 들어가면 그대로 둔다
        return esc(line)
    out = []
    while len(line) > 26:
        cut = None
        for m in re.finditer(r", ", line):
            if 12 <= m.end() <= 34:
                cut = m.end()
                break
        if cut is None:
            sp = [m.start() for m in re.finditer(" ", line) if m.start() <= width]
            cut = sp[-1] + 1 if sp else None
        if not cut or cut >= len(line):
            break
        out.append(line[:cut].rstrip())
        line = line[cut:].lstrip()
    out.append(line)
    return "<br>".join(esc(x) for x in out)


def table(columns, rows):
    out = ['<table style="border-collapse:collapse;width:100%;margin:10px 0 16px;border:1px solid #e5e7eb">']
    out.append("<tr>" + "".join(f'<th style="{TH}">{esc(c)}</th>' for c in columns) + "</tr>")
    for r in rows:
        out.append("<tr>" + "".join(f'<td style="{TD}">{esc(c)}</td>' for c in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name("브리핑.html")
    d = json.loads(src.read_text(encoding="utf-8"))

    blanks = []
    body = []
    def block(lines):
        """한 묶음의 줄들은 한 문단 안에서 <br>로 붙여 간격 없이 보이게 한다."""
        return "<p>" + "<br>".join(wrap(x) for x in lines) + "</p>"

    head_lines = ([d["heading"]] if d.get("heading") else []) + d.get("intro", [])
    if head_lines:
        body.append(block(head_lines))
    if d.get("basis"):
        body.append('<p style="margin-top:22px"><b>기준 시각</b></p>')
        body.append(block(d["basis"]))

    for i, s in enumerate(d.get("sections", []), 1):
        body.append(f'<p style="margin:26px 0 8px"><b>{i}. {esc(s["title"])}</b></p>')
        if s.get("columns") and s.get("rows"):
            for r in s["rows"]:
                if any(str(c).strip() in ("-", "", NA) for c in r):
                    blanks.append(f'{s["title"]} / {r[1] if s["columns"][0] == "구분" else r[0]}')
            body.append(table(s["columns"], s["rows"]))
        if s.get("commentary"):
            body.append(block(s["commentary"]))

    if d.get("ai_note"):
        body.append(f'<p style="margin-top:26px;color:#666">{esc(d["ai_note"])}</p>')
    tags = " ".join("#" + t.lstrip("#") for t in d.get("tags", []))
    if tags:
        body.append(f"<p>{esc(tags)}</p>")

    cands = "".join(f"<li>{esc(t)}</li>" for t in d.get("title_candidates", []))
    head = (
        '<div style="border:2px dashed #999;padding:12px;margin-bottom:24px">'
        "<b>제목</b> <button onclick=\"cp('t')\">제목 복사</button><p id=\"t\">" + esc(d.get("title", "")) + "</p>"
        + (f"<b>제목 후보</b><ul>{cands}</ul>" if len(d.get("title_candidates", [])) > 1 else "")
        + (f'<p style="color:#c00">확인 필요: {esc(", ".join(blanks))}</p>' if blanks else "")
        + "</div>"
    )
    page = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        "<title>오늘의 브리핑</title></head>"
        '<body style="max-width:760px;margin:24px auto;padding:0 16px;line-height:1.8;font-family:sans-serif">'
        + head
        + '<p><button onclick="cp(\'b\')" style="font-size:16px;padding:8px 14px">본문 전체 복사</button></p>'
        + '<div id="b" style="text-align:center">' + "\n".join(body) + "</div>" + SCRIPT + "</body></html>"
    )
    dst.write_text(page, encoding="utf-8")
    print(dst)
    if blanks:
        print("확인 필요:", ", ".join(blanks))


if __name__ == "__main__":
    main()
