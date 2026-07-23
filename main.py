# =========================================================
# 한국관광공사 위치기반 관광정보 대시보드 (main.py)
# -----------------------------------------------------------
# 이 앱은 한국관광공사 TourAPI(KorService2)를 이용해서
# 시/도 + 시/군/구를 선택하면 아래 정보들을 조회해주는 스트림릿 대시보드입니다.
#   0) 선택한 지역 위치를 대한민국 지도 위에 표시
#   1) 행사정보      (/searchFestival2)
#   2) 숙박정보      (/searchStay2)
#   3) 공통정보      (/detailCommon2)
#   4) 개요정보      (/detailCommon2 의 overview 항목)
#   5) 반려동물 동반 여행정보 (/detailPetTour2)
#
# 인증키(서비스키)는 절대 코드에 직접 쓰지 않고,
# 스트림릿 클라우드의 "Secrets"(비밀 금고)에서 불러옵니다.
# .streamlit/secrets.toml 파일 또는 배포 설정의 Secrets 에
#   TOUR_API_KEY = "여기에_발급받은_인증키"
# 형태로 넣어두면 됩니다.
# =========================================================

import time
import calendar
from datetime import date

import streamlit as st
import pandas as pd
import requests

# ---------------------------------------------------------
# 1. 기본 설정
# ---------------------------------------------------------

# 페이지 기본 설정 (제목, 아이콘, 레이아웃)
st.set_page_config(
    page_title="한국관광공사 위치기반 관광정보 대시보드",
    page_icon="🗺️",
    layout="wide",
)

# TourAPI(KorService2)의 기본 주소(엔드포인트)
BASE_URL = "https://apis.data.go.kr/B551011/KorService2"

# 인증키는 코드에 직접 쓰지 않고 st.secrets 에서 불러옵니다.
# 스트림릿 클라우드 배포 시 "Settings > Secrets"에 TOUR_API_KEY를 등록해야 합니다.
try:
    TOUR_API_KEY = st.secrets["TOUR_API_KEY"]
except Exception:
    TOUR_API_KEY = None


# ---------------------------------------------------------
# 2. 지역 코드 (시/도) / 콘텐츠 타입 코드 (TourAPI 공식 코드표)
# ---------------------------------------------------------
# 지역코드조회(areaCode2)는 공식 문서상 "미사용 예정" 표시가 있지만,
# 시/군/구 목록을 동적으로 받아오기 위한 유일한 공식 방법이라 계속 사용합니다.
# 시/도(대분류) 코드는 자주 바뀌지 않으므로 앱 안에 직접 정리해두었고,
# 시/군/구(소분류) 목록은 아래 함수에서 API로 실시간 조회합니다.
AREA_CODES = {
    "서울": "1",
    "인천": "2",
    "대전": "3",
    "대구": "4",
    "광주": "5",
    "부산": "6",
    "울산": "7",
    "세종특별자치시": "8",
    "경기도": "31",
    "강원도": "32",
    "충청북도": "33",
    "충청남도": "34",
    "경상북도": "35",
    "경상남도": "36",
    "전라북도": "37",
    "전라남도": "38",
    "제주도": "39",
}

# 지도에 대략적인 위치를 바로 보여주기 위한 시/도 대표 좌표(위도, 경도)
# (시/군/구를 선택하면 아래 geocode_region 함수가 더 정확한 좌표로 갱신합니다)
AREA_CENTER_COORDS = {
    "서울": (37.5665, 126.9780),
    "인천": (37.4563, 126.7052),
    "대전": (36.3504, 127.3845),
    "대구": (35.8714, 128.6014),
    "광주": (35.1595, 126.8526),
    "부산": (35.1796, 129.0756),
    "울산": (35.5384, 129.3114),
    "세종특별자치시": (36.4801, 127.2890),
    "경기도": (37.4138, 127.5183),
    "강원도": (37.8228, 128.1555),
    "충청북도": (36.6357, 127.4917),
    "충청남도": (36.5184, 126.8000),
    "경상북도": (36.4919, 128.8889),
    "경상남도": (35.4606, 128.2132),
    "전라북도": (35.7175, 127.1530),
    "전라남도": (34.8161, 126.4629),
    "제주도": (33.4996, 126.5312),
}

