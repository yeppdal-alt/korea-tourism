# =========================================================
# 한국관광공사 위치기반 관광정보 대시보드 (main.py)
# -----------------------------------------------------------
# 이 앱은 한국관광공사 TourAPI(KorService2)를 이용해서
# 시/도 + 시/군/구를 선택하면 아래 정보들을 조회해주는 스트림릿 대시보드입니다.
#   0) 선택한 지역 위치를 대한민국 지도 위에 표시 (작게, 한글 지명 표시)
#   0-1) 계절별 방문객수 그래프 (DataLabService /metcoRegnVisitrDDList, /locgoRegnVisitrDDList)
#   1) 숙박정보      (/searchStay2)
#   2) 공통정보      (/detailCommon2)
#   3) 개요정보      (/detailCommon2 의 overview 항목)
#   4) 반려동물 동반 여행정보 (/detailPetTour2)
#
# ※ 행사정보(searchFestival2)는 API 응답이 계속 불안정하게 에러가 나서 이 버전에서는 뺐습니다.
#
# 인증키(서비스키)는 절대 코드에 직접 쓰지 않고,
# 스트림릿 클라우드의 "Secrets"(비밀 금고)에서 불러옵니다.
# .streamlit/secrets.toml 파일 또는 배포 설정의 Secrets 에
#   TOUR_API_KEY = "여기에_발급받은_TourAPI(KorService2) 인증키"
#   TOURNUM_API_KEY = "여기에_발급받은_DataLabService(방문자수) 인증키"
# 형태로 넣어두면 됩니다.
# =========================================================

import time

import streamlit as st
import pandas as pd
import requests
import plotly.express as px

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

# 관광 빅데이터(방문자수) DataLabService의 기본 주소(엔드포인트)
BASE_URL_DATALAB = "https://apis.data.go.kr/B551011/DataLabService"

# 인증키는 코드에 직접 쓰지 않고 st.secrets 에서 불러옵니다.
# 스트림릿 클라우드 배포 시 "Settings > Secrets"에 아래 두 개의 키를 등록해야 합니다.
try:
    TOUR_API_KEY = st.secrets["TOUR_API_KEY"]
except Exception:
    TOUR_API_KEY = None

try:
    TOURNUM_API_KEY = st.secrets["TOURNUM_API_KEY"]
except Exception:
    TOURNUM_API_KEY = None


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

# DataLabService의 방문자수 데이터는 areaNm(시도명)을 "서울특별시", "전라북도" 처럼
# 정식 명칭으로 내려줍니다. 우리 앱의 시/도 이름(AREA_CODES의 key)과 매칭하기 위한 표입니다.
# (지역 명칭이 개정되어도(예: 전라북도->전북특별자치도) 매칭되도록 여러 접두어를 등록해둡니다)
REGION_NAME_PREFIXES = {
    "서울": ["서울"],
    "인천": ["인천"],
    "대전": ["대전"],
    "대구": ["대구"],
    "광주": ["광주"],
    "부산": ["부산"],
    "울산": ["울산"],
    "세종특별자치시": ["세종"],
    "경기도": ["경기"],
    "강원도": ["강원"],
    "충청북도": ["충청북", "충북"],
    "충청남도": ["충청남", "충남"],
    "경상북도": ["경상북", "경북"],
    "경상남도": ["경상남", "경남"],
    "전라북도": ["전라북", "전북"],
    "전라남도": ["전라남", "전남"],
    "제주도": ["제주"],
}

# 기초 지자체(시/군/구) 방문자수 데이터(signguCode)는 5자리 숫자이고,
# 앞 2자리가 표준 시/도 코드입니다. 같은 이름의 시/군/구가 여러 시/도에 있을 수 있어
# (예: "중구"는 서울/부산/대구 등에 모두 있음) 시/도 코드로 먼저 좁힌 뒤 이름을 매칭합니다.
STANDARD_SIDO_CODE = {
    "서울": "11",
    "부산": "26",
    "대구": "27",
    "인천": "28",
    "광주": "29",
    "대전": "30",
    "울산": "31",
    "세종특별자치시": "36",
    "경기도": "41",
    "강원도": "42",
    "충청북도": "43",
    "충청남도": "44",
    "전라북도": "45",
    "전라남도": "46",
    "경상북도": "47",
    "경상남도": "48",
    "제주도": "50",
}

