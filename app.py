
import streamlit as st
import requests
import pandas as pd
import re
import html

from urllib.parse import quote
from datetime import datetime, timezone

# =====================================================
# 1. PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Movie Review | Cinema Community",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/"

HEADERS = {
    "User-Agent": "MovieReviewCommunity/3.0 (educational Streamlit project)",
    "Accept": "application/json"
}

REVIEW_COLUMNS = [
    "id", "movie_id", "movie_name", "reviewer",
    "score", "comment", "created_at"
]

# =====================================================
# 2. CSS - CINEMA DESIGN
# =====================================================

st.markdown("""
<style>
.stApp {
    background: #10141D;
    color: #F1F3F7;
}

.block-container {
    max-width: 1200px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

[data-testid="stSidebar"] {
    background: #171D29;
    border-right: 1px solid #303B50;
}

h1, h2, h3 {
    color: #F4CA68 !important;
}

.hero {
    background: linear-gradient(120deg, #202B40, #38302B);
    border: 1px solid #48516A;
    padding: 30px;
    border-radius: 18px;
    margin-bottom: 24px;
}

.hero-title {
    color: #F4CA68;
    font-size: 34px;
    font-weight: 800;
}

.hero-subtitle {
    color: #D5DCE8;
    font-size: 15px;
    line-height: 1.8;
}

.section-title {
    color: #F4CA68;
    font-size: 22px;
    font-weight: 700;
    margin: 20px 0 15px;
}

div[data-testid="stMetric"] {
    background: #1C2432;
    border: 1px solid #303C51;
    border-radius: 14px;
    padding: 16px;
}

div[data-testid="stMetricValue"] {
    color: #F4CA68;
}

div.stButton > button,
div.stFormSubmitButton > button {
    background: #E7BB60;
    color: #151923;
    border: none;
    border-radius: 9px;
    font-weight: 700;
    min-height: 42px;
}

div.stButton > button:hover,
div.stFormSubmitButton > button:hover {
    background: #F5D48D;
    color: #10141D;
}

div[data-testid="stForm"] {
    background: #1A2230;
    border: 1px solid #303C51;
    border-radius: 14px;
    padding: 18px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #303C51;
    border-radius: 14px;
}

a {
    color: #F4CA68 !important;
}

.footer {
    text-align: center;
    color: #9BA7BA;
    padding: 25px 0;
    line-height: 2;
}

@media (max-width: 768px) {
    .hero {
        padding: 20px;
    }
    .hero-title {
        font-size: 25px;
    }
    .block-container {
        padding-top: 1rem;
    }
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# 3. SUPABASE REST API
# =====================================================

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

except (KeyError, FileNotFoundError):
    st.error(
        "Chưa cấu hình Supabase. "
        "Hãy thêm SUPABASE_URL và SUPABASE_KEY "
        "vào Streamlit Secrets."
    )
    st.stop()

SUPABASE_TABLE_URL = (
    f"{SUPABASE_URL}/rest/v1/reviews"
)


def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


def test_supabase_connection():
    response = requests.get(
        SUPABASE_TABLE_URL,
        headers=supabase_headers(),
        params={"select": "id", "limit": 1},
        timeout=20
    )
    response.raise_for_status()
    return True


def save_review(
    movie_id,
    movie_name,
    reviewer,
    score,
    comment
):
    payload = {
        "movie_id": movie_id,
        "movie_name": movie_name,
        "reviewer": reviewer,
        "score": int(score),
        "comment": comment
    }

    response = requests.post(
        SUPABASE_TABLE_URL,
        headers={
            **supabase_headers(),
            "Prefer": "return=minimal"
        },
        json=payload,
        timeout=20
    )

    response.raise_for_status()
    return True


def load_reviews(movie_id=None, limit=1000):
    all_rows = []
    offset = 0
    page_size = 1000

    while len(all_rows) < limit:
        take = min(page_size, limit - len(all_rows))

        params = {
            "select": "*",
            "order": "created_at.desc,id.desc",
            "limit": take,
            "offset": offset
        }

        if movie_id:
            params["movie_id"] = f"eq.{movie_id}"

        response = requests.get(
            SUPABASE_TABLE_URL,
            headers=supabase_headers(),
            params=params,
            timeout=25
        )

        response.raise_for_status()
        rows = response.json()
        all_rows.extend(rows)

        if len(rows) < take:
            break

        offset += len(rows)

    df = pd.DataFrame(all_rows)

    if df.empty:
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    for column in REVIEW_COLUMNS:
        if column not in df.columns:
            df[column] = None

    df["score"] = pd.to_numeric(
        df["score"], errors="coerce"
    )

    return df


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
                    "name": item.get("label", qid),
                    "description": item.get(
                        "description", ""
                    )
                }

    return list(results.values())


# =====================================================
# 5. MOVIE DETAILS
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


def get_claims(entity, property_id):
    values = []

    for claim in entity.get(
        "claims", {}
    ).get(property_id, []):
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            values.append(value)
        except (KeyError, TypeError):
            continue

    return values


@st.cache_data(ttl=3600, show_spinner=False)
def get_entity_labels(entity_ids):
    labels = {}
    entity_ids = list(dict.fromkeys(entity_ids))

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
            names = item.get("labels", {})
            labels[qid] = (
                names.get("vi", {}).get("value")
                or names.get("en", {}).get("value")
                or qid
            )

    return labels


def get_related_names(entity, property_id):
    ids = [
        value["id"]
        for value in get_claims(entity, property_id)
        if isinstance(value, dict) and "id" in value
    ]

    labels = get_entity_labels(ids)
    return [labels.get(qid, qid) for qid in ids]


def get_year(entity):
    dates = get_claims(entity, "P577")

    if not dates:
        return "Chưa cập nhật"

    value = dates[0].get("time", "")
    match = re.search(r"\+?(-?\d+)-", value)

    if match:
        year = int(match.group(1))
        return (
            f"{abs(year)} TCN"
            if year < 0 else str(year)
        )

    return "Chưa cập nhật"


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
# 6. POSTER
# =====================================================

def get_wikidata_poster(entity):
    images = get_claims(entity, "P18")

    if images and isinstance(images[0], str):
        return (
            COMMONS_FILE
            + quote(images[0].replace(" ", "_"), safe="")
        )

    return None


@st.cache_data(ttl=3600, show_spinner=False)
def search_commons_poster(movie_name):
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'"{movie_name}" film poster',
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
        pass

    return None


def get_poster(entity, movie_name):
    poster = get_wikidata_poster(entity)

    if poster:
        return poster, "Wikidata"

    poster = search_commons_poster(movie_name)

    if poster:
        return poster, "Wikimedia Commons"

    return None, None


def get_trailer(entity):
    videos = get_claims(entity, "P1651")

    if videos and isinstance(videos[0], str):
        return (
            "https://www.youtube.com/watch?v="
            + videos[0]
        )

    return None


def get_imdb(entity):
    values = get_claims(entity, "P345")

    if values and isinstance(values[0], str):
        return (
            "https://www.imdb.com/title/"
            + values[0]
            + "/"
        )

    return None


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

    poster, image_source = get_poster(
        entity, name
    )

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
# 7. UI HELPERS
# =====================================================

def safe_text(value):
    return html.escape(str(value))


def show_review(review, show_movie=True):
    with st.container(border=True):
        if show_movie:
            st.markdown(
                f"🎬 **{safe_text(review.get('movie_name', 'Phim'))}**"
            )

        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(
                f"👤 **{safe_text(review.get('reviewer', 'Ẩn danh'))}**"
            )

        with col2:
            st.markdown(
                f"⭐ **{review.get('score', 0):g}/10**"
            )

        st.write(review.get("comment", ""))

        created = str(review.get("created_at", ""))

        if created:
            st.caption(f"🕒 {created[:19].replace('T', ' ')}")


def movie_stats(df):
    if df.empty:
        return 0, 0.0, 0

    return (
        len(df),
        float(df["score"].mean()),
        df["movie_id"].nunique()
    )


def section_title(text):
    st.markdown(
        f'<div class="section-title">{safe_text(text)}</div>',
        unsafe_allow_html=True
    )


# =====================================================
# 8. SESSION STATE
# =====================================================

if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "selected_movie_id" not in st.session_state:
    st.session_state.selected_movie_id = None

if "current_page" not in st.session_state:
    st.session_state.current_page = "🏠 Trang chủ"


# =====================================================
# 9. SIDEBAR
# =====================================================

st.sidebar.title("🎬 MOVIE REVIEW")
st.sidebar.caption("CINEMA COMMUNITY")
st.sidebar.divider()

pages = [
    "🏠 Trang chủ",
    "🔍 Tìm kiếm phim",
    "⭐ Cộng đồng Review",
    "📊 Thống kê"
]

menu = st.sidebar.radio(
    "ĐIỀU HƯỚNG",
    pages,
    key="current_page"
)

st.sidebar.divider()

st.sidebar.write("🎥 Khám phá phim")
st.sidebar.write("⭐ Chia sẻ cảm nhận")
st.sidebar.write("💬 Kết nối cộng đồng")

st.sidebar.divider()

try:
    test_supabase_connection()
    st.sidebar.success("🟢 Database đã kết nối")
except requests.RequestException:
    st.sidebar.error("🔴 Lỗi kết nối Database")
    st.error(
        "Không thể kết nối Supabase. "
        "Kiểm tra URL, Publishable/anon Key, "
        "bảng reviews và chính sách RLS."
    )
    st.stop()


# =====================================================
# 10. HOME PAGE
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
        total, average, movie_count = movie_stats(reviews)

        c1, c2, c3 = st.columns(3)

        c1.metric("💬 Tổng review", total)
        c2.metric("⭐ Điểm trung bình", f"{average:.1f}/10")
        c3.metric("🎬 Phim được review", movie_count)

        st.divider()
        section_title("✨ KHÁM PHÁ ĐIỆN ẢNH")

        st.write(
            "Tìm kiếm bộ phim yêu thích và chia sẻ "
            "đánh giá với cộng đồng."
        )

        if st.button(
            "🔍 TÌM KIẾM PHIM",
            use_container_width=True
        ):
            st.session_state.current_page = "🔍 Tìm kiếm phim"
            st.rerun()

        st.divider()
        section_title("💬 REVIEW MỚI NHẤT")

        if reviews.empty:
            st.info("Chưa có đánh giá nào.")
        else:
            for _, review in reviews.head(5).iterrows():
                show_review(review)

    except requests.RequestException as e:
        st.error(f"Lỗi tải dữ liệu: {e}")


# =====================================================
# 11. SEARCH PAGE
# =====================================================

elif menu == "🔍 Tìm kiếm phim":
    st.title("🔍 TÌM KIẾM PHIM")
    st.caption(
        "Tra cứu phim bằng Wikidata - Không cần API Key tìm phim."
    )

    with st.form("search_form"):
        keyword = st.text_input(
            "Nhập tên phim",
            placeholder="Titanic, Avengers, Doraemon..."
        )

        submitted = st.form_submit_button(
            "🔍 TÌM KIẾM",
            use_container_width=True
        )

    if submitted:
        if len(keyword.strip()) < 2:
            st.warning("Vui lòng nhập ít nhất 2 ký tự.")
            st.session_state.search_results = []
        else:
            try:
                with st.spinner("Đang tìm kiếm..."):
                    results = search_movies(keyword.strip())

                st.session_state.search_results = results
                st.session_state.selected_movie_id = (
                    results[0]["id"] if results else None
                )

            except requests.RequestException as e:
                st.error(f"Lỗi tìm kiếm: {e}")

    results = st.session_state.search_results

    if results:
        st.success(f"Tìm thấy {len(results)} kết quả.")

        ids = [item["id"] for item in results]

        selected_id = st.selectbox(
            "Chọn phim",
            options=ids,
            format_func=lambda qid: next(
                (
                    f"{item['name']} - {item['description']} ({qid})"
                    for item in results
                    if item["id"] == qid
                ),
                qid
            )
        )

        try:
            with st.spinner("Đang tải thông tin phim..."):
                entity = get_movie_entity(selected_id)
                movie = build_movie(selected_id, entity)

            st.divider()
            st.title(movie["name"])
            st.caption(f"Tên gốc: {movie['original_name']}")

            col1, col2 = st.columns([1, 2])

            with col1:
                if movie["poster"]:
                    try:
                        st.image(
                            movie["poster"],
                            use_container_width=True
                        )
                        st.caption(
                            f"Nguồn ảnh: {movie['image_source']}"
                        )
                    except Exception:
                        st.info("Không tải được poster.")
                else:
                    st.info("Chưa có poster phù hợp.")

            with col2:
                st.subheader("📌 THÔNG TIN PHIM")

                st.write(f"**Năm:** {movie['year']}")
                st.write(f"**Thời lượng:** {movie['duration']}")

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
                    f"[🌐 Wikidata]({movie['wikidata_url']})"
                )

                if movie["imdb"]:
                    st.markdown(
                        f"[⭐ IMDb]({movie['imdb']})"
                    )

            st.divider()
            st.subheader("📖 GIỚI THIỆU")
            st.write(movie["description"])

            st.divider()
            st.subheader("🎭 DIỄN VIÊN")

            if movie["actors"]:
                for actor in movie["actors"][:20]:
                    st.write(f"🎭 {actor}")
            else:
                st.info("Chưa có thông tin diễn viên.")

            st.divider()
            st.subheader("▶️ TRAILER")

            if movie["trailer"]:
                st.video(movie["trailer"])
            else:
                trailer_url = (
                    "https://www.youtube.com/results?search_query="
                    + quote(movie["name"] + " official trailer")
                )
                st.link_button(
                    "🔎 Tìm trailer trên YouTube",
                    trailer_url
                )

            st.divider()
            st.subheader("⭐ VIẾT ĐÁNH GIÁ")

            with st.form(f"review_form_{selected_id}"):
                reviewer = st.text_input(
                    "Tên của bạn",
                    max_chars=50
                )

                score = st.slider(
                    "Điểm đánh giá",
                    1, 10, 8
                )

                comment = st.text_area(
                    "Cảm nhận của bạn",
                    max_chars=2000,
                    height=120
                )

                submit_review = st.form_submit_button(
                    "📩 GỬI ĐÁNH GIÁ",
                    use_container_width=True
                )

                if submit_review:
                    if not reviewer.strip() or not comment.strip():
                        st.warning(
                            "Vui lòng nhập tên và nhận xét."
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
                            st.success("Đã gửi review thành công!")
                            st.rerun()

                        except requests.RequestException as e:
                            st.error(f"Lỗi lưu review: {e}")

            st.divider()
            st.subheader("💬 CỘNG ĐỒNG REVIEW")

            movie_reviews = load_reviews(selected_id)

            if not movie_reviews.empty:
                a, b = st.columns(2)

                a.metric(
                    "⭐ Điểm cộng đồng",
                    f"{movie_reviews['score'].mean():.1f}/10"
                )

                b.metric(
                    "💬 Lượt review",
                    len(movie_reviews)
                )

                for _, review in movie_reviews.iterrows():
                    show_review(review, show_movie=False)
            else:
                st.info("Chưa có đánh giá cho phim này.")

        except requests.RequestException as e:
            st.error(f"Không thể tải dữ liệu: {e}")

    elif submitted:
        st.warning("Không tìm thấy kết quả phù hợp.")


# =====================================================
# 12. COMMUNITY PAGE
# =====================================================

elif menu == "⭐ Cộng đồng Review":
    st.title("💬 CỘNG ĐỒNG REVIEW")

    if st.button("🔄 Làm mới đánh giá"):
        st.rerun()

    try:
        df = load_reviews()

        if df.empty:
            st.info("Chưa có review nào.")
        else:
            c1, c2 = st.columns(2)

            c1.metric(
                "⭐ Điểm cộng đồng",
                f"{df['score'].mean():.1f}/10"
            )

            c2.metric(
                "💬 Tổng lượt đánh giá",
                len(df)
            )

            st.divider()

            movie_options = (
                df[["movie_id", "movie_name"]]
                .drop_duplicates("movie_id")
            )

            option_ids = ["all"] + movie_options["movie_id"].tolist()

            movie_lookup = dict(zip(
                movie_options["movie_id"],
                movie_options["movie_name"]
            ))

            selected = st.selectbox(
                "Lọc theo phim",
                option_ids,
                format_func=lambda x: (
                    "Tất cả phim"
                    if x == "all"
                    else movie_lookup.get(x, x)
                )
            )

            if selected != "all":
                df = df[df["movie_id"] == selected]

            st.write(f"Hiển thị {len(df)} đánh giá.")

            for _, review in df.iterrows():
                show_review(review)

    except requests.RequestException as e:
        st.error(f"Lỗi tải review: {e}")


# =====================================================
# 13. STATISTICS PAGE
# =====================================================

elif menu == "📊 Thống kê":
    st.title("📊 THỐNG KÊ CỘNG ĐỒNG")

    if st.button("🔄 Cập nhật thống kê"):
        st.rerun()

    try:
        df = load_reviews()

        if df.empty:
            st.info("Chưa có dữ liệu thống kê.")
        else:
            total, average, movie_count = movie_stats(df)

            c1, c2, c3 = st.columns(3)

            c1.metric("💬 Tổng review", total)
            c2.metric("⭐ Điểm TB", f"{average:.2f}/10")
            c3.metric("🎬 Số phim", movie_count)

            st.divider()
            st.subheader("🏆 BẢNG XẾP HẠNG PHIM")

            ranking = (
                df.groupby(["movie_id", "movie_name"])
                .agg(
                    diem_trung_binh=("score", "mean"),
                    so_luot=("score", "count")
                )
                .reset_index()
                .sort_values(
                    ["diem_trung_binh", "so_luot"],
                    ascending=[False, False]
                )
            )

            st.dataframe(
                ranking.rename(columns={
                    "movie_name": "Tên phim",
                    "diem_trung_binh": "Điểm trung bình",
                    "so_luot": "Lượt đánh giá"
                })[
                    ["Tên phim", "Điểm trung bình", "Lượt đánh giá"]
                ],
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("⭐ ĐIỂM REVIEW THEO PHIM")

            st.bar_chart(
                ranking.set_index("movie_name")[
                    "diem_trung_binh"
                ]
            )

            st.divider()
            st.subheader("📈 SỐ LƯỢT ĐÁNH GIÁ")

            st.bar_chart(
                ranking.set_index("movie_name")[
                    "so_luot"
                ]
            )

            st.divider()
            st.subheader("📋 DỮ LIỆU ĐÁNH GIÁ")

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "📥 TẢI CSV",
                data=df.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="movie_reviews.csv",
                mime="text/csv"
            )

    except requests.RequestException as e:
        st.error(f"Lỗi thống kê: {e}")


# =====================================================
# 14. FOOTER
# =====================================================

st.divider()

st.markdown("""
<div class="footer">
    <div style="font-size:22px;color:#F4CA68;font-weight:700">
        🎬 MOVIE REVIEW
    </div>
    DISCOVER - WATCH - REVIEW<br>
    A COMMUNITY FOR MOVIE LOVERS<br>
    Powered by Wikidata & Supabase REST API
</div>
""", unsafe_allow_html=True)
