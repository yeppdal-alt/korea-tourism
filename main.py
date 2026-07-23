# =========================================================
# 한국관광공사 위치기반 관광정보 대시보드 (main.py)
# -----------------------------------------------------------
# 이 앱은 한국관광공사 TourAPI(KorService2)를 이용해서
# 지역을 선택하면 아래 정보들을 조회해주는 스트림릿 대시보드입니다.
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
# 2. 지역 코드 / 콘텐츠 타입 코드 (TourAPI 공식 코드표)
# ---------------------------------------------------------
# 지역코드조회(areaCode2)는 공식 문서상 "미사용 예정" 기능이라
# 자주 바뀌지 않는 표준 시도 코드를 앱 안에 직접 정리해두었습니다.
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


# ---------------------------------------------------------
# 3. API 호출 공통 함수
# ---------------------------------------------------------
def call_tour_api(operation: str, extra_params: dict) -> list:
    """
    TourAPI(KorService2)의 특정 기능(operation)을 호출하고
    결과 아이템 리스트를 돌려주는 공통 함수입니다.

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
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()  # HTTP 오류가 있으면 예외 발생
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


# ---------------------------------------------------------
# 4. 화면 구성 - 사이드바 (지역 선택)
# ---------------------------------------------------------
st.title("🗺️ 한국관광공사 위치기반 관광정보 대시보드")
st.caption("지역을 선택하고 원하는 정보 탭을 눌러 관광 정보를 조회하세요.")

with st.sidebar:
    st.header("🔎 검색 조건")

    selected_area_name = st.selectbox("지역을 선택하세요", list(AREA_CODES.keys()))
    selected_area_code = AREA_CODES[selected_area_name]

    st.markdown("---")
    st.caption(
        "※ 공통정보 / 개요정보 / 반려동물 동반 정보는 "
        "콘텐츠ID(contentId)가 필요합니다. "
        "아래 탭에서 목록을 먼저 검색한 뒤 항목을 선택하면 자동으로 조회됩니다."
    )

    if not TOUR_API_KEY:
        st.error("⚠️ TOUR_API_KEY 시크릿이 설정되지 않았습니다.")


# ---------------------------------------------------------
# 5. 탭 구성
# ---------------------------------------------------------
tab_festival, tab_stay, tab_detail = st.tabs(
    ["🎉 행사정보", "🏨 숙박정보", "📋 공통·개요·반려동물 정보"]
)


# ===========================================================
# 탭 1) 행사정보 (searchFestival2)
# ===========================================================
with tab_festival:
    st.subheader(f"'{selected_area_name}' 지역의 행사정보")

    # 행사 시작일 기본값: 오늘 날짜
    event_start_date = st.date_input("행사 시작일(이후) 검색 기준", value=pd.Timestamp.today())
    event_start_str = event_start_date.strftime("%Y%m%d")

    if st.button("행사정보 조회", key="btn_festival"):
        with st.spinner("행사정보를 불러오는 중입니다..."):
            festival_items = call_tour_api(
                "searchFestival2",
                {
                    "areaCode": selected_area_code,
                    "eventStartDate": event_start_str,
                    "arrange": "A",  # A: 제목순 정렬
                },
            )

        if festival_items:
            df = pd.DataFrame(festival_items)
            # 화면에 보여줄 주요 컬럼만 정리 (없는 컬럼은 자동으로 무시)
            show_cols = [c for c in ["title", "eventstartdate", "eventenddate", "addr1", "tel"] if c in df.columns]
            st.dataframe(df[show_cols], use_container_width=True)
        else:
            st.info("조회된 행사정보가 없습니다.")


# ===========================================================
# 탭 2) 숙박정보 (searchStay2)
# ===========================================================
with tab_stay:
    st.subheader(f"'{selected_area_name}' 지역의 숙박정보")

    if st.button("숙박정보 조회", key="btn_stay"):
        with st.spinner("숙박정보를 불러오는 중입니다..."):
            stay_items = call_tour_api(
                "searchStay2",
                {
                    "areaCode": selected_area_code,
                    "arrange": "A",  # A: 제목순 정렬
                },
            )

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
    st.subheader(f"'{selected_area_name}' 지역의 관광정보 상세 조회")
    st.caption("먼저 콘텐츠 타입을 선택해 목록을 검색하고, 아래에서 항목을 선택하세요.")

    selected_content_name = st.selectbox("콘텐츠 타입을 선택하세요", list(CONTENT_TYPES.keys()))
    selected_content_type = CONTENT_TYPES[selected_content_name]

    if st.button("목록 조회", key="btn_area_list"):
        with st.spinner("목록을 불러오는 중입니다..."):
            # 지역기반 관광정보조회(areaBasedList2)로 콘텐츠 목록을 가져옵니다.
            area_items = call_tour_api(
                "areaBasedList2",
                {
                    "areaCode": selected_area_code,
                    "contentTypeId": selected_content_type,
                    "arrange": "A",
                },
            )
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
# 6. 하단 안내
# ---------------------------------------------------------
st.markdown("---")
st.caption(
    "데이터 출처: 한국관광공사 TourAPI(KorService2) · "
    "본 대시보드는 공공데이터포털에서 발급받은 인증키가 필요합니다."
)