# 월(1~12) -> 계절 매핑 (봄:3~5월, 여름:6~8월, 가을:9~11월, 겨울:12~2월)
MONTH_TO_SEASON = {
    3: "🌱 봄", 4: "🌱 봄", 5: "🌱 봄",
    6: "☀️ 여름", 7: "☀️ 여름", 8: "☀️ 여름",
    9: "🍂 가을", 10: "🍂 가을", 11: "🍂 가을",
    12: "❄️ 겨울", 1: "❄️ 겨울", 2: "❄️ 겨울",
}
SEASON_ORDER = ["🌱 봄", "☀️ 여름", "🍂 가을", "❄️ 겨울"]

# 계절별 표를 월 단위로 펼쳐서 보여줄 때 사용할, 계절 안에서의 월 순서
# (겨울은 12월이 먼저 오도록 숫자 순서가 아니라 계절 흐름 순서를 씁니다)
SEASON_MONTH_ORDER = {
    "🌱 봄": [3, 4, 5],
    "☀️ 여름": [6, 7, 8],
    "🍂 가을": [9, 10, 11],
    "❄️ 겨울": [12, 1, 2],
}


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


def fetch_datalab_items(operation: str, start_ymd: str, end_ymd: str, page_size: int = 1000, max_pages: int = 40) -> list:
    """
    DataLabService(관광 빅데이터 방문자수)의 특정 기능을 호출해서
    페이지 단위로 나뉜 결과를 모두 모아 하나의 리스트로 돌려줍니다.
    (하루치 데이터가 지역x관광객구분별로 나뉘어 있어 결과가 많을 수 있습니다)
    """
    if not TOURNUM_API_KEY:
        return []

    all_items = []
    page_no = 1
    total_count = None

    while True:
        params = {
            "serviceKey": TOURNUM_API_KEY,
            "MobileOS": "ETC",
            "MobileApp": "TourDashboard",
            "_type": "json",
            "numOfRows": page_size,
            "pageNo": page_no,
            "startYmd": start_ymd,
            "endYmd": end_ymd,
        }

        try:
            response = request_with_retry(f"{BASE_URL_DATALAB}/{operation}", params, timeout=25, retries=2)
            data = response.json()
        except Exception:
            break  # 실패하면 지금까지 모은 데이터만이라도 돌려줍니다.

        try:
            header = data["response"]["header"]
            if header.get("resultCode") != "0000":
                break

            body = data["response"]["body"]
            if total_count is None:
                total_count = int(body.get("totalCount", 0) or 0)

            items = body.get("items")
            if not items or items == "":
                break
            item = items.get("item")
            if item is None:
                break
            if isinstance(item, dict):
                item = [item]
            all_items.extend(item)
        except (KeyError, TypeError, ValueError):
            break

        # 전체 결과를 다 모았거나, 페이지 요청이 너무 많아지면 중단합니다(안전장치).
        if total_count is not None and len(all_items) >= total_count:
            break
        if page_no >= max_pages:
            break
        page_no += 1

    return all_items


@st.cache_data(ttl=86400, show_spinner=False)
def get_metco_visitor_year(year: int):
    """
    광역 지자체(시/도) 단위 방문자수 데이터를 특정 연도 1년치(1/1~12/31) 통째로 가져옵니다.
    지역 필터가 없는 API라 한 번에 전국 데이터를 받아서, 화면에서 시/도만 골라 씁니다.
    같은 연도는 하루 동안 캐시해두어 반복 조회 시 API를 다시 호출하지 않습니다.
    (일일 트래픽이 1,000건으로 제한되어 있어 캐시가 중요합니다)
    """
    start_ymd = f"{year}0101"
    end_ymd = f"{year}1231"
    return fetch_datalab_items("metcoRegnVisitrDDList", start_ymd, end_ymd)


