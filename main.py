"""
한국관광공사 데이터 기반 휴가계획 앱 (Streamlit)

흐름: 계절 버튼 4개 -> 계절별 인기 지역 리스트 -> 지역 클릭 시 관광지 Top10
      (카드 + 지도)
"""

import streamlit as st
from streamlit_folium import st_folium
import folium

from config import SEASON_REGIONS, SEASON_EMOJI, CONTENT_TYPE_TOURIST_SPOT
from tour_api import get_area_based_list, get_detail_overview, get_detail_images, TourApiError

st.set_page_config(page_title="계절 휴가 플래너", page_icon="🧳", layout="wide")

if "season" not in st.session_state:
    st.session_state.season = None
if "region" not in st.session_state:
    st.session_state.region = None


def select_season(season: str) -> None:
    st.session_state.season = season
    st.session_state.region = None  # 계절이 바뀌면 지역 선택 초기화


def select_region(region: dict) -> None:
    st.session_state.region = region


def truncate(text: str, length: int = 120) -> str:
    text = (text or "").strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


st.title("🧳 계절별 휴가 플래너")
st.caption("한국관광공사 TourAPI 4.0 데이터를 기반으로 계절별 인기 지역과 관광지 Top10을 추천합니다.")

st.subheader("1. 계절을 선택하세요")
season_cols = st.columns(4)
for col, season in zip(season_cols, SEASON_REGIONS.keys()):
    with col:
        st.button(
            f"{SEASON_EMOJI[season]} {season}",
            use_container_width=True,
            type="primary" if st.session_state.season == season else "secondary",
            on_click=select_season,
            args=(season,),
        )

if st.session_state.season:
    season = st.session_state.season
    st.subheader(f"2. {SEASON_EMOJI[season]} {season} 인기 지역")

    regions = SEASON_REGIONS[season]
    region_cols = st.columns(len(regions))
    for col, region in zip(region_cols, regions):
        with col:
            st.button(
                region["name"],
                use_container_width=True,
                type="primary" if (
                    st.session_state.region and st.session_state.region["name"] == region["name"]
                ) else "secondary",
                on_click=select_region,
                args=(region,),
                help=region.get("desc", ""),
            )
            st.caption(region.get("desc", ""))

if st.session_state.region:
    region = st.session_state.region
    st.subheader(f"3. {region['name']} 관광지 Top10")

    with st.spinner(f"{region['name']} 관광지 정보를 불러오는 중..."):
        try:
            items = get_area_based_list(
                area_code=region["area_code"],
                sigungu_code=region.get("sigungu_code"),
                content_type_id=CONTENT_TYPE_TOURIST_SPOT,
                num_of_rows=10,
            )
        except TourApiError as e:
            items = None
            st.error(f"관광지 정보를 불러오지 못했습니다: {e}")

    if items is not None:
        if not items:
            st.info("해당 지역의 관광지 정보를 찾지 못했습니다. 다른 지역을 선택해보세요.")
        else:
            map_points = []

            cols = st.columns(2)
            for idx, item in enumerate(items):
                col = cols[idx % 2]
                title = item.get("title", "이름 없음")
                addr = " ".join(
                    part for part in [item.get("addr1", ""), item.get("addr2", "")] if part
                ).strip() or "주소 정보 없음"
                content_id = item.get("contentid", "")

                image_url = item.get("firstimage") or item.get("firstimage2")
                if not image_url and content_id:
                    fallback_images = get_detail_images(content_id)
                    image_url = fallback_images[0] if fallback_images else None

                overview = get_detail_overview(content_id) if content_id else ""

                with col:
                    with st.container(border=True):
                        if image_url:
                            st.image(image_url, use_container_width=True)
                        else:
                            st.markdown("🖼️ *이미지 없음*")
                        st.markdown(f"**{idx + 1}. {title}**")
                        st.caption(addr)
                        if overview:
                            st.write(truncate(overview))

                mapx, mapy = item.get("mapx"), item.get("mapy")
                if mapx and mapy:
                    try:
                        map_points.append(
                            {"title": title, "lon": float(mapx), "lat": float(mapy)}
                        )
                    except ValueError:
                        pass

            if map_points:
                st.subheader("📍 지도로 보기")
                center_lat = sum(p["lat"] for p in map_points) / len(map_points)
                center_lon = sum(p["lon"] for p in map_points) / len(map_points)
                fmap = folium.Map(location=[center_lat, center_lon], zoom_start=11)
                for p in map_points:
                    folium.Marker(
                        location=[p["lat"], p["lon"]],
                        popup=p["title"],
                        tooltip=p["title"],
                    ).add_to(fmap)
                st_folium(fmap, use_container_width=True, height=450, returned_objects=[])
else:
    if st.session_state.season:
        st.info("위에서 지역을 선택하면 관광지 Top10이 표시됩니다.")
    else:
        st.info("위에서 계절을 선택해주세요.")
