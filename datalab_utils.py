# =========================================================
# datalab_utils.py
# -----------------------------------------------------------
# 여러 페이지(main.py, pages/ 안의 파일들)에서 공통으로 쓰는
# 설정값과 함수들을 모아둔 파일입니다.
#
# - HTTP 요청 재시도 함수(request_with_retry)
# - 한국관광공사 관광 빅데이터 DataLabService 관련 상수/함수
#   (방문자수 데이터를 가져오는 fetch_datalab_items, get_locgo_visitor_year)
#
# 이렇게 따로 빼두면 main.py와 새로 만든 페이지들이
# 같은 코드를 복사/붙여넣기 하지 않고 함께 불러 쓸 수 있고,
# 캐시(st.cache_data)도 페이지끼리 공유되어 API를 중복 호출하지 않습니다.
# =========================================================

import time

import streamlit as st
import requests

# ---------------------------------------------------------
# 인증키 / 엔드포인트
# ---------------------------------------------------------
# 관광 빅데이터(방문자수) DataLabService의 기본 주소(엔드포인트)
BASE_URL_DATALAB = "https://apis.data.go.kr/B551011/DataLabService"

# 인증키는 코드에 직접 쓰지 않고 st.secrets 에서 불러옵니다.
try:
    TOURNUM_API_KEY = st.secrets["TOURNUM_API_KEY"]
except Exception:
    TOURNUM_API_KEY = None


# ---------------------------------------------------------
# 지역 코드 표
# ---------------------------------------------------------
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

# STANDARD_SIDO_CODE를 거꾸로 뒤집어서, signguCode 앞 2자리로 시/도 이름을 찾을 때 씁니다.
# (예: "11" -> "서울") 여러 페이지에서 지역 표시용 라벨을 만들 때 사용합니다.
SIDO_CODE_TO_NAME = {code: name for name, code in STANDARD_SIDO_CODE.items()}

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
# 공통 HTTP 요청 함수
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


# ---------------------------------------------------------
# DataLabService(방문자수) 관련 함수
# ---------------------------------------------------------
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
def get_locgo_visitor_year(year: int):
    """
    기초 지자체(시/군/구) 단위 방문자수 데이터를 특정 연도 1년치 통째로 가져옵니다.
    전국 모든 시/군/구 데이터를 하루 단위로 담고 있어 데이터 양이 매우 많으므로,
    한 페이지에 최대한 많이 받아오고(page_size) 페이지 수 제한도 넉넉히 잡습니다.
    같은 연도는 하루 동안 캐시해서 반복 호출을 막습니다.
    (main.py와 pages/ 안의 페이지들이 이 함수를 함께 불러 쓰므로,
    한 번 불러온 데이터는 다른 페이지에서도 캐시를 그대로 재사용합니다)
    """
    start_ymd = f"{year}0101"
    end_ymd = f"{year}1231"
    return fetch_datalab_items("locgoRegnVisitrDDList", start_ymd, end_ymd, page_size=5000, max_pages=150)