# 관광 콘텐츠 타입 코드 (공통정보/반려동물 조회 등에 사용)
CONTENT_TYPES = {
    "관광지": "12",
    "문화시설": "14",
    "축제공연행사": "15",
    "여행코스": "25",
    "레포츠": "28",
    "숙박": "32",
    "쇼핑": "38",
    "음식점": "39",
}

# 행사정보를 계절별로 조회하기 위한 계절 -> (시작월, 종료월) 매핑
# 겨울은 12월에 시작해서 다음 해 2월에 끝나는 것으로 처리합니다.
SEASON_MONTHS = {
    "🌱 봄 (3월~5월)": (3, 5),
    "☀️ 여름 (6월~8월)": (6, 8),
    "🍂 가을 (9월~11월)": (9, 11),
    "❄️ 겨울 (12월~2월)": (12, 2),
}


def get_season_date_range(year: int, season_key: str):
    """
    선택한 연도와 계절을 실제 조회 시작일/종료일(date)로 변환합니다.
    예: 2026년 겨울 -> 2026-12-01 ~ 2027-02-28
    """
    start_month, end_month = SEASON_MONTHS[season_key]
    start_date = date(year, start_month, 1)

    if start_month > end_month:
        # 겨울처럼 해를 넘기는 계절 (12월 -> 다음 해 2월)
        end_year = year + 1
    else:
        end_year = year

    last_day_of_end_month = calendar.monthrange(end_year, end_month)[1]
    end_date = date(end_year, end_month, last_day_of_end_month)
    return start_date, end_date


