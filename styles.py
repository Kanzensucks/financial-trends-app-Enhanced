"""Custom CSS for the Streamlit app.

Palette: dark navy base, cool-toned data (indigo/blue/teal/cyan for quarters),
warm amber accents for highlights and interactive states, soft emerald/rose
for semantic positive/negative.
"""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600&display=swap');

:root {
    --bg-deep:     #0B0F1A;
    --bg-card:     #131A2B;
    --bg-hover:    #182036;
    --border:      #1E293B;
    --border-warm: #2A2215;
    --text-main:   #F1F5F9;
    --text-muted:  #94A3B8;
    --text-dim:    #64748B;
    --accent:      #14B8A6;
    --warm:        #F59E0B;
    --warm-glow:   rgba(245, 158, 11, 0.08);
    --indigo:      #6366F1;
    --positive:    #34D399;
    --negative:    #FB7185;
}

html, body, [class*="css"], .stApp, .stMarkdown, .stText {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.stApp {
    background: linear-gradient(165deg, #0E1525 0%, #0B0F1A 40%, #0D1117 100%);
}

/* ─── Generic card ───────────────────────────────────────────────────── */
.card {
    background: linear-gradient(135deg, var(--bg-card) 0%, #152033 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 18px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}
.card h3 {
    margin: 0 0 14px 0;
    color: var(--warm);
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.04em;
}

/* ─── Metric cards (the four big TTM numbers) ────────────────────────── */
.metric-card {
    background: linear-gradient(160deg, #131A2B 0%, #0F1624 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px 22px;
    height: 100%;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--indigo), var(--accent), #22D3EE);
    opacity: 0;
    transition: opacity 0.2s ease;
}
.metric-card:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(20, 184, 166, 0.12);
}
.metric-card:hover::before {
    opacity: 1;
}
.metric-label {
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 10px;
}
.metric-value {
    color: var(--text-main);
    font-size: 28px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: -0.02em;
    line-height: 1.1;
}
.metric-delta {
    font-size: 13px;
    font-weight: 600;
    margin-top: 8px;
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
}
.metric-delta-pos {
    color: var(--positive);
    background: rgba(52, 211, 153, 0.12);
}
.metric-delta-neg {
    color: var(--negative);
    background: rgba(251, 113, 133, 0.12);
}

/* ─── Company header ─────────────────────────────────────────────────── */
.company-header {
    padding: 8px 0 22px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 26px;
}
.company-name {
    font-size: 34px;
    font-weight: 800;
    color: var(--text-main);
    letter-spacing: -0.03em;
    line-height: 1.1;
}
.company-ticker {
    color: var(--warm);
    font-size: 22px;
    font-weight: 700;
    margin-left: 12px;
    padding: 2px 10px;
    background: var(--warm-glow);
    border-radius: 6px;
}
.company-sub {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 6px;
    letter-spacing: 0.01em;
}

/* ─── AI insight bullets ─────────────────────────────────────────────── */
.insight-bullet {
    color: #CBD5E1;
    font-size: 14px;
    line-height: 1.6;
    padding: 10px 0 10px 4px;
    border-bottom: 1px solid var(--border);
}
.insight-bullet:last-child { border: none; padding-bottom: 2px; }
.insight-dot {
    color: var(--warm);
    font-weight: 700;
    margin-right: 8px;
}

.ai-commentary {
    background: linear-gradient(135deg, #131A2B 0%, #15202E 100%);
    border-left: 3px solid var(--warm);
    border-radius: 10px;
    padding: 16px 20px;
    color: #CBD5E1;
    font-size: 14px;
    line-height: 1.6;
    margin-bottom: 18px;
}
.ai-commentary .ai-tag {
    color: var(--warm);
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    display: block;
    margin-bottom: 6px;
}

.placeholder {
    color: var(--text-dim);
    font-style: italic;
    font-size: 13px;
}

/* ─── Tabs ────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: transparent;
    border-bottom: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 10px 10px 0 0;
    color: var(--text-muted);
    font-weight: 500;
    padding: 12px 22px;
    font-size: 14px;
}
.stTabs [aria-selected="true"] {
    background: var(--bg-card);
    color: var(--warm);
    font-weight: 600;
}

/* ─── Sidebar ─────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #080C14;
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] h3 {
    color: var(--text-main);
    font-weight: 700;
}
.search-label {
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 6px 0 6px 2px;
}
[data-testid="stSidebar"] .stSelectbox label { display: none; }

/* Sidebar company card — always visible while scrolling main content */
.sidebar-company {
    background: linear-gradient(135deg, var(--bg-card) 0%, #152033 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 14px;
}
.sidebar-company-name {
    color: var(--text-main);
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.2;
}
.sidebar-company-ticker {
    color: var(--warm);
    font-size: 13px;
    font-weight: 700;
    display: inline-block;
    margin-top: 4px;
    padding: 1px 8px;
    background: var(--warm-glow);
    border-radius: 4px;
}
.sidebar-company-sub {
    color: var(--text-dim);
    font-size: 11px;
    margin-top: 6px;
    line-height: 1.3;
}
[data-testid="stSidebar"] .stTextInput input {
    background: var(--bg-card);
    color: var(--text-main);
    border: 1px solid #334155;
    border-radius: 10px;
    font-weight: 600;
}
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: var(--warm);
    box-shadow: 0 0 0 3px var(--warm-glow);
}
.stButton > button {
    background: linear-gradient(135deg, var(--accent) 0%, #0D9488 100%);
    color: #0B0F1A;
    border: none;
    border-radius: 10px;
    font-weight: 700;
    padding: 10px 20px;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #0D9488 0%, var(--accent) 100%);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(20, 184, 166, 0.25);
}

/* ─── Chart section headers ───────────────────────────────────────────── */
.chart-header {
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin: 14px 0 4px 2px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--border);
}
.chart-sublabel {
    color: var(--text-dim);
    font-size: 10px;
    font-weight: 500;
    margin: 10px 0 2px 2px;
    letter-spacing: 0.04em;
}

/* ─── Financial statement tables ──────────────────────────────────────── */
.stmt-wrap {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 4px 4px 4px;
    margin-bottom: 14px;
    overflow: auto;
    max-height: 560px;
    position: relative;
}
/* Subtle right-edge shadow hinting there's more content to scroll */
.stmt-wrap::after {
    content: "";
    position: sticky;
    right: 0;
    top: 0;
    bottom: 0;
    width: 30px;
    background: linear-gradient(to right, transparent, var(--bg-card));
    pointer-events: none;
    float: right;
    height: 100%;
}
.stmt-title {
    color: var(--warm);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 4px 18px 10px 18px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 6px;
    text-transform: uppercase;
}
.stmt-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
    font-size: 12.5px;
}
.stmt-table thead th {
    color: var(--text-dim);
    font-weight: 600;
    font-size: 10.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    text-align: right;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-card);
    position: sticky;
    top: 0;
    white-space: nowrap;
}
.stmt-table thead th:first-child {
    text-align: left;
    position: sticky;
    left: 0;
    z-index: 3;
}
.stmt-table tbody td {
    padding: 8px 12px;
    text-align: right;
    color: #E2E8F0;
    border-bottom: 1px solid #111827;
    white-space: nowrap;
}
.stmt-table tbody td:first-child {
    text-align: left;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    color: var(--text-main);
    background: var(--bg-card);
    position: sticky;
    left: 0;
    z-index: 2;
    border-right: 1px solid var(--border);
    padding-right: 22px;
}
.stmt-table tbody tr:hover td {
    background: var(--bg-hover);
}
.stmt-table tbody tr:hover td:first-child {
    background: var(--bg-hover);
}
.stmt-table td.pos { color: var(--positive); }
.stmt-table td.neg { color: var(--negative); }
.stmt-table td.muted { color: #475569; }

/* ─── Jargon tooltips (hover to learn) ─────────────────────────────────── */
abbr.tip {
    text-decoration: underline dotted var(--text-dim);
    text-underline-offset: 3px;
    cursor: help;
    color: inherit;
}

/* ─── Misc ────────────────────────────────────────────────────────────── */
.stDataFrame, [data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
}
.streamlit-expanderHeader {
    background: var(--bg-card);
    border-radius: 8px;
    color: #CBD5E1;
}
.js-plotly-plot .plotly .modebar {
    background: transparent !important;
}

/* Hide streamlit branding */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
</style>
"""


STICKY_TABS_JS = """
<script>
(function() {
    const doc = window.parent.document;

    function init() {
        const tabList = doc.querySelector('[data-baseweb="tab-list"]');
        if (!tabList) { setTimeout(init, 500); return; }
        if (tabList.dataset.stickyInit) return;
        tabList.dataset.stickyInit = '1';

        // Find the scrollable container
        let scroller = null;
        let el = tabList.parentElement;
        while (el && el !== doc.body) {
            const s = window.parent.getComputedStyle(el);
            if (s.overflowY === 'auto' || s.overflowY === 'scroll') {
                scroller = el; break;
            }
            el = el.parentElement;
        }
        if (!scroller) return;

        // Snapshot the tab bar's exact position BEFORE we touch anything
        const rect = tabList.getBoundingClientRect();
        const naturalLeft = rect.left;
        const naturalWidth = rect.width;
        const naturalTop = rect.top - scroller.getBoundingClientRect().top + scroller.scrollTop;
        const tabHeight = rect.height;

        const placeholder = doc.createElement('div');
        placeholder.style.display = 'none';
        placeholder.style.height = tabHeight + 'px';
        tabList.parentNode.insertBefore(placeholder, tabList);

        let pinned = false;

        function tick() {
            // Check if the company header is also pinned — sit below it
            const pinnedHeader = doc.querySelector('.company-header');
            const headerPinned = pinnedHeader && pinnedHeader.style.position === 'fixed';
            const topOffset = headerPinned ? pinnedHeader.offsetHeight : 0;

            if (scroller.scrollTop >= naturalTop && !pinned) {
                pinned = true;
                placeholder.style.display = 'block';
                tabList.style.position = 'fixed';
                tabList.style.top = topOffset + 'px';
                tabList.style.left = naturalLeft + 'px';
                tabList.style.width = naturalWidth + 'px';
                tabList.style.zIndex = '999';
                tabList.style.background = '#0B0F1A';
                tabList.style.borderBottom = '1px solid #1E293B';
                tabList.style.boxShadow = '0 4px 20px rgba(0,0,0,0.4)';
            } else if (scroller.scrollTop < naturalTop && pinned) {
                pinned = false;
                placeholder.style.display = 'none';
                tabList.style.position = '';
                tabList.style.top = '';
                tabList.style.left = '';
                tabList.style.width = '';
                tabList.style.zIndex = '';
                tabList.style.background = '';
                tabList.style.borderBottom = '';
                tabList.style.boxShadow = '';
            }
            // Keep top offset synced while pinned
            if (pinned) {
                tabList.style.top = topOffset + 'px';
            }
        }

        scroller.addEventListener('scroll', tick, { passive: true });
        tick();
    }

    setTimeout(init, 800);

    // --- Same treatment for the company header ---
    function initHeader() {
        const header = doc.querySelector('.company-header');
        if (!header) { setTimeout(initHeader, 500); return; }
        if (header.dataset.stickyInit) return;
        header.dataset.stickyInit = '1';

        let scroller = null;
        let el = header.parentElement;
        while (el && el !== doc.body) {
            const s = window.parent.getComputedStyle(el);
            if (s.overflowY === 'auto' || s.overflowY === 'scroll') {
                scroller = el; break;
            }
            el = el.parentElement;
        }
        if (!scroller) return;

        const rect = header.getBoundingClientRect();
        const naturalLeft = rect.left;
        const naturalWidth = rect.width;
        const naturalTop = rect.top - scroller.getBoundingClientRect().top + scroller.scrollTop;
        const headerHeight = rect.height;

        const placeholder = doc.createElement('div');
        placeholder.style.display = 'none';
        placeholder.style.height = headerHeight + 'px';
        header.parentNode.insertBefore(placeholder, header);

        let pinned = false;

        function tick() {
            if (scroller.scrollTop >= naturalTop && !pinned) {
                pinned = true;
                placeholder.style.display = 'block';
                header.style.position = 'fixed';
                header.style.top = '0px';
                header.style.left = naturalLeft + 'px';
                header.style.width = naturalWidth + 'px';
                header.style.zIndex = '1000';
                header.style.background = '#0B0F1A';
                header.style.padding = '8px 0 8px 0';
                header.style.borderBottom = '1px solid #1E293B';
                header.style.boxShadow = '0 4px 20px rgba(0,0,0,0.4)';
            } else if (scroller.scrollTop < naturalTop && pinned) {
                pinned = false;
                placeholder.style.display = 'none';
                header.style.position = '';
                header.style.top = '';
                header.style.left = '';
                header.style.width = '';
                header.style.zIndex = '';
                header.style.background = '';
                header.style.padding = '';
                header.style.borderBottom = '';
                header.style.boxShadow = '';
            }
        }

        scroller.addEventListener('scroll', tick, { passive: true });
        tick();

        // Now re-init tabs so they sit below the pinned header
        function fixTabOffset() {
            const tabList = doc.querySelector('[data-baseweb="tab-list"]');
            if (!tabList || !tabList.dataset.stickyInit) return;
            // Update tab top offset when header is pinned
            const origTick = scroller._tabTick;
            if (!origTick) return;
        }
    }
    setTimeout(initHeader, 600);
})();
</script>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
    st.components.v1.html(STICKY_TABS_JS, height=0)