@st.cache_data(ttl=86400, show_spinner=False)
def get_locgo_visitor_year(year: int):
    """
    기초 지자체(시/군/구) 단위 방문자수 데이터를 특정 연도 1년치 통째로 가져옵니다.
    전국 모든 시/군/구 데이터를 하루 단위로 담고 있어 데이터 양이 매우 많으므로,
    (시/도 데이터보다 페이지 수를 훨씬 크게 잡아 가져옵니다)
    같은 연도는 하루 동안 캐시해서 반복 호출을 막습니다.
    """
    start_ymd = f"{year}0101"
    end_ymd = f"{year}1231"
    # 전국 시/군/구 x 365일 x 관광객구분(3) 데이터라 매우 많아서,
    # 한 페이지에 최대한 많이 받아오고(page_size) 페이지 수 제한도 넉넉히 잡습니다.
    return fetch_datalab_items("locgoRegnVisitrDDList", start_ymd, end_ymd, page_size=5000, max_pages=150)


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
    if not TOURNUM_API_KEY:
        st.warning("⚠️ TOURNUM_API_KEY 시크릿이 없으면 '계절별 방문객수' 그래프를 사용할 수 없습니다.")


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

# 지도를 화면 왼쪽의 좁은 칸(전체 폭의 약 1/4)에만 작게 표시하고,
# 오른쪽 칸에는 위치 정보 텍스트를 보여줍니다.
map_col, info_col = st.columns([1, 3])

with map_col:
    if coords:
        lat, lon = coords
        map_df = pd.DataFrame({"lat": [lat], "lon": [lon], "지명": [location_label]})

        # Plotly의 오픈스트리트맵(OpenStreetMap) 타일을 사용합니다.
        # 별도의 Mapbox 인증키 없이도 지도에 한글 지명이 표시됩니다.
        map_fig = px.scatter_mapbox(
            map_df,
            lat="lat",
            lon="lon",
            hover_name="지명",
            zoom=9,
            height=220,  # 지도 세로 크기를 작게 설정
        )
        map_fig.update_traces(marker=dict(size=14, color="red"))
        map_fig.update_layout(
            mapbox_style="open-street-map",
            margin=dict(l=0, r=0, t=0, b=0),  # 여백 최소화로 더 작게 보이게 함
        )
        st.plotly_chart(map_fig, use_container_width=True, config={"scrollZoom": False})
    else:
        st.info("좌표를 찾지 못했습니다.")

with info_col:
    if coords:
        lat, lon = coords
        st.write(f"**현재 선택 지역:** {location_label}")
        st.write(f"위도: {lat:.4f} / 경도: {lon:.4f}")
    else:
        st.write("선택한 지역의 좌표를 찾지 못했습니다.")


# ---------------------------------------------------------
# 6. 계절별 방문객수 (DataLabService)
#    - 시/군/구를 선택하지 않았으면 시/도 단위(metcoRegnVisitrDDList)
#    - 시/군/구까지 선택했으면 시/군/구 단위(locgoRegnVisitrDDList)
#    - 연도는 선택하지 않고 2025년 데이터만 고정으로 보여줍니다.
# ---------------------------------------------------------
VISITOR_CHART_YEAR = 2025  # 방문객수 그래프는 2025년 데이터만 조회합니다.

st.subheader(f"📊 '{location_label}' '25년 계절별 방문자수")

if not TOURNUM_API_KEY:
    st.error("⚠️ TOURNUM_API_KEY 시크릿이 설정되지 않았습니다. 스트림릿 클라우드 Secrets에 등록해주세요.")
