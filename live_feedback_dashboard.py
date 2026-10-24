"""
☕ Sunrise Café – Live Customer Feedback Dashboard (single-file Streamlit app)
============================================================================
Business venture: "Sunrise Café", a neighbourhood café & bakery.

* Customers submit feedback in the "Give Feedback" tab (any phone / laptop that opens the app).
* Every response is saved to a shared CSV file (no database server needed).
* The dashboard re-reads that file every 3 seconds, so charts update LIVE for everyone.

Run
    pip install streamlit pandas
    streamlit run live_feedback_dashboard.py
Tip: to collect feedback from other phones on the same Wi-Fi, open the "Network URL"
that Streamlit prints in the terminal on each phone.
"""
import csv
import random
import re
import tempfile
import threading
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

BUSINESS = "Sunrise Café"
PRODUCTS = ["Espresso", "Cappuccino", "Croissant", "Sourdough Loaf", "Blueberry Muffin", "Club Sandwich"]
VISITS = ["Dine-in", "Takeaway", "Delivery"]
CATS = ["taste", "service", "cleanliness", "value"]
COLS = ["time", "product", "visit", *CATS, "overall", "nps", "comment"]
POS = {"great", "amazing", "delicious", "friendly", "fresh", "love", "loved", "perfect", "best", "tasty", "lovely",
       "excellent", "cozy", "quick", "fast", "good", "wonderful", "clean", "warm", "yummy"}
NEG = {"cold", "slow", "rude", "dirty", "expensive", "stale", "bland", "bad", "awful", "worst", "noisy", "wait",
       "waited", "overpriced", "burnt", "soggy", "late", "wrong", "disappointing", "terrible"}
STOP = set("the a an and or but is was were are it its i we my our to of in on for with at this that very so too "
           "have had has be been as they them you your me us just really not no".split())


# ------------------------------ shared storage (CSV, no DB server) ------------------------------
class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.path = Path(__file__).with_name("feedback_data.csv")
        try:
            self._init()
        except OSError:                                   # read-only folder (some cloud hosts)
            self.path = Path(tempfile.gettempdir()) / "feedback_data.csv"
            self._init()

    def _init(self):
        if not self.path.exists():
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(COLS)

    def add(self, rows):
        with self.lock, open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([[r[c] for c in COLS] for r in rows])

    def read(self):
        with self.lock:
            df = pd.read_csv(self.path)
        df["time"] = pd.to_datetime(df["time"])
        df["comment"] = df["comment"].fillna("").astype(str)
        return df

    def clear(self):
        with self.lock:
            self.path.unlink(missing_ok=True)
            self._init()


@st.cache_resource
def get_store():
    return Store()


def make_row(product, visit, taste, service, cleanliness, value, nps, comment, when=None):
    return {"time": (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), "product": product, "visit": visit,
            "taste": taste, "service": service, "cleanliness": cleanliness, "value": value,
            "overall": round((taste + service + cleanliness + value) / 4, 2), "nps": nps,
            "comment": re.sub(r"\s+", " ", comment).strip()}


# ------------------------------ demo data generator ------------------------------
GOOD = ["Amazing {p}, so fresh and tasty!", "Friendly staff and quick service, loved the {p}.", "Cozy place, the {p} was perfect.",
        "Best {p} in town, great value too.", "Lovely atmosphere and delicious {p}."]
BAD = ["The {p} was cold and the service was slow.", "Too expensive for such a bland {p}.", "Waited a long time and the table was dirty.",
       "Disappointing, the {p} was stale.", "Rude staff and noisy place."]
MID = ["The {p} was okay, nothing special.", "Decent {p} but a bit of a wait.", "Good coffee, average service."]
QUALITY = {"Espresso": 4.4, "Cappuccino": 4.2, "Croissant": 4.5, "Sourdough Loaf": 3.9, "Blueberry Muffin": 3.2, "Club Sandwich": 3.5}


def sample_rows(n=70):
    now, rows = datetime.now(), []
    for _ in range(n):
        p = random.choice(PRODUCTS)
        base = QUALITY[p] + random.uniform(-1.3, .8)
        r = lambda off=0: max(1, min(5, round(base + off + random.uniform(-.7, .7))))
        t, s, c, v = r(), r(.1), r(.3), r(-.4 if p in ("Club Sandwich", "Blueberry Muffin") else 0)
        avg = (t + s + c + v) / 4
        txt = random.choice(GOOD if avg >= 4 else BAD if avg < 3 else MID).format(p=p.lower())
        nps = max(0, min(10, round(avg * 2 + random.uniform(-1.5, 1))))
        rows.append(make_row(p, random.choice(VISITS), t, s, c, v, nps, txt, now - timedelta(minutes=random.randint(1, 60 * 24 * 7))))
    return sorted(rows, key=lambda x: x["time"])


