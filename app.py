
import streamlit as st
import requests
import pandas as pd
import re

from urllib.parse import quote
from supabase import create_client


# =====================================================
# 1. PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Movie Review",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/"

HEADERS = {
    "User-Agent": "MovieReviewApp/2.0 (educational project)"
}


# =====================================================
# 2. CUSTOM CSS
# =====================================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');

.stApp {
    background: #10141D;
    color: #F1F3F7;
    font-family: 'Be Vietnam Pro', sans-serif;
}

[data-testid="stSidebar"] {
    background: #171D29;
    border-right: 1px solid #293244;
}

[data-testid="stSidebar"] * {
    color: #E8EAF0;
}

h1, h2, h3 {
    color: #F4CA68 !important;
    font-weight: 700 !important;
}

p, label {
    color: #D3D8E2;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1250px;
}

.hero {
    background: linear-gradient(120deg, #202B40, #342C2C);
    border: 1px solid #46516A;
    padding: 30px;
    border-radius: 18px;
    margin-bottom: 25px;
}

.hero-title {
    font-size: 34px;
    font-weight: 800;
    color: #F4CA68;
}

.hero-subtitle {
    color: #D2D8E3;
    font-size: 15px;
    line-height: 1.8;
}

.section-title {
    font-size: 22px;
    font-weight: 700;
    color: #F4CA68;
    margin-top: 15px;
    margin-bottom: 15px;
}

div[data-testid="stMetric"] {
    background: #1C2432;
    border: 1px solid #303C51;
    border-radius: 14px;
    padding: 18px;
}

div[data-testid="stMetricLabel"] {
    color: #B7C1D2;
}

div[data-testid="stMetricValue"] {
    color: #F4CA68;
}

div.stButton > button {
    background: #E7BB60;
    color: #151923;
    border: none;
    border-radius: 9px;
    font-weight: 700;
    min-height: 42px;
}

div.stButton > button:hover {
    background: #F5D48D;
    color: #10141D;
}

div[data-testid="stForm"] {
    background: #1A2230;
    border: 1px solid #303C51;
    padding: 18px;
    border-radius: 14px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #303C51;
    border-radius: 13px;
    background: #171E2A;
}

.stTextInput input, .stTextArea textarea {
    background: #202A3A;
    color: white;
    border: 1px solid #39465D;
    border-radius: 8px;
}

.stSelectbox div[data-baseweb="select"] {
    background: #202A3A;
}

hr {
    border-color: #303C51;
}

a {
    color: #F4CA68 !important;
}

.footer {
    text-align: center;
    color: #8994A8;
    padding: 25px 0;
    line-height: 2;
}

@media (max-width: 768px) {
    .hero-title {
        font-size: 25px;
    }

    .hero {
        padding: 20px;
    }
}

</style>
""", unsafe_allow_html=True)


# =====================================================
# 3. SUPABASE CONNECTION
# =====================================================

@st.cache_resource
def get_supabase():

    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]

        if not url or not key:
            raise ValueError("Thiếu thông tin Supabase.")

        client = create_client(url, key)

        return client

    except Exception as e:

        st.error(
            "Không thể kết nối Supabase. "
            "Vui lòng kiểm tra Secrets trên Streamlit Cloud."
        )

        st.caption(str(e))
        st.stop()


supabase = get_supabase()


# =====================================================
# 4. WIKIDATA REQUEST
# =====================================================

def wikidata_request(params):

    response = requests.get(
        WD_API,
        params=params,
        headers=HEADERS,
        timeout=25
    )

    response.raise_for_status()

    return response.json()


# =====================================================
# 5. SEARCH MOVIES
# =====================================================

@st.cache_data(ttl=1800, show_spinner=False)
def search_movies(keyword):

    results = {}

    for language in ["vi", "en"]:

        params = {
            "action": "wbsearchentities",
            "search": keyword,
            "language": language,
            "uselang": language,
            "type": "item",
            "limit": 50,
            "format": "json"
        }

        data = wikidata_request(params)

        for item in data.get("search", []):

            qid = item.get("id")

            if not qid:
                continue

            if qid not in results:

                results[qid] = {
                    "id": qid,
                    "name": item.get("label", "Unknown"),
                    "description": item.get(
                        "description",
                        "Chưa có mô tả"
                    )
                }

    return list(results.values())


# =====================================================
# 6. GET MOVIE ENTITY
# =====================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_movie_entity(qid):

    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels|descriptions|claims",
        "languages": "vi|en",
        "format": "json"
    }

    data = wikidata_request(params)

    return data.get("entities", {}).get(qid, {})


# =====================================================
# 7. GET CLAIMS
# =====================================================

def get_claims(entity, property_id):

    claims = entity.get("claims", {})

    values = []

    for claim in claims.get(property_id, []):

        try:

            value = claim["mainsnak"]["datavalue"]["value"]

            values.append(value)

        except (KeyError, TypeError):
            continue

    return values


# =====================================================
# 8. GET ENTITY LABELS
# =====================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_entity_labels(entity_ids):

    entity_ids = list(dict.fromkeys(entity_ids))

    if not entity_ids:
        return {}

    labels = {}

    for start in range(0, len(entity_ids), 40):

        batch = entity_ids[start:start + 40]

        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "vi|en",
            "format": "json"
        }

        data = wikidata_request(params)

        for qid, item in data.get("entities", {}).items():

            item_labels = item.get("labels", {})

            labels[qid] = (
                item_labels.get("vi", {}).get("value")
                or item_labels.get("en", {}).get("value")
                or qid
            )

    return labels


def get_related_names(entity, property_id):

    values = get_claims(entity, property_id)

    ids = [
        value["id"]
        for value in values
        if isinstance(value, dict) and "id" in value
    ]

    labels = get_entity_labels(ids)

    return [
        labels.get(qid, qid)
        for qid in ids
    ]


# =====================================================
# 9. RELEASE YEAR
# =====================================================

def get_year(entity):

    dates = get_claims(entity, "P577")

    if not dates:
        return "Chưa cập nhật"

    value = dates[0].get("time", "")

    match = re.search(r"\+?(-?\d+)-", value)

    if match:

        year = int(match.group(1))

        if year < 0:
            return f"{abs(year)} TCN"

        return str(year)

    return "Chưa cập nhật"


# =====================================================
# 10. DURATION
# =====================================================

def get_duration(entity):

    values = get_claims(entity, "P2047")

    if not values:
        return "Chưa cập nhật"

    try:

        minutes = float(
            values[0]["amount"].replace("+", "")
        )

        return f"{minutes:g} phút"

    except (KeyError, ValueError, TypeError):
        return "Chưa cập nhật"


# =====================================================
# 11. POSTER FROM WIKIDATA
# =====================================================

def get_wikidata_poster(entity):

    images = get_claims(entity, "P18")

    if images:

        filename = images[0]

        return (
            COMMONS_FILE
            + quote(filename.replace(" ", "_"), safe="")
        )

    return None


# =====================================================
# 12. SEARCH POSTER FROM COMMONS
# =====================================================

@st.cache_data(ttl=3600, show_spinner=False)
def search_commons_poster(movie_name):

    searches = [
        f'"{movie_name}" film poster',
        f'"{movie_name}" movie poster'
    ]

    for search in searches:

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": search,
            "gsrnamespace": 6,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 600,
            "format": "json"
        }

        try:

            response = requests.get(
                COMMONS_API,
                params=params,
                headers=HEADERS,
                timeout=20
            )

            response.raise_for_status()

            pages = (
                response.json()
                .get("query", {})
                .get("pages", {})
            )

            for page in pages.values():

                title = page.get("title", "").lower()

                if "poster" not in title:
                    continue

                images = page.get("imageinfo", [])

                if images:

                    return (
                        images[0].get("thumburl")
                        or images[0].get("url")
                    )

        except requests.RequestException:
            continue

    return None


def get_poster(entity, movie_name):

    poster = get_wikidata_poster(entity)

    if poster:
        return poster, "Wikidata"

    poster = search_commons_poster(movie_name)

    if poster:
        return poster, "Wikimedia Commons"

    return None, None


# =====================================================
# 13. TRAILER AND IMDB
# =====================================================

def get_trailer(entity):

    videos = get_claims(entity, "P1651")

    if videos:

        return (
            "https://www.youtube.com/watch?v="
            + videos[0]
        )

    return None


def get_imdb(entity):

    values = get_claims(entity, "P345")

    if values:

        return (
            "https://www.imdb.com/title/"
            + values[0]
            + "/"
        )

    return None


# =====================================================
# 14. BUILD MOVIE
# =====================================================

def build_movie(qid, entity):

    labels = entity.get("labels", {})
    descriptions = entity.get("descriptions", {})

    name = (
        labels.get("vi", {}).get("value")
        or labels.get("en", {}).get("value")
        or qid
    )

    original_name = (
        labels.get("en", {}).get("value")
        or name
    )

    description = (
        descriptions.get("vi", {}).get("value")
        or descriptions.get("en", {}).get("value")
        or "Chưa có mô tả."
    )

    poster, image_source = get_poster(entity, name)

    return {
        "id": qid,
        "name": name,
        "original_name": original_name,
        "description": description,
        "year": get_year(entity),
        "duration": get_duration(entity),
        "poster": poster,
        "image_source": image_source,
        "directors": get_related_names(entity, "P57"),
        "actors": get_related_names(entity, "P161"),
        "genres": get_related_names(entity, "P136"),
        "countries": get_related_names(entity, "P495"),
        "companies": get_related_names(entity, "P272"),
        "trailer": get_trailer(entity),
        "imdb": get_imdb(entity),
        "wikidata_url": f"https://www.wikidata.org/wiki/{qid}"
    }


# =====================================================
# 15. SAVE REVIEW TO SUPABASE
# =====================================================

def save_review(movie_id, movie_name, reviewer, score, comment):

    data = {
        "movie_id": movie_id,
        "movie_name": movie_name,
        "reviewer": reviewer,
        "score": score,
        "comment": comment
    }

    response = (
        supabase
        .table("reviews")
        .insert(data)
        .execute()
    )

    return response.data


# =====================================================
# 16. LOAD REVIEWS FROM SUPABASE
# =====================================================

def load_reviews(movie_id=None):

    query = (
        supabase
        .table("reviews")
        .select("*")
    )

    if movie_id:

        query = query.eq(
            "movie_id",
            movie_id
        )

    response = (
        query
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )

    return pd.DataFrame(response.data or [])


# =====================================================
# 17. REVIEW DISPLAY
# =====================================================

def show_review(review):

    with st.container(border=True):

        col1, col2 = st.columns([3, 1])

        with col1:

            st.markdown(
                f"**👤 {review['reviewer']}**"
            )

        with col2:

            st.markdown(
                f"⭐ **{review['score']}/10**"
            )

        st.write(review["comment"])

        st.caption(
            str(review.get("created_at", ""))[:19]
        )


# =====================================================
# 18. SIDEBAR
# =====================================================

st.sidebar.markdown(
    "<h2 style='color:#F4CA68'>🎬 MOVIE REVIEW</h2>",
    unsafe_allow_html=True
)

st.sidebar.caption("CINEMA COMMUNITY")

st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "ĐIỀU HƯỚNG",
    [
        "🏠 Trang chủ",
        "🔍 Tìm kiếm phim",
        "⭐ Cộng đồng Review",
        "📊 Thống kê"
    ]
)

st.sidebar.markdown("---")

st.sidebar.markdown("""
<div style="color:#AAB5C8;font-size:13px;line-height:2">
🎥 Khám phá phim<br>
⭐ Chia sẻ cảm nhận<br>
💬 Kết nối cộng đồng
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

st.sidebar.caption(
    "Powered by Wikidata & Supabase"
)


# =====================================================
# 19. HOME PAGE
# =====================================================

if menu == "🏠 Trang chủ":

    st.markdown("""
    <div class="hero">
        <div class="hero-title">🎬 MOVIE REVIEW</div>
        <div class="hero-subtitle">
            Khám phá thế giới điện ảnh.<br>
            Tìm kiếm phim, chia sẻ cảm nhận và kết nối
            cùng cộng đồng yêu phim.
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:

        reviews = load_reviews()

        total = len(reviews)

        average = (
            reviews["score"].mean()
            if total else 0
        )

        movie_count = (
            reviews["movie_id"].nunique()
            if total else 0
        )

        c1, c2, c3 = st.columns(3)

        c1.metric("💬 Tổng lượt review", total)

        c2.metric("⭐ Điểm trung bình", f"{average:.1f}/10")

        c3.metric("🎬 Phim được review", movie_count)

        st.markdown(
            '<div class="section-title">✨ KHÁM PHÁ ĐIỆN ẢNH</div>',
            unsafe_allow_html=True
        )

        st.write(
            "Tìm kiếm bộ phim yêu thích và chia sẻ đánh giá "
            "của bạn với tất cả thành viên."
        )

        st.markdown("---")

        st.markdown(
            '<div class="section-title">💬 REVIEW MỚI NHẤT</div>',
            unsafe_allow_html=True
        )

        if not reviews.empty:

            for _, review in reviews.head(5).iterrows():

                show_review(review)

        else:

            st.info(
                "Chưa có đánh giá nào. "
                "Hãy là người đầu tiên review phim!"
            )

    except Exception as e:

        st.error(f"Không tải được dữ liệu: {e}")


# =====================================================
# 20. SEARCH PAGE
# =====================================================

elif menu == "🔍 Tìm kiếm phim":

    st.title("🔍 TÌM KIẾM PHIM")

    st.caption(
        "Tra cứu phim trực tuyến bằng Wikidata - Không cần API Key."
    )

    with st.form("movie_search_form"):

        keyword = st.text_input(
            "Tên phim",
            placeholder="Ví dụ: Avengers, Titanic, Doraemon..."
        )

        search_button = st.form_submit_button(
            "🔍 TÌM KIẾM",
            use_container_width=True
        )

    if search_button:

        if len(keyword.strip()) < 2:

            st.warning(
                "Vui lòng nhập ít nhất 2 ký tự."
            )

            st.session_state.search_results = []

        else:

            try:

                with st.spinner("Đang tìm kiếm phim..."):

                    results = search_movies(
                        keyword.strip()
                    )

                st.session_state.search_results = results
                st.session_state.search_keyword = keyword.strip()

                if results:

                    st.session_state.selected_movie_id = results[0]["id"]

            except requests.RequestException as e:

                st.error(
                    f"Lỗi kết nối Wikidata: {e}"
                )

    results = st.session_state.search_results

    if results:

        st.markdown("---")

        st.success(
            f"Tìm thấy {len(results)} kết quả."
        )

        ids = [item["id"] for item in results]

        default_index = (
            ids.index(st.session_state.selected_movie_id)
            if st.session_state.selected_movie_id in ids
            else 0
        )

        selected_id = st.selectbox(
            "Chọn bộ phim muốn xem",
            options=ids,
            index=default_index,
            format_func=lambda qid: next(
                (
                    f"{item['name']} ({qid})"
                    for item in results
                    if item["id"] == qid
                ),
                qid
            ),
            key="selected_movie_dropdown"
        )

        st.session_state.selected_movie_id = selected_id

        try:

            with st.spinner("Đang tải thông tin phim..."):

                entity = get_movie_entity(selected_id)

                movie = build_movie(
                    selected_id,
                    entity
                )

            st.markdown("---")

            st.markdown(
                f'<div class="section-title">{movie["name"]}</div>',
                unsafe_allow_html=True
            )

            st.caption(
                f"Tên gốc: {movie['original_name']}"
            )

            col1, col2 = st.columns([1, 2])

            with col1:

                if movie["poster"]:

                    st.image(
                        movie["poster"],
                        use_container_width=True
                    )

                    st.caption(
                        f"Nguồn ảnh: {movie['image_source']}"
                    )

                else:

                    st.info(
                        "Chưa tìm thấy poster."
                    )

            with col2:

                st.markdown("### 📌 THÔNG TIN PHIM")

                st.write(
                    f"**Năm phát hành:** {movie['year']}"
                )

                st.write(
                    f"**Thời lượng:** {movie['duration']}"
                )

                st.write(
                    "**Đạo diễn:** "
                    + (", ".join(movie["directors"]) or "Chưa cập nhật")
                )

                st.write(
                    "**Thể loại:** "
                    + (", ".join(movie["genres"]) or "Chưa cập nhật")
                )

                st.write(
                    "**Quốc gia:** "
                    + (", ".join(movie["countries"]) or "Chưa cập nhật")
                )

                st.write(
                    "**Hãng sản xuất:** "
                    + (", ".join(movie["companies"]) or "Chưa cập nhật")
                )

                st.markdown(
                    f"[🌐 Xem Wikidata]({movie['wikidata_url']})"
                )

                if movie["imdb"]:

                    st.markdown(
                        f"[⭐ Xem IMDb]({movie['imdb']})"
                    )

            st.markdown("---")

            st.markdown("### 📖 GIỚI THIỆU")

            st.write(movie["description"])

            st.markdown("---")

            st.markdown("### 🎭 DIỄN VIÊN")

            if movie["actors"]:

                actor_cols = st.columns(4)

                for i, actor in enumerate(movie["actors"][:20]):

                    with actor_cols[i % 4]:

                        st.write(f"🎭 {actor}")

            else:

                st.info(
                    "Chưa có thông tin diễn viên."
                )

            st.markdown("---")

            st.markdown("### ▶️ TRAILER")

            if movie["trailer"]:

                st.video(movie["trailer"])

            else:

                st.info(
                    "Chưa có trailer trong Wikidata."
                )

                trailer_url = (
                    "https://www.youtube.com/results?search_query="
                    + quote(movie["name"] + " official trailer")
                )

                st.markdown(
                    f"[🔎 Tìm trailer trên YouTube]({trailer_url})"
                )

            st.markdown("---")

            st.markdown("### ⭐ VIẾT ĐÁNH GIÁ")

            with st.form(f"review_form_{selected_id}"):

                reviewer = st.text_input(
                    "Tên người đánh giá",
                    placeholder="Nhập tên của bạn"
                )

                score = st.slider(
                    "Bạn đánh giá bộ phim bao nhiêu điểm?",
                    min_value=1,
                    max_value=10,
                    value=8
                )

                comment = st.text_area(
                    "Cảm nhận của bạn",
                    placeholder="Chia sẻ cảm nhận về nội dung, diễn xuất, hình ảnh...",
                    height=120
                )

                submit = st.form_submit_button(
                    "📩 GỬI ĐÁNH GIÁ",
                    use_container_width=True
                )

                if submit:

                    if not reviewer.strip() or not comment.strip():

                        st.warning(
                            "Vui lòng nhập tên và nội dung đánh giá."
                        )

                    elif len(reviewer.strip()) > 50 or len(comment.strip()) > 2000:

                        st.warning(
                            "Tên tối đa 50 ký tự và nhận xét tối đa 2.000 ký tự."
                        )

                    else:

                        try:

                            save_review(
                                movie["id"],
                                movie["name"],
                                reviewer.strip(),
                                score,
                                comment.strip()
                            )

                            st.success(
                                "Đánh giá đã được chia sẻ với cộng đồng!"
                            )

                            st.rerun()

                        except Exception as e:

                            st.error(
                                f"Không thể lưu đánh giá: {e}"
                            )

            st.markdown("---")

            st.markdown("### 💬 CỘNG ĐỒNG REVIEW")

            movie_reviews = load_reviews(selected_id)

            if not movie_reviews.empty:

                a, b = st.columns(2)

                a.metric(
                    "⭐ Điểm cộng đồng",
                    f"{movie_reviews['score'].mean():.1f}/10"
                )

                b.metric(
                    "💬 Lượt đánh giá",
                    len(movie_reviews)
                )

                for _, review in movie_reviews.iterrows():

                    show_review(review)

            else:

                st.info(
                    "Bộ phim này chưa có đánh giá nào."
                )

        except requests.RequestException as e:

            st.error(
                f"Không thể tải thông tin phim: {e}"
            )

        except Exception as e:

            st.error(
                f"Đã xảy ra lỗi: {e}"
            )


# =====================================================
# 21. COMMUNITY REVIEW
# =====================================================

elif menu == "⭐ Cộng đồng Review":

    st.title("💬 CỘNG ĐỒNG REVIEW")

    st.caption(
        "Tất cả đánh giá từ những người dùng Movie Review."
    )

    try:

        df = load_reviews()

        if not df.empty:

            c1, c2 = st.columns(2)

            c1.metric(
                "⭐ Điểm review cộng đồng",
                f"{df['score'].mean():.1f}/10"
            )

            c2.metric(
                "💬 Tổng lượt đánh giá",
                len(df)
            )

            st.markdown("---")

            selected_filter = st.selectbox(
                "Lọc đánh giá theo phim",
                ["Tất cả phim"] + sorted(
                    df["movie_name"].dropna().unique().tolist()
                )
            )

            if selected_filter != "Tất cả phim":

                df = df[
                    df["movie_name"] == selected_filter
                ]

            st.write(
                f"Hiển thị {len(df)} đánh giá."
            )

            for _, review in df.iterrows():

                show_review(review)

        else:

            st.info(
                "Chưa có đánh giá từ cộng đồng."
            )

    except Exception as e:

        st.error(
            f"Không thể tải review: {e}"
        )


# =====================================================
# 22. STATISTICS
# =====================================================

elif menu == "📊 Thống kê":

    st.title("📊 THỐNG KÊ CỘNG ĐỒNG")

    try:

        df = load_reviews()

        if not df.empty:

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "💬 Tổng review",
                len(df)
            )

            c2.metric(
                "⭐ Điểm trung bình",
                f"{df['score'].mean():.2f}/10"
            )

            c3.metric(
                "🎬 Số phim",
                df["movie_id"].nunique()
            )

            st.markdown("---")

            st.markdown("### ⭐ ĐIỂM REVIEW THEO PHIM")

            rating_chart = (
                df.groupby("movie_name")["score"]
                .mean()
                .sort_values(ascending=False)
            )

            st.bar_chart(rating_chart)

            st.markdown("---")

            st.markdown("### 📈 SỐ LƯỢT ĐÁNH GIÁ")

            count_chart = (
                df.groupby("movie_name")["score"]
                .count()
                .sort_values(ascending=False)
            )

            st.bar_chart(count_chart)

            st.markdown("---")

            st.markdown("### 📋 DỮ LIỆU REVIEW")

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            csv = df.to_csv(
                index=False
            ).encode("utf-8-sig")

            st.download_button(
                "📥 TẢI DỮ LIỆU CSV",
                data=csv,
                file_name="movie_reviews.csv",
                mime="text/csv"
            )

        else:

            st.info(
                "Chưa có dữ liệu để thống kê."
            )

    except Exception as e:

        st.error(
            f"Không thể tải thống kê: {e}"
        )


# =====================================================
# 23. FOOTER
# =====================================================

st.markdown("---")

st.markdown("""
<div class="footer">
    <div style="font-size:22px;color:#F4CA68;font-weight:700">
        🎬 MOVIE REVIEW
    </div>
    DISCOVER - WATCH - REVIEW<br>
    A COMMUNITY FOR MOVIE LOVERS<br>
    Powered by Wikidata & Supabase
</div>
""", unsafe_allow_html=True)
