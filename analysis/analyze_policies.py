"""
seed.sql 에 담긴 복지 정책 데이터(5,011건)의 현황을 집계하고 그래프로 저장합니다.
DB 없이 seed.sql 만으로 실행할 수 있습니다.

    python analysis/analyze_policies.py

결과: docs/analysis/*.png, docs/analysis/summary.md
"""
import os
import re
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED    = os.path.join(ROOT, "seed.sql")
OUT_DIR = os.path.join(ROOT, "docs", "analysis")

# 분석 대상 컬럼 (servlist)
CHECK_COLUMNS = {
    "servDgst":          "서비스 요약",
    "jurMnofNm":         "소관 부처/기관",
    "sprtCycNm":         "지원 주기",
    "srvPvsnNm":         "제공 유형",
    "lifeArray":         "생애주기",
    "intrsThemaArray":   "관심주제",
    "trgterIndvdlArray": "가구 유형",
    "servDtlLink":       "상세 링크",
    "onapPsbltYn":       "온라인 신청 여부",
}


# ---------- seed.sql 파싱 ----------

def parse_values(text, pos):
    """VALUES 뒤의 (...),(...); 튜플 목록을 읽어 (rows, 다음 위치)를 반환"""
    rows, row, n = [], None, len(text)
    while pos < n:
        ch = text[pos]
        if ch == "(":
            row = []
            pos += 1
        elif ch == "'":
            buf, pos = [], pos + 1
            while text[pos] != "'":
                if text[pos] == "\\":
                    nxt = text[pos + 1]
                    buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(nxt, nxt))
                    pos += 2
                else:
                    buf.append(text[pos])
                    pos += 1
            row.append("".join(buf))
            pos += 1
        elif ch == ")":
            rows.append(row)
            pos += 1
        elif ch == ";":
            return rows, pos + 1
        elif ch in ", \r\n\t":
            pos += 1
        else:
            m = re.match(r"[^,)]+", text[pos:pos + 64])
            token = m.group(0).strip()
            row.append(None if token == "NULL" else token)
            pos += m.end()
    return rows, pos


def load_table(text, table):
    pattern = re.compile(r"INSERT INTO `%s` \(([^)]*)\) VALUES" % table)
    records = []
    for m in pattern.finditer(text):
        cols = [c.strip(" `") for c in m.group(1).split(",")]
        rows, _ = parse_values(text, m.end())
        records.extend(dict(zip(cols, r)) for r in rows)
    return records


# ---------- 집계 ----------

def is_empty(v):
    return v is None or str(v).strip() == ""


def split_multi(value):
    """'청년, 중장년' 처럼 쉼표로 묶인 값을 나눔"""
    if is_empty(value):
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def count_multi(records, col):
    c = Counter()
    for r in records:
        c.update(split_multi(r.get(col)))
    return c


def count_single(records, col, empty_label="(값 없음)"):
    return Counter(empty_label if is_empty(r.get(col)) else r[col].strip() for r in records)


# ---------- 그래프 ----------

def setup_font():
    for name in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]:
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def barh(counter, title, filename, top=None, xlabel="정책 수(건)"):
    items = counter.most_common(top)[::-1]
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(8, max(3, 0.38 * len(items) + 1)))
    bars = ax.barh(labels, values, color="#3B6EA8")
    ax.bar_label(bars, labels=[f"{v:,}" for v in values], padding=3, fontsize=9)
    ax.set_title(title, fontsize=13, pad=12)
    ax.set_xlabel(xlabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, filename), dpi=130)
    plt.close(fig)