# ------------------------------ analytics (pure functions) ------------------------------
def sentiment(text):
    w = re.findall(r"[a-z']+", text.lower())
    s = sum(x in POS for x in w) - sum(x in NEG for x in w)
    return "Positive" if s > 0 else "Negative" if s < 0 else "Neutral"


def keywords(df, n=10):
    words = [w for t in df["comment"] for w in re.findall(r"[a-z']{3,}", t.lower()) if w not in STOP]
    return pd.Series(dict(Counter(words).most_common(n)), dtype=int)


def nps_score(s):
    return 0 if len(s) == 0 else round(100 * ((s >= 9).mean() - (s <= 6).mean()))


def insights(df):
    if df.empty:
        return []
    by = df.groupby("product")["overall"].agg(["mean", "size"])
    by = by[by["size"] >= 3] if (by["size"] >= 3).any() else by
    cat = df[CATS].mean()
    out = [f"🏆 Best-rated item: **{by['mean'].idxmax()}** ({by['mean'].max():.1f}★)",
           f"⚠️ Needs work: **{by['mean'].idxmin()}** ({by['mean'].min():.1f}★)",
           f"📉 Weakest area: **{cat.idxmin()}** ({cat.min():.1f}/5) · strongest: **{cat.idxmax()}** ({cat.max():.1f}/5)"]
    recent = df[df["time"] >= datetime.now() - timedelta(hours=1)]
    if len(recent) >= 3 and recent["overall"].mean() < df["overall"].mean() - 0.4:
        out.append("🚨 Ratings in the **last hour** are well below the average – check the floor now!")
    return out


# ------------------------------ UI ------------------------------
CSS = """<style>
.stApp{background:linear-gradient(160deg,#fff7ec 0%,#fffdf8 50%,#f1f8f4 100%)}
.hero{background:linear-gradient(90deg,#c8742c,#e9a23b);color:#fff;border-radius:20px;padding:16px 24px;margin-bottom:12px}
.hero h1{margin:0;color:#fff;font-size:1.8rem}.hero p{margin:4px 0 0;opacity:.95}
.live{display:inline-block;background:#e6f9ee;color:#1b7a3d;padding:3px 12px;border-radius:20px;font-weight:700;font-size:.85rem}
.live i{display:inline-block;width:9px;height:9px;border-radius:50%;background:#2fbf71;margin-right:6px;animation:p 1.2s infinite}
@keyframes p{50%{opacity:.25}}
div.stButton>button,div.stFormSubmitButton>button{border-radius:12px;font-weight:700}
</style>"""


def dashboard():
    store, now = get_store(), datetime.now()
    if st.session_state.get("sim") and (now - st.session_state.get("last_sim", now - timedelta(seconds=9))).total_seconds() >= 3:
        r = sample_rows(1)[0]
        r["time"] = now.strftime("%Y-%m-%d %H:%M:%S")      # a customer who just submitted
        store.add([r])
        st.session_state.last_sim = now
    df = store.read()
    st.markdown(f'<span class="live"><i></i>LIVE</span> &nbsp; updated {now:%H:%M:%S}'
                + (" · auto-refreshing every 3 s" if st.session_state.get("live", True) else " · paused"), unsafe_allow_html=True)
    if df.empty:
        st.info("No feedback yet – open the **Give Feedback** tab (or load sample data in **Admin**) and watch this page update.")
        return
    hour = df[df["time"] >= now - timedelta(hours=1)]
    today = df[df["time"].dt.date == now.date()]
    k = st.columns(5)
    k[0].metric("Responses", len(df), f"+{len(hour)} in last hour")
    k[1].metric("Average rating", f"{df['overall'].mean():.2f} ★")
    k[2].metric("NPS", nps_score(df["nps"]), help="% promoters (9–10) minus % detractors (0–6)")
    k[3].metric("Satisfied (≥4★)", f"{100 * (df['overall'] >= 4).mean():.0f}%")
    k[4].metric("Today", len(today))
    for line in insights(df):
        st.markdown(line)

    a, b = st.columns(2)
    dist = df["overall"].round().clip(1, 5).astype(int).value_counts().reindex(range(1, 6), fill_value=0)
    dist.index = [f"{i}★" for i in dist.index]
    a.caption("Rating distribution"); a.bar_chart(dist)
    b.caption("Average score by area (out of 5)"); b.bar_chart(df[CATS].mean().round(2))

    c, d = st.columns(2)
    daily = df.groupby(df["time"].dt.date).agg(avg=("overall", "mean"), n=("overall", "size"))
    daily.index = daily.index.astype(str)
    c.caption("Average rating per day"); c.line_chart(daily["avg"])
    d.caption("Responses per day"); d.bar_chart(daily["n"])

    e, f = st.columns(2)
    prod = df.groupby("product").agg(Responses=("overall", "size"), Rating=("overall", "mean")).sort_values("Rating", ascending=False)
    prod["Rating"] = prod["Rating"].round(2)
    e.caption("Menu leaderboard"); e.dataframe(prod)
    sent = df["comment"].apply(sentiment).value_counts().reindex(["Positive", "Neutral", "Negative"], fill_value=0)
    f.caption("What the comments feel like"); f.bar_chart(sent)

    g, h = st.columns(2)
    kw = keywords(df)
    g.caption("Words guests use most")
    if len(kw):
        g.bar_chart(kw)
    h.caption("Dine-in vs takeaway vs delivery (avg rating)")
    h.bar_chart(df.groupby("visit")["overall"].mean().round(2))

    st.subheader("🚨 Needs attention (low ratings)")
    low = df[df["overall"] <= 2.5].sort_values("time", ascending=False).head(4)
    if low.empty:
        st.success("No low ratings right now 🎉")
    for _, r in low.iterrows():
        st.error(f"{r['time']:%d %b %H:%M} · {r['product']} · {r['overall']:.1f}★ · “{r['comment'] or 'no comment'}”")
    st.subheader("🕒 Latest feedback")
    for _, r in df.sort_values("time", ascending=False).head(6).iterrows():
        icon = "🟢" if r["overall"] >= 4 else "🟡" if r["overall"] >= 3 else "🔴"
        st.markdown(f"{icon} **{r['product']}** · {r['visit']} · {r['overall']:.1f}★ · {r['time']:%H:%M:%S}  \n&nbsp;&nbsp;&nbsp;“{r['comment'] or '—'}”")