# ---------------------------------------------------------
# 3. API 호출 공통 함수
# ---------------------------------------------------------
def request_with_retry(url: str, params: dict, headers: dict = None, timeout: int = 20, retries: int = 2):
    """
    공공데이터포털 서버가 가끔 응답이 느려서(Read timed out) 실패하는 경우를 대비해
    같은 요청을 몇 번 더 시도해보는 함수입니다.

    timeout: 한 번 요청에 최대로 기다리는 시간(초)
    retries: 실패했을 때 추가로 재시도하는 횟수
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))  # 재시도 전 잠깐 대기 (점점 길게)
                continue
    # 재시도까지 모두 실패하면 마지막 에러를 그대로 발생시킵니다.
    raise last_error


def call_tour_api(operation: str, extra_params: dict) -> list:
    """
    TourAPI(KorService2)의 특정 기능(operation)을 호출하고
    결과 아이템 리스트를 돌려주는 공통 함수입니다.
    화면에 에러 메시지를 보여주는 용도(버튼 클릭 시 조회)로 사용합니다.

    operation: 예) "searchFestival2", "searchStay2", "detailCommon2" 등
    extra_params: 각 기능별로 추가로 필요한 파라미터(딕셔너리)
    """
    if not TOUR_API_KEY:
        st.error(
            "TOUR_API_KEY가 설정되지 않았습니다. "
            "스트림릿 클라우드의 Secrets에 TOUR_API_KEY를 등록해주세요."
        )
        return []

    # 모든 기능에서 공통으로 필요한 기본 파라미터
    params = {
        "serviceKey": TOUR_API_KEY,   # 공공데이터포털에서 발급받은 인증키
        "MobileOS": "ETC",            # 서비스를 사용하는 기기 종류(필수값)
        "MobileApp": "TourDashboard", # 앱 이름(필수값, 자유롭게 지정 가능)
        "_type": "json",              # 응답을 JSON 형태로 받기
        "numOfRows": 30,              # 한 번에 가져올 결과 개수
        "pageNo": 1,                  # 페이지 번호
    }
    # 기능별 추가 파라미터를 합쳐줍니다.
    params.update(extra_params)

    url = f"{BASE_URL}/{operation}"

    try:
        # 공공데이터포털 서버가 느릴 때가 있어 자동으로 몇 번 재시도합니다.
        response = request_with_retry(url, params, timeout=20, retries=2)
    except requests.exceptions.Timeout:
        st.error(
            "⏱️ 공공데이터포털 서버 응답이 지연되고 있습니다 (여러 번 재시도했지만 실패했습니다). "
            "잠시 후 '조회' 버튼을 다시 눌러주세요."
        )
        return []
    except requests.exceptions.RequestException as e:
        st.error(f"API 요청 중 오류가 발생했습니다: {e}")
        return []

    # 공공데이터포털은 오류일 때 XML을 주는 경우가 있어 JSON 변환을 시도합니다.
    try:
        data = response.json()
    except ValueError:
        st.error("응답을 JSON으로 해석할 수 없습니다. 인증키 또는 요청 값을 확인해주세요.")
        st.code(response.text[:500])
        return []

    # 정상 응답 구조: data['response']['body']['items']['item']
    try:
        header = data["response"]["header"]
        result_code = header.get("resultCode")

        if result_code != "0000":
            st.warning(f"API 응답 코드: {result_code} / 메시지: {header.get('resultMsg')}")
            return []

        body = data["response"]["body"]

        # 결과가 없으면 items가 빈 문자열("")로 오는 경우가 있습니다.
        items = body.get("items")
        if not items or items == "":
            return []

        item = items.get("item")
        if item is None:
            return []

        # 결과가 1건이면 dict, 여러 건이면 list로 오므로 항상 list로 통일합니다.
        if isinstance(item, dict):
            return [item]
        return item

    except (KeyError, TypeError):
        st.error("응답 형식이 예상과 다릅니다.")
        st.json(data)
        return []


def fetch_area_code_items_silent(area_code: str = None) -> list:
    """
    areaCode2를 호출하는 조용한(에러 메시지를 화면에 띄우지 않는) 버전입니다.
    시/군/구 목록처럼 화면이 그려질 때마다 자동으로 호출되는 곳에서 사용합니다.
    """
    if not TOUR_API_KEY:
        return []

    params = {
        "serviceKey": TOUR_API_KEY,
        "MobileOS": "ETC",
        "MobileApp": "TourDashboard",
        "_type": "json",
        "numOfRows": 100,
        "pageNo": 1,
    }
    if area_code:
        params["areaCode"] = area_code

    try:
        response = request_with_retry(f"{BASE_URL}/areaCode2", params, timeout=20, retries=2)
        data = response.json()
        body = data["response"]["body"]
        items = body.get("items")
        if not items or items == "":
            return []
        item = items.get("item")
        if item is None:
            return []
        if isinstance(item, dict):
            return [item]
        return item
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_sigungu_list(area_code: str):
    """
    선택한 시/도(area_code)에 속한 시/군/구 목록을 가져옵니다.
    반복 조회를 줄이기 위해 1시간 동안 결과를 캐시(임시 저장)합니다.
    반환값 예: {"강남구": "1", "강동구": "2", ...}
    """
    items = fetch_area_code_items_silent(area_code)
    result = {}
    for it in items:
        name = it.get("name")
        code = it.get("code")
        if name and code:
            result[name] = code
    return result


@st.cache_data(ttl=86400, show_spinner=False)
def geocode_region(sido_name: str, sigungu_name: str = ""):
    """
    시/도(+시/군/구) 이름으로 대략적인 위도/경도를 찾아옵니다.
    OpenStreetMap의 무료 지오코딩 서비스(Nominatim)를 사용하며,
    별도의 인증키가 필요 없습니다. 하루 동안 결과를 캐시합니다.
    실패하면 시/도 대표 좌표(AREA_CENTER_COORDS)로 대신 사용합니다.
    """
    query = f"대한민국 {sido_name} {sigungu_name}".strip()
    try:
        response = request_with_retry(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "kr"},
            headers={"User-Agent": "streamlit-tour-dashboard (educational use)"},
            timeout=15,
            retries=1,
        )
        results = response.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return lat, lon
    except Exception:
        pass

    # 지오코딩에 실패하면 시/도 대표 좌표라도 보여줍니다.
    return AREA_CENTER_COORDS.get(sido_name)


# ---------------------------------------------------------
# 4. 화면 구성 - 사이드바 (지역 선택: 시/도 -> 시/군/구)
# ---------------------------------------------------------
st.title("🗺️ 한국관광공사 위치기반 관광정보 대시보드")
st.caption("시/도와 시/군/구를 선택하면 지도에 위치가 표시되고, 원하는 정보 탭에서 관광 정보를 조회할 수 있습니다.")

with st.sidebar:
    st.header("🔎 검색 조건")

    # 1단계: 시/도 선택
    selected_sido_name = st.selectbox("시/도를 선택하세요", list(AREA_CODES.keys()))
    selected_sido_code = AREA_CODES[selected_sido_name]

    # 2단계: 선택한 시/도에 속한 시/군/구 목록을 API로 조회
    with st.spinner("시/군/구 목록을 불러오는 중입니다..."):
        sigungu_map = get_sigungu_list(selected_sido_code)

    if sigungu_map:
        sigungu_options = ["전체"] + list(sigungu_map.keys())
    else:
        sigungu_options = ["전체"]

    selected_sigungu_name = st.selectbox("시/군/구를 선택하세요", sigungu_options)

    if selected_sigungu_name == "전체":
        selected_sigungu_code = None
    else:
        selected_sigungu_code = sigungu_map.get(selected_sigungu_name)

    st.markdown("---")
    st.caption(
        "※ 공통정보 / 개요정보 / 반려동물 동반 정보는 "
        "콘텐츠ID(contentId)가 필요합니다. "
        "아래 탭에서 목록을 먼저 검색한 뒤 항목을 선택하면 자동으로 조회됩니다."
    )

    if not TOUR_API_KEY:
        st.error("⚠️ TOUR_API_KEY 시크릿이 설정되지 않았습니다.")


# ---------------------------------------------------------
# 5. 선택한 지역 위치를 대한민국 지도 위에 표시
# ---------------------------------------------------------
st.subheader("📍 선택한 지역 위치")

# 시/군/구까지 선택했으면 더 정확한 좌표를, 시/도만 선택했으면 시/도 대표 좌표를 사용합니다.
if selected_sigungu_name != "전체":
    coords = geocode_region(selected_sido_name, selected_sigungu_name)
    location_label = f"{selected_sido_name} {selected_sigungu_name}"
else:
    coords = AREA_CENTER_COORDS.get(selected_sido_name)
    location_label = selected_sido_name

if coords:
    lat, lon = coords
    st.write(f"**현재 선택 지역:** {location_label}  (위도: {lat:.4f}, 경도: {lon:.4f})")
    map_df = pd.DataFrame({"lat": [lat], "lon": [lon]})
    # st.map은 스트림릿에 기본 내장된 지도 위젯이라 별도 라이브러리 설치가 필요 없습니다.
    st.map(map_df, zoom=9, size=200)
else:
    st.info("선택한 지역의 좌표를 찾지 못했습니다.")


# ---------------------------------------------------------
# 6. 탭 구성
# ---------------------------------------------------------
tab_festival, tab_stay, tab_detail = st.tabs(
    ["🎉 행사정보", "🏨 숙박정보", "📋 공통·개요·반려동물 정보"]
)


# ===========================================================
# 탭 1) 행사정보 (searchFestival2)
# ===========================================================
with tab_festival:
    st.subheader(f"'{location_label}' 지역의 행사정보")
    st.caption("날짜를 직접 입력하는 대신, 연도와 계절을 선택하면 해당 기간의 행사정보를 조회합니다.")

    col_year, col_season = st.columns(2)

    # 연도 선택 (작년 ~ 내년+1 범위로 제공, 기본값은 올해)
    current_year = pd.Timestamp.today().year
    year_options = list(range(current_year - 1, current_year + 3))
    selected_year = col_year.selectbox("연도를 선택하세요", year_options, index=year_options.index(current_year))

    # 계절 선택
    selected_season = col_season.selectbox("계절을 선택하세요", list(SEASON_MONTHS.keys()))

    # 선택한 연도 + 계절을 실제 날짜 범위로 변환 (겨울은 다음 해 2월까지 자동 계산)
    season_start, season_end = get_season_date_range(selected_year, selected_season)
    st.caption(f"📅 조회 기간: {season_start.strftime('%Y년 %m월 %d일')} ~ {season_end.strftime('%Y년 %m월 %d일')}")

    if st.button("행사정보 조회", key="btn_festival"):
        params = {
            "areaCode": selected_sido_code,
            "eventStartDate": season_start.strftime("%Y%m%d"),
            "eventEndDate": season_end.strftime("%Y%m%d"),
            "arrange": "A",  # A: 제목순 정렬
        }
        # 시/군/구까지 선택한 경우에만 sigunguCode를 추가합니다.
        if selected_sigungu_code:
            params["sigunguCode"] = selected_sigungu_code

        with st.spinner("행사정보를 불러오는 중입니다..."):
            festival_items = call_tour_api("searchFestival2", params)

        if festival_items:
            df = pd.DataFrame(festival_items)
            # 화면에 보여줄 주요 컬럼만 정리 (없는 컬럼은 자동으로 무시)
            show_cols = [c for c in ["title", "eventstartdate", "eventenddate", "addr1", "tel"] if c in df.columns]
            # 행사 시작일 순으로 정렬해서 보여줍니다.
            if "eventstartdate" in df.columns:
                df = df.sort_values("eventstartdate")
            st.dataframe(df[show_cols], use_container_width=True)
            st.caption(f"총 {len(df)}건의 행사가 {selected_season.split(' ')[1]}({selected_year}년 기준) 기간에 조회되었습니다.")
        else:
            st.info("해당 계절 기간에 조회된 행사정보가 없습니다.")


# ===========================================================
# 탭 2) 숙박정보 (searchStay2)
# ===========================================================
with tab_stay:
    st.subheader(f"'{location_label}' 지역의 숙박정보")

    if st.button("숙박정보 조회", key="btn_stay"):
        params = {
            "areaCode": selected_sido_code,
            "arrange": "A",  # A: 제목순 정렬
        }
        if selected_sigungu_code:
            params["sigunguCode"] = selected_sigungu_code

        with st.spinner("숙박정보를 불러오는 중입니다..."):
            stay_items = call_tour_api("searchStay2", params)

        if stay_items:
            df = pd.DataFrame(stay_items)
            show_cols = [c for c in ["title", "addr1", "tel", "firstimage"] if c in df.columns]
            st.dataframe(df[show_cols], use_container_width=True)
        else:
            st.info("조회된 숙박정보가 없습니다.")


# ===========================================================
# 탭 3) 공통정보 / 개요정보 / 반려동물 동반 여행정보
#       (지역기반 목록 조회 -> 항목 선택 -> 상세 조회)
# ===========================================================
with tab_detail:
    st.subheader(f"'{location_label}' 지역의 관광정보 상세 조회")
    st.caption("먼저 콘텐츠 타입을 선택해 목록을 검색하고, 아래에서 항목을 선택하세요.")

    selected_content_name = st.selectbox("콘텐츠 타입을 선택하세요", list(CONTENT_TYPES.keys()))
    selected_content_type = CONTENT_TYPES[selected_content_name]

    if st.button("목록 조회", key="btn_area_list"):
        params = {
            "areaCode": selected_sido_code,
            "contentTypeId": selected_content_type,
            "arrange": "A",
        }
        if selected_sigungu_code:
            params["sigunguCode"] = selected_sigungu_code

        with st.spinner("목록을 불러오는 중입니다..."):
            # 지역기반 관광정보조회(areaBasedList2)로 콘텐츠 목록을 가져옵니다.
            area_items = call_tour_api("areaBasedList2", params)
        # 세션 상태에 저장해서 버튼을 다시 눌러도 유지되게 합니다.
        st.session_state["area_items"] = area_items

    area_items = st.session_state.get("area_items", [])

    if area_items:
        # 제목 목록으로 selectbox 구성 (title -> contentid 매핑)
        title_to_id = {item.get("title", "제목없음"): item.get("contentid") for item in area_items}
        selected_title = st.selectbox("상세 정보를 볼 항목을 선택하세요", list(title_to_id.keys()))
        selected_content_id = title_to_id[selected_title]

        st.markdown(f"**선택한 콘텐츠 ID**: `{selected_content_id}`")

        col1, col2, col3 = st.columns(3)
        show_common = col1.button("📋 공통정보 보기", key="btn_common")
        show_overview = col2.button("📝 개요정보 보기", key="btn_overview")
        show_pet = col3.button("🐾 반려동물 동반 정보 보기", key="btn_pet")

        # -------------------------------------------------
        # 공통정보 (detailCommon2)
        # -------------------------------------------------
        if show_common:
            with st.spinner("공통정보를 불러오는 중입니다..."):
                common_items = call_tour_api(
                    "detailCommon2",
                    {
                        "contentId": selected_content_id,
                        "contentTypeId": selected_content_type,
                        "defaultYN": "Y",   # 기본정보 포함
                        "addrinfoYN": "Y",  # 주소정보 포함
                        "mapinfoYN": "Y",   # 좌표정보 포함
                        "overviewYN": "N",  # 개요는 별도 버튼에서 조회
                    },
                )
            if common_items:
                info = common_items[0]
                st.write("**제목:**", info.get("title", "-"))
                st.write("**주소:**", info.get("addr1", "-"), info.get("addr2", ""))
                st.write("**전화번호:**", info.get("tel", "-"))
                st.write("**홈페이지:**", info.get("homepage", "-"))
                if info.get("firstimage"):
                    st.image(info.get("firstimage"), width=400)

                # 이 콘텐츠의 좌표(mapx=경도, mapy=위도)가 있으면 지도에도 표시합니다.
                if info.get("mapx") and info.get("mapy"):
                    try:
                        item_lon = float(info["mapx"])
                        item_lat = float(info["mapy"])
                        st.map(pd.DataFrame({"lat": [item_lat], "lon": [item_lon]}), zoom=13, size=100)
                    except (TypeError, ValueError):
                        pass

                with st.expander("전체 원본 데이터 보기"):
                    st.json(info)
            else:
                st.info("공통정보를 찾을 수 없습니다.")

        # -------------------------------------------------
        # 개요정보 (detailCommon2 의 overview 필드)
        # -------------------------------------------------
        if show_overview:
            with st.spinner("개요정보를 불러오는 중입니다..."):
                overview_items = call_tour_api(
                    "detailCommon2",
                    {
                        "contentId": selected_content_id,
                        "contentTypeId": selected_content_type,
                        "defaultYN": "Y",
                        "overviewYN": "Y",  # 개요정보 포함 요청
                    },
                )
            if overview_items:
                overview_text = overview_items[0].get("overview", "")
                if overview_text:
                    st.write(overview_text)
                else:
                    st.info("등록된 개요정보가 없습니다.")
            else:
                st.info("개요정보를 찾을 수 없습니다.")

        # -------------------------------------------------
        # 반려동물 동반 여행정보 (detailPetTour2)
        # -------------------------------------------------
        if show_pet:
            with st.spinner("반려동물 동반 여행정보를 불러오는 중입니다..."):
                pet_items = call_tour_api(
                    "detailPetTour2",
                    {
                        "contentId": selected_content_id,
                    },
                )
            if pet_items:
                info = pet_items[0]
                st.write("**동반 가능 정보:**", info.get("acmpyTypeCd", "-"))
                st.write("**반려동물 관련 안내:**", info.get("relaAcdntRiskMtr", "-"))
                with st.expander("전체 원본 데이터 보기"):
                    st.json(info)
            else:
                st.info("반려동물 동반 여행정보가 없습니다. (해당 콘텐츠는 반려동물 동반 정보가 등록되지 않았을 수 있습니다.)")
    else:
        st.info("먼저 '목록 조회' 버튼을 눌러 콘텐츠 목록을 불러오세요.")


# ---------------------------------------------------------
# 7. 하단 안내
# ---------------------------------------------------------
st.markdown("---")
st.caption(
    "데이터 출처: 한국관광공사 TourAPI(KorService2) · 위치 좌표: OpenStreetMap Nominatim · "
    "본 대시보드는 공공데이터포털에서 발급받은 인증키가 필요합니다."
)