else:
    is_sigungu_view = selected_sigungu_name != "전체"

    if is_sigungu_view:
        st.caption(
            "한국관광공사 관광 빅데이터(DataLab)의 '기초 지자체 지역방문자수' 데이터를 활용합니다(2025년 기준). "
            "시/군/구 단위는 전국 데이터 양이 매우 많아 처음 조회할 때 시간이 다소 걸릴 수 있어요."
        )
    else:
        st.caption("한국관광공사 관광 빅데이터(DataLab)의 '광역 지자체 지역방문자수' 데이터를 활용합니다(2025년 기준).")

    chart_year = VISITOR_CHART_YEAR
    run_visitor_query = st.button("방문객수 조회", key="btn_visitor")

    if run_visitor_query:
        region_df = pd.DataFrame()

        if not is_sigungu_view:
            # -------- 시/도 단위 --------
            with st.spinner("1년치 시/도 방문객수 데이터를 불러오는 중입니다..."):
                yearly_items = get_metco_visitor_year(chart_year)

            if yearly_items:
                df = pd.DataFrame(yearly_items)
                name_prefixes = REGION_NAME_PREFIXES.get(selected_sido_name, [selected_sido_name])
                mask = df["areaNm"].apply(lambda name: any(str(name).startswith(p) for p in name_prefixes))
                region_df = df[mask].copy()
        else:
            # -------- 시/군/구 단위 --------
            with st.spinner("1년치 시/군/구 방문객수 데이터를 불러오는 중입니다... (전국 데이터라 오래 걸릴 수 있어요)"):
                yearly_items = get_locgo_visitor_year(chart_year)

            if yearly_items:
                df = pd.DataFrame(yearly_items)
                sido_prefix = STANDARD_SIDO_CODE.get(selected_sido_name)
                # 1) 시/도 코드로 먼저 좁히고, 2) 시/군/구 이름이 정확히 같은 행만 남깁니다.
                if sido_prefix:
                    df = df[df["signguCode"].astype(str).str.startswith(sido_prefix)]
                mask = df["signguNm"] == selected_sigungu_name
                region_df = df[mask].copy()
                if region_df.empty:
                    # 이름 표기가 살짝 다를 수 있어(예: 공백 등) 부분일치로 한 번 더 시도합니다.
                    mask = df["signguNm"].astype(str).str.contains(selected_sigungu_name, na=False)
                    region_df = df[mask].copy()

        if region_df.empty:
            st.info("선택한 지역의 방문객수 데이터를 찾을 수 없습니다.")
        else:
            # 관광객수(touNum)는 숫자로, 기준연월일(baseYmd)의 월(月)로 계절을 구분합니다.
            region_df["touNum"] = pd.to_numeric(region_df["touNum"], errors="coerce")
            region_df["월"] = region_df["baseYmd"].astype(str).str[4:6].astype(int)
            region_df["계절"] = region_df["월"].map(MONTH_TO_SEASON)

            # 계절 x 관광객구분(현지인/외지인/외국인)별로 합산합니다.
            season_summary = region_df.groupby(["계절", "touDivNm"], as_index=False)["touNum"].sum()

            fig = px.bar(
                season_summary,
                x="계절",
                y="touNum",
                color="touDivNm",
                barmode="stack",
                category_orders={"계절": SEASON_ORDER},
                labels={"touNum": "방문객수(명)", "계절": "계절", "touDivNm": "관광객 구분"},
                title=f"{location_label} '25년 계절별 방문자수",
            )
            # 방문객수를 천단위 구분기호로, 소수점 없이 표시합니다.
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), yaxis_tickformat=",.0f")
            fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:,.0f}명<extra></extra>")
            st.plotly_chart(fig, use_container_width=True)

            # 아래 표는 계절 옆에 월 칸을 추가해서, 월별 합계까지 함께 보여줍니다.
            month_total = region_df.groupby(["계절", "월"], as_index=False)["touNum"].sum()

            # 겨울(12,1,2)처럼 숫자 순서가 아니라 계절이 흘러가는 순서로 정렬하기 위한 순번을 매깁니다.
            month_order_lookup = {
                (season, month): idx
                for idx, (season, month) in enumerate(
                    (season, month) for season in SEASON_ORDER for month in SEASON_MONTH_ORDER[season]
                )
            }
            month_total["정렬순서"] = month_total.apply(
                lambda row: month_order_lookup.get((row["계절"], row["월"]), 999), axis=1
            )
            month_total = month_total.sort_values("정렬순서")

            month_total["월"] = month_total["월"].astype(str) + "월"
            # 천단위 구분기호를 넣고 소수점은 표시하지 않습니다.
            month_total["총 방문객수(명)"] = month_total["touNum"].round(0).astype(int).map(lambda n: f"{n:,}")

            # st.dataframe은 같은 값이어도 셀을 하나로 합쳐(rowspan) 보여줄 수 없어서,
            # 계절이 바뀔 때만 "계절" 칸을 표시하고 나머지는 rowspan으로 이어붙이는 HTML 표를 직접 만듭니다.
            season_row_counts = month_total.groupby("계절", sort=False).size().to_dict()
            table_rows_html = []
            last_season_shown = None
            for _, row in month_total.iterrows():
                season = row["계절"]
                if season != last_season_shown:
                    rowspan = season_row_counts[season]
                    season_cell = (
                        f'<td rowspan="{rowspan}" '
                        f'style="text-align:center; vertical-align:middle; font-weight:600;">{season}</td>'
                    )
                    last_season_shown = season
                else:
                    season_cell = ""  # 이미 위 행에서 rowspan으로 합쳐졌으므로 셀을 생략합니다.

                table_rows_html.append(
                    "<tr>"
                    f"{season_cell}"
                    f'<td style="text-align:center;">{row["월"]}</td>'
                    f'<td style="text-align:right;">{row["총 방문객수(명)"]}</td>'
                    "</tr>"
                )

            season_table_html = f"""
            <style>
                .season-visitor-table {{ width:100%; border-collapse: collapse; font-size: 14px; }}
                .season-visitor-table th, .season-visitor-table td {{
                    border: 1px solid rgba(128,128,128,0.3);
                    padding: 6px 10px;
                }}
                .season-visitor-table th {{ background-color: rgba(128,128,128,0.15); }}
            </style>
            <table class="season-visitor-table">
                <thead>
                    <tr><th>계절</th><th>월</th><th>총 방문객수(명)</th></tr>
                </thead>
                <tbody>
                    {''.join(table_rows_html)}
                </tbody>
            </table>
            """
            st.markdown(season_table_html, unsafe_allow_html=True)


