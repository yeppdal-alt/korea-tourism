"""
계절 휴가 플래너 (단일 파일 버전)

흐름: 계절 버튼 4개 -> 계절별 인기 지역 -> 지역 클릭 시 관광지 Top10(카드 + 지도)
데이터: 한국관광공사 TourAPI 4.0 (KorService2)

배포: 이 파일 하나 + requirements.txt만 있으면 된다.
Streamlit Cloud > 앱 설정 > Secrets 에 아래처럼 등록:
    TOUR_API_KEY = "공공데이터포털에서_받은_디코딩_서비스키"
(Encoding 키를 넣으면 이중 인코딩되어 인증 오류가 난다. 반드시 "Decoding" 키 사용)
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
import requests

# ---------------------------------------------------------------------------
# 계절별 인기 지역 (큐레이션 데이터)
# TourAPI에는 "계절별 인기 지역" 랭킹 API가 없어서 직접 정한 목록이다.
# area_code는 TourAPI 시/도 단위 코드. 필요하면 자유롭게 추가/수정 가능.
# ---------------------------------------------------------------------------
SEASON_REGIONS = {
    "봄": [
        {"name": "경주", "area_code": "35", "desc": "벚꽃과 고도(古都) 유적"},
        {"name": "창원(진해)", "area_code": "36", "desc": "군항제 벚꽃길"},
        {"name": "전주", "area_code": "37", "desc": "한옥마을과 봄 골목"},
    ],
    "여름": [
        {"name": "강릉", "area_code": "32", "desc": "동해 바다와 해변"},
        {"name": "부산", "area_code": "6", "desc": "해운대·광안리 해수욕장"},
        {"name": "제주", "area_code": "39", "desc": "바다와 여름 액티비티"},
    ],
    "가을": [
        {"name": "속초", "area_code": "32", "desc": "설악산 단풍"},
        {"name": "정읍", "area_code": "37", "desc": "내장산 단풍 터널"},
        {"name": "경주", "area_code": "35", "desc": "가을 유적 산책"},
    ],
    "겨울": [
        {"name": "평창", "area_code": "32", "desc": "스키·눈꽃 명소"},
        {"name": "태백", "area_code": "32", "desc": "눈꽃 축제"},
        {"name": "인천", "area_code": "2", "desc": "겨울 도심 나들이"},
    ],
}
SEASON_EMOJI = {"봄": "🌸", "여름": "🌊", "가을": "🍁", "겨울": "⛄"}

CONTENT_TYPE_TOURIST_SPOT = "12"  # 관광지
TOUR_API_BASE_URL = "https://apis.data.go.kr/B551011/KorService2"


# ---------------------------------------------------------------------------
# TourAPI 호출 함수
# ---------------------------------------------------------------------------
class TourApiError(Exception):
    pass


def _get_service_key() -> str:
    key = st.secrets.get("TOUR_API_KEY", "")
    if not key:
        raise TourApiError(
            "TOUR_API_KEY가 설정되지 않았습니다. Streamlit Cloud > Settings > Secrets 에 등록하세요."
        )
    return key


def _call(operation: str, params: dict) -> dict:
    base_params = {
        "serviceKey": _get_service_key(),
        "MobileOS": "ETC",
        "MobileApp": "VacationPlanner",
        "_type": "json",
    }
    base_params.update(params)

    try:
        resp = requests.get(f"{TOUR_API_BASE_URL}/{operation}", params=base_params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        raise TourApiError(f"TourAPI 요청 실패: {e}") from e
    except ValueError as e:
        raise TourApiError(
            "TourAPI 응답을 해석할 수 없습니다. 서비스키 또는 일일 호출 한도를 확인하세요."
        ) from e

    response = data.get("response", {})
    header = response.get("header", {})
    if header.get("resultCode") != "0000":
        raise TourApiError(f"TourAPI 오류 [{header.get('resultCode')}]: {header.get('resultMsg')}")

    return response.get("body", {})


def _normalize_items(body: dict) -> list:
    items = body.get("items", "")
    if items == "" or items is None:
        return []
    item = items.get("item", [])
    if isinstance(item, dict):
        return [item]
    return item


@st.cache_data(ttl=3600, show_spinner=False)
def get_area_based_list(area_code: str, content_type_id: str = "12", num_of_rows: int = 10) -> list:
    params = {
        "areaCode": area_code,
        "contentTypeId": content_type_id,
        "numOfRows": num_of_rows,
        "pageNo": 1,
        "arrange": "O",
        "listYN": "Y",
    }
    body = _call("areaBasedList2", params)
    return _normalize_items(body)


@st.cache_data(ttl=3600, show_spinner=False)
def get_detail_overview(content_id: str, content_type_id: str = "12") -> str:
    try:
        body = _call(
            "detailCommon2",
            {
                "contentId": content_id,
                "contentTypeId": content_type_id,
                "defaultYN": "Y",
                "overviewYN": "Y",
                "firstImageYN": "N",
                "addrinfoYN": "N",
                "mapinfoYN": "N",
            },
        )
    except TourApiError:
        return ""
    items = _normalize_items(body)
    return items[0].get("overview", "") if items else ""


def truncate(text: str, length: int = 120) -> str:
    text = (text or "").strip()
    return text if len(text) <= length else text[:length].rstrip() + "…"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="계절 휴가 플래너", page_icon="🧳", layout="wide")

if "season" not in st.session_state:
    st.session_state.season = None
if "region" not in st.session_state:
    st.session_state.region = None


def select_season(season):
    st.session_state.season = season
    st.session_state.region = None


def select_region(region):
    st.session_state.region = region


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
            )
            st.caption(region.get("desc", ""))

if st.session_state.region:
    region = st.session_state.region
    st.subheader(f"3. {region['name']} 관광지 Top10")

    items, error = None, None
    with st.spinner(f"{region['name']} 관광지 정보를 불러오는 중..."):
        try:
            items = get_area_based_list(region["area_code"], CONTENT_TYPE_TOURIST_SPOT, 10)
        except TourApiError as e:
            error = str(e)

    if error:
        st.error(f"관광지 정보를 불러오지 못했습니다: {error}")
    elif not items:
        st.info("해당 지역의 관광지 정보를 찾지 못했습니다. 다른 지역을 선택해보세요.")
    else:
        map_points = []
        cols = st.columns(2)
        for idx, item in enumerate(items):
            col = cols[idx % 2]
            title = item.get("title", "이름 없음")
            addr = " ".join(p for p in [item.get("addr1", ""), item.get("addr2", "")] if p).strip()
            addr = addr or "주소 정보 없음"
            content_id = item.get("contentid", "")
            image_url = item.get("firstimage") or item.get("firstimage2")
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
                    map_points.append({"title": title, "lon": float(mapx), "lat": float(mapy)})
                except ValueError:
                    pass

        if map_points:
            st.subheader("📍 지도로 보기")
            center_lat = sum(p["lat"] for p in map_points) / len(map_points)
            center_lon = sum(p["lon"] for p in map_points) / len(map_points)
            fmap = folium.Map(location=[center_lat, center_lon], zoom_start=11)
            for p in map_points:
                folium.Marker([p["lat"], p["lon"]], popup=p["title"], tooltip=p["title"]).add_to(fmap)
            st_folium(fmap, use_container_width=True, height=450, returned_objects=[])
else:
    st.info("위에서 지역을 선택하면 관광지 Top10이 표시됩니다." if st.session_state.season else "위에서 계절을 선택해주세요.")
