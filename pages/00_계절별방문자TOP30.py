# =========================================================
# pages/1_🌸_계절별_TOP30.py
# -----------------------------------------------------------
# 스트림릿의 "여러 페이지(multipage) 앱" 기능을 사용한 새 페이지입니다.
# main.py와 같은 폴더 안에 pages/ 폴더를 두면, 스트림릿이 자동으로
# 사이드바에 페이지 전환 메뉴를 만들어줍니다. (별도 설정 코드가 필요 없습니다)
#
# 이 페이지는 전국 시/군/구 중에서, 계절별(봄/여름/가을/겨울)로
# "외지인 + 외국인" 방문객수를 합산했을 때 가장 많았던 상위 30개 지역을
# 계절마다 다른 색 그라데이션 그래프로 보여줍니다.
# (현지인(그 지역에 사는 사람) 데이터는 관광객이라 보기 어려워 제외했습니다)
#
# main.py에서 쓰는 것과 똑같은 데이터(한국관광공사 관광 빅데이터
# DataLabService의 '기초 지자체 지역방문자수')를 사용하며,
# datalab_utils.py에 있는 공통 함수를 그대로 불러다 씁니다.
# (같은 함수를 쓰기 때문에, main.py에서 이미 데이터를 한 번 불러왔다면
# 캐시를 그대로 재사용해서 이 페이지도 빠르게 열립니다)
# =========================================================

import streamlit as st
import pandas as pd
import plotly.express as px

from datalab_utils import (
    TOURNUM_API_KEY,
    SIDO_CODE_TO_NAME,
    MONTH_TO_SEASON,
    SEASON_ORDER,
    get_locgo_visitor_year,
)

# 페이지 기본 설정 (이 페이지만의 제목/아이콘)
st.set_page_config(
    page_title="계절별 방문자 TOP30",
    page_icon="🌸",
    layout="wide",
)

VISITOR_CHART_YEAR = 2025  # main.py와 동일하게 2025년 데이터만 사용합니다.
TOP_N = 30  # 계절별로 보여줄 순위 개수

# 계절마다 그래프 색을 다르게 주기 위한 그라데이션(연속 색상) 팔레트입니다.
# 값이 클수록(방문객이 많을수록) 색이 진해지는 방식이라 순위가 한눈에 들어옵니다.
SEASON_COLOR_SCALE = {
    "🌱 봄": "Greens",
    "☀️ 여름": "Blues",
    "🍂 가을": "Oranges",
    "❄️ 겨울": "Purples",
}

st.title("🌸 계절별 방문자 TOP30 (전국 시/군/구)")
st.caption(
    "2025년 데이터를 기준으로, 계절별 '외지인 + 외국인' 방문객수가 가장 많았던 "
    "전국 시/군/구 상위 30곳을 보여줍니다. (현지인 데이터는 제외)"
)

if not TOURNUM_API_KEY:
    st.error("⚠️ TOURNUM_API_KEY 시크릿이 설정되지 않았습니다. 스트림릿 클라우드 Secrets에 등록해주세요.")
    st.stop()

# 전국 시/군/구의 1년치 방문객수 데이터를 통째로 가져옵니다.
# (지역 필터가 없는 API라 항상 전국 데이터를 받아온 뒤 우리가 직접 계절/지역별로 정리합니다)
with st.spinner("전국 방문객수 데이터를 불러오는 중입니다... (처음 조회할 때는 시간이 다소 걸릴 수 있어요)"):
    yearly_items = get_locgo_visitor_year(VISITOR_CHART_YEAR)

if not yearly_items:
    st.info("방문객수 데이터를 가져오지 못했습니다. 인증키 또는 API 상태를 확인해주세요.")
    st.stop()

df = pd.DataFrame(yearly_items)

# 관광객수(touNum)는 숫자로, 기준연월일(baseYmd)의 월(月)로 계절을 구분합니다.
df["touNum"] = pd.to_numeric(df["touNum"], errors="coerce")
df["월"] = df["baseYmd"].astype(str).str[4:6].astype(int)
df["계절"] = df["월"].map(MONTH_TO_SEASON)

# 관광객구분(touDivNm)에서 "외지인"과 "외국인"만 남기고, 현지인은 제외합니다.
# (touDivCd 기준: 1=현지인, 2=외지인, 3=외국인 이지만, 이름으로 걸러내는 것이 더 안전합니다)
df = df[df["touDivNm"].isin(["외지인(b)", "외국인(c)"])].copy()

# signguCode 앞 2자리로 시/도 이름을 찾아서 "서울 종로구"처럼 지역명을 만듭니다.
# (전국 데이터다 보니 다른 시/도에 이름이 같은 시/군/구가 있을 수 있어 구분이 필요합니다)
df["시도"] = df["signguCode"].astype(str).str[:2].map(SIDO_CODE_TO_NAME)
df["지역명"] = df["시도"].fillna("") + " " + df["signguNm"]

# 지역(시/군/구) x 계절별로 방문객수(외지인+외국인 합계)를 합산합니다.
season_region_total = df.groupby(["계절", "지역명"], as_index=False)["touNum"].sum()

st.markdown("---")

# 계절 4개를 2행 x 2열로 배치해서 한눈에 비교할 수 있게 보여줍니다.
season_rows = [SEASON_ORDER[0:2], SEASON_ORDER[2:4]]

for row_seasons in season_rows:
    cols = st.columns(2)
    for col, season in zip(cols, row_seasons):
        with col:
            top_n_df = (
                season_region_total[season_region_total["계절"] == season]
                .sort_values("touNum", ascending=False)
                .head(TOP_N)
            )

            if top_n_df.empty:
                st.info(f"{season} 데이터를 찾을 수 없습니다.")
                continue

            # 가로 막대 그래프는 아래에서 위로 그려지므로, 1위가 맨 위에 오도록 오름차순으로 정렬해서 넣습니다.
            top_n_df = top_n_df.sort_values("touNum")

            fig = px.bar(
                top_n_df,
                x="touNum",
                y="지역명",
                orientation="h",
                color="touNum",  # 값(방문객수)에 따라 색이 점점 진해지는 그라데이션을 적용합니다.
                color_continuous_scale=SEASON_COLOR_SCALE.get(season, "Blues"),
                labels={"touNum": "방문객수(명)", "지역명": "시/군/구"},
                title=f"{season} 외지인·외국인 방문자 TOP{TOP_N}",
            )
            # 막대가 30개라 세로 공간을 넉넉하게 잡아야 라벨이 겹치지 않습니다.
            fig.update_layout(
                margin=dict(l=10, r=10, t=50, b=10),
                xaxis_tickformat=",.0f",
                height=850,
                coloraxis_showscale=False,  # 그래프마다 색상 범례를 따로 두지 않아 깔끔하게 보이도록 함
            )
            fig.update_traces(
                hovertemplate="%{y}<br>방문객수: %{x:,.0f}명<extra></extra>",
                marker_line_color="rgba(0,0,0,0.15)",
                marker_line_width=0.5,
            )
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption(
    "데이터 출처: 한국관광공사 관광 빅데이터 DataLabService(locgoRegnVisitrDDList) · "
    "본 페이지는 TOURNUM_API_KEY 인증키가 필요합니다."
)