def md_table(counter, header, total, top=None):
    lines = [f"| {header} | 건수 | 비율 |", "| --- | ---: | ---: |"]
    for k, v in counter.most_common(top):
        lines.append(f"| {k} | {v:,} | {v / total:.1%} |")
    return "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    setup_font()

    with open(SEED, encoding="utf-8") as f:
        text = f.read()

    servs   = load_table(text, "servlist")
    details = load_table(text, "servdetail")
    total   = len(servs)

    # 1. 데이터 품질: 중복 · 결측치 · 상세 정보 연결
    dup_ids = [k for k, v in Counter(r["servId"] for r in servs).items() if v > 1]
    detail_ids = {d["servId"] for d in details}
    no_detail = sum(1 for r in servs if r["servId"] not in detail_ids)
    missing = Counter({label: sum(1 for r in servs if is_empty(r.get(col)))
                       for col, label in CHECK_COLUMNS.items()})

    # 2. 출처 · 지역
    source = Counter({"중앙부처": 0, "지자체": 0})
    for r in servs:
        source["중앙부처" if r.get("source") == "central" else "지자체"] += 1
    local = [r for r in servs if r.get("source") != "central"]
    by_sido = count_single(local, "ctpvNm")

    # 3. 정책 특성
    life    = count_multi(servs, "lifeArray")
    theme   = count_multi(servs, "intrsThemaArray")
    target  = count_multi(servs, "trgterIndvdlArray")
    # 제공 유형은 '현금지급, 기타' / '현금지급,기타' 처럼 여러 값이 섞여 있어 나눠서 집계
    pvsn    = count_multi(servs, "srvPvsnNm")
    multi_pvsn = sum(1 for r in servs if len(split_multi(r.get("srvPvsnNm"))) > 1)
    cycle   = count_single(servs, "sprtCycNm")

    # 4. 조회수 상위 정책
    top_inq = sorted(servs, key=lambda r: int(r.get("inqNum") or 0), reverse=True)[:10]
    top_central = sum(1 for r in top_inq if r.get("source") == "central")
    local_missing_link = sum(1 for r in local if is_empty(r.get("servDtlLink")))

    # 그래프
    barh(by_sido, "지자체 정책 수 (시도별)", "by_sido.png")
    barh(life, "생애주기별 정책 수 (중복 포함)", "by_life.png")
    barh(theme, "관심주제별 정책 수 (상위 12개, 중복 포함)", "by_theme.png", top=12)
    barh(pvsn, "제공 유형별 정책 수 (중복 포함)", "by_provision.png")
    barh(Counter({k: v for k, v in missing.items() if v}), "컬럼별 빈 값(결측치) 건수",
         "missing.png")

    # 요약 문서
    lines = [
        "# 복지 정책 데이터 현황",
        "",
        "> `python analysis/analyze_policies.py` 로 `seed.sql` 에서 자동 생성한 문서입니다.",
        "",
        "## 주요 발견",
        "",
        f"- 정책의 **{source['지자체'] / total:.0%}가 지자체 정책**이지만, 조회수 상위 10개 중 "
        f"**{top_central}개는 중앙부처 정책**입니다. 지자체 정책은 수는 많아도 잘 알려지지 않아, "
        "거주 지역 기반 추천이 필요한 근거가 됩니다.",
        f"- 상세 링크·온라인 신청 여부의 빈 값은 모두 지자체 정책입니다 "
        f"(지자체 {len(local):,}건 중 {local_missing_link:,}건). 지자체 수집 스크립트"
        "(`importLocal.py`)가 이 두 항목을 저장하지 않아 생긴 빈 값으로, 수집 단계의 개선 과제입니다.",
        f"- 제공 유형은 {multi_pvsn:,}건이 여러 값을 쉼표로 묶어 저장하고 있고 띄어쓰기도 "
        "제각각이라, 값을 나눠 정리한 뒤 집계했습니다.",
        "",
        "## 1. 데이터 품질 점검",
        "",
        "| 항목 | 결과 |",
        "| --- | --- |",
        f"| 전체 정책 수 | **{total:,}건** (중앙부처 {source['중앙부처']:,} · 지자체 {source['지자체']:,}) |",
        f"| 정책 ID 중복 | {len(dup_ids)}건 |",
        f"| 상세 정보(servdetail) 연결 | {total - no_detail:,}건 연결 · {no_detail:,}건 미연결 |",
        "",
        "**컬럼별 빈 값(결측치)**",
        "",
        "| 컬럼 | 빈 값 | 비율 |",
        "| --- | ---: | ---: |",
    ]
    for label, v in missing.most_common():
        lines.append(f"| {label} | {v:,} | {v / total:.1%} |")
    lines += [
        "",
        "![결측치](missing.png)",
        "",
        "## 2. 출처 · 지역",
        "",
        md_table(source, "출처", total),
        "",
        "![시도별](by_sido.png)",
        "",
        "## 3. 정책 특성",
        "",
        "하나의 정책이 여러 생애주기·주제에 해당할 수 있어 합계는 전체 건수보다 큽니다.",
        "",
        "![생애주기](by_life.png)",
        "",
        "![관심주제](by_theme.png)",
        "",
        "![제공 유형](by_provision.png)",
        "",
        "**가구 유형 (중복 포함)**",
        "",
        md_table(target, "가구 유형", total),
        "",
        "**지원 주기**",
        "",
        md_table(cycle, "지원 주기", total),
        "",
        "## 4. 조회수 상위 10개 정책",
        "",
        "| 순위 | 정책명 | 출처 | 조회수 |",
        "| ---: | --- | --- | ---: |",
    ]
    for i, r in enumerate(top_inq, 1):
        src = "중앙부처" if r.get("source") == "central" else (r.get("ctpvNm") or "지자체")
        lines.append(f"| {i} | {r['servNm']} | {src} | {int(r['inqNum']):,} |")
    lines.append("")

    with open(os.path.join(OUT_DIR, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"정책 {total:,}건 · 상세 {len(details):,}건 분석 완료 → {OUT_DIR}")


if __name__ == "__main__":
    main()