# ---------------------------------------------------------
# 7. 탭 구성
# ---------------------------------------------------------
tab_stay, tab_detail = st.tabs(
    ["🏨 숙박정보", "📋 공통·개요·반려동물 정보"]
)


# ===========================================================
# 탭 1) 숙박정보 (searchStay2)
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
# 탭 2) 공통정보 / 개요정보 / 반려동물 동반 여행정보
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
                        # detailCommon2는 contentId만으로 타입을 알아서 판별합니다.
                        # contentTypeId를 같이 보내면 "INVALID_REQUEST_PARAMETER_ERROR"가 나는 경우가 있어 뺐습니다.
                        # defaultYN=Y만으로도 주소(addr1/addr2)·좌표(mapx/mapy) 등 기본 정보가 함께 내려옵니다.
                        "defaultYN": "Y",   # 기본정보 포함
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

                # 이 콘텐츠의 좌표(mapx=경도, mapy=위도)가 있으면 작은 지도로도 표시합니다.
                if info.get("mapx") and info.get("mapy"):
                    try:
                        item_lon = float(info["mapx"])
                        item_lat = float(info["mapy"])
                        item_map_col, _ = st.columns([1, 3])  # 지도를 좁은 칸에 작게 표시
                        with item_map_col:
                            item_map_fig = px.scatter_mapbox(
                                pd.DataFrame({"lat": [item_lat], "lon": [item_lon], "지명": [info.get("title", "")]}),
                                lat="lat",
                                lon="lon",
                                hover_name="지명",
                                zoom=13,
                                height=200,
                            )
                            item_map_fig.update_traces(marker=dict(size=14, color="red"))
                            item_map_fig.update_layout(
                                mapbox_style="open-street-map",
                                margin=dict(l=0, r=0, t=0, b=0),
                            )
                            st.plotly_chart(item_map_fig, use_container_width=True, config={"scrollZoom": False})
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
# 8. 하단 안내
# ---------------------------------------------------------
st.markdown("---")
st.caption(
    "데이터 출처: 한국관광공사 TourAPI(KorService2), 관광 빅데이터 DataLabService · "
    "위치 좌표: OpenStreetMap Nominatim · "
    "본 대시보드는 공공데이터포털에서 발급받은 인증키(TOUR_API_KEY, TOURNUM_API_KEY)가 필요합니다."
)