def feedback_form():
    st.subheader(f"Tell {BUSINESS} how we did ☕")
    with st.form("fb", clear_on_submit=True):
        c1, c2 = st.columns(2)
        product = c1.selectbox("What did you have?", PRODUCTS)
        visit = c2.selectbox("How did you enjoy it?", VISITS)
        st.caption("Rate each area from 1 (poor) to 5 (excellent)")
        r1, r2 = st.columns(2)
        taste = r1.slider("😋 Taste & freshness", 1, 5, 4)
        service = r2.slider("🙂 Service", 1, 5, 4)
        r3, r4 = st.columns(2)
        clean = r3.slider("✨ Cleanliness", 1, 5, 4)
        value = r4.slider("💰 Value for money", 1, 5, 4)
        nps = st.slider("How likely are you to recommend us to a friend? (0–10)", 0, 10, 8)
        comment = st.text_area("Anything else? (optional)", max_chars=300)
        go = st.form_submit_button("Send feedback 🚀")
    if go:
        get_store().add([make_row(product, visit, taste, service, clean, value, nps, comment)])
        st.success("Thank you! Your feedback is already on the live dashboard. 💛")
        st.balloons()


def admin():
    store = get_store()
    st.subheader("Admin tools")
    c1, c2 = st.columns(2)
    if c1.button("📥 Load 70 sample responses"):
        store.add(sample_rows(70)); st.success("Sample data added.")
    st.toggle("🤖 Simulate live customers (adds a response every ~3 s)", key="sim")
    sure = c2.checkbox("I'm sure I want to delete all data")
    if c2.button("🗑️ Clear all feedback", disabled=not sure):
        store.clear(); st.warning("All feedback deleted.")
    df = store.read()
    st.download_button("⬇️ Download all feedback (CSV)", df.to_csv(index=False), "sunrise_cafe_feedback.csv", "text/csv", disabled=df.empty)
    st.caption(f"Data file: `{store.path}` · {len(df)} rows")


def main():
    st.set_page_config(page_title=f"{BUSINESS} Live Feedback", page_icon="☕", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="hero"><h1>☕ {BUSINESS} · Live Feedback Dashboard</h1>'
                f'<p>Customers give feedback → the owner sees it on the dashboard within seconds.</p></div>', unsafe_allow_html=True)
    with st.sidebar:
        st.toggle("🔴 Live auto-refresh (every 3 s)", value=True, key="live")
        st.caption("Switch it off to pause the dashboard while you read it.")
    t1, t2, t3 = st.tabs(["📊 Live Dashboard", "📝 Give Feedback", "⚙️ Admin"])
    with t1:
        if hasattr(st, "fragment"):
            st.fragment(run_every=3 if st.session_state.get("live", True) else None)(dashboard)()
        else:
            st.button("🔄 Refresh"); dashboard()
    with t2:
        feedback_form()
    with t3:
        admin()


if __name__ == "__main__":
    main()
