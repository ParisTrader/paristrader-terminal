import streamlit as st
from streamlit_option_menu import option_menu
import streamlit.components.v1 as components
import os
import sys
import glob
import time

# 加入 Trade 資料夾路徑
sys.path.append('Trade')
try:
    from Trade import trade_app
except ImportError:
    pass


# ==========================================
# 🔐 安全登入系統 (Security Gate)
# ==========================================
def login_system():
    """
    簡單的登入驗證：檢查 Email 是否在白名單內 + 驗證通用密碼
    """
    # 如果已經登入成功，直接返回 True
    if "authentication_status" in st.session_state and st.session_state["authentication_status"]:
        return True

    # 登入介面
    st.markdown("""
    <style>
        .stApp { background: #0B0E14; }
        .login-box { 
            background: rgba(30, 41, 59, 0.5); 
            padding: 40px; 
            border-radius: 20px; 
            border: 1px solid rgba(255,255,255,0.1);
            text-align: center;
            max-width: 500px;
            margin: 100px auto;
        }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            "<div style='text-align: center; margin-top: 50px;'><h2>🔒 ParisTrader Pro</h2><p style='color:#94A3B8'>Member Access Only</p></div>",
            unsafe_allow_html=True)

        with st.form("login_form"):
            email_input = st.text_input("Email Address")
            password_input = st.text_input("Access Password", type="password")
            submit_button = st.form_submit_button("Login", type="primary", use_container_width=True)

        if submit_button:
            # 1. 從 Secrets 獲取白名單和密碼
            try:
                valid_emails = st.secrets["allowed_users"]["emails"]
                correct_password = st.secrets["access_password"]
            except FileNotFoundError:
                st.error("⚠️ 系統錯誤：未設定 Secrets (請聯繫管理員)")
                return False

            # 2. 驗證邏輯
            if email_input in valid_emails and password_input == correct_password:
                st.session_state["authentication_status"] = True
                st.session_state["user_email"] = email_input
                st.success("Login Successful! Redirecting...")
                time.sleep(1)
                st.rerun()  # 重新整理進入主頁
            else:
                st.session_state["authentication_status"] = False
                st.error("❌ Access Denied: Email not in whitelist or wrong password.")

    return False


# --- 主程式邏輯 ---
# 如果沒有通過登入驗證，就停止執行後面的程式碼
if not login_system():
    st.stop()  # ⛔ 這裡會擋住所有人，除非登入成功

# ==========================================
# 👇 您的原始程式碼從這裡開始 (原本的 Sidebar, Content 等)
# ==========================================

# ==========================================
# 1. 頁面基礎設置
# ==========================================
st.set_page_config(
    page_title="ParisTrader Professional Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. 自定義 CSS (背景與介面優化 - 含手機版修復)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;500;700&display=swap');

    /* [關鍵] 強制將 Streamlit 主容器背景設為透明 */
    .stApp {
        background: transparent !important;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', 'Microsoft JhengHei', sans-serif;
        color: #e2e8f0;
    }

    /* ----------------------------------------------------
       📱 手機與電腦的差異化設定 (Media Queries)
       ---------------------------------------------------- */

    /* === 電腦版 (螢幕寬度 > 768px) === */
    @media (min-width: 768.1px) {
        /* 電腦版隱藏 Header，追求極簡 */
        header {
            visibility: hidden !important;
        }
        /* 電腦版隱藏原生的漢堡選單 */
        #MainMenu {
            visibility: hidden !important;
            display: none !important;
        }
    }

    /* === 手機版 (螢幕寬度 <= 768px) === */
    @media (max-width: 768px) {
        /* 1. 讓 Header 可見，這樣才能點擊左上角的箭頭打開 Sidebar */
        header {
            visibility: visible !important;
            background: transparent !important;
        }

        /* 2. 讓左上角的選單按鈕更明顯一點 (半透明黑底)，以免看不見 */
        header button[kind="header"] {
            background-color: rgba(17, 24, 39, 0.6) !important;
            color: white !important;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
        }

        /* 3. [解決空間太少] 縮小手機版內容的邊距 (Padding) */
        .block-container {
            padding-top: 3rem !important;    /* 留一點空間給選單按鈕 */
            padding-left: 1rem !important;   /* 減少左右留白 */
            padding-right: 1rem !important;
        }

        /* 4. 手機版字體稍微調小，避免標題爆框 */
        h1 { font-size: 1.8rem !important; }
        h2 { font-size: 1.5rem !important; }
        h3 { font-size: 1.2rem !important; }
    }

    /* ----------------------------------------------------
       共用設定 (保持原樣)
       ---------------------------------------------------- */

    /* 隱藏右下角 Footer */
    footer {
        visibility: hidden !important;
        display: none !important;
    }

    /* 隱藏彩虹線裝飾 */
    div[data-testid="stDecoration"] {
        display: none !important;
    }

    /* --- 背景層 --- */
    .fixed-bg {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; 
        z-index: -1; 
        background-color: #020617;
        background-image: 
            linear-gradient(to right, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
        background-size: 50px 50px;
        mask-image: linear-gradient(to bottom, black 40%, transparent 100%);
        -webkit-mask-image: linear-gradient(to bottom, black 40%, transparent 100%);
    }

    .fixed-blobs {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; 
        z-index: -1;
        background: 
            radial-gradient(circle at 10% 10%, rgba(79, 70, 229, 0.15) 0%, transparent 40%),
            radial-gradient(circle at 90% 20%, rgba(14, 165, 233, 0.15) 0%, transparent 40%),
            radial-gradient(circle at 30% 90%, rgba(16, 185, 129, 0.1) 0%, transparent 40%);
        filter: blur(60px); pointer-events: none;
    }

    /* --- 側邊欄樣式 --- */
    section[data-testid="stSidebar"] {
        background-color: #111827; 
        border-right: 1px solid #374151;
        z-index: 999999 !important; /* 加大層級，確保蓋過內容 */
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div {
        color: #F3F4F6 !important;
    }

    /* --- Dashboard 卡片 --- */
    .metric-card {
        background: rgba(17, 24, 39, 0.7); backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px;
        padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;
    }
    .metric-card h4 { color: #94a3b8; font-size: 0.9em; text-transform: uppercase; margin: 0; }
    .metric-card h2 { color: #f8fafc; margin: 5px 0; font-size: 1.8em; }

    .profile-card {
        background: rgba(17, 24, 39, 0.7); backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px;
        padding: 25px; text-align: center;
    }

    .custom-footer {
        margin-top: 50px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center; color: #94a3b8; font-size: 0.8rem;
    }
    .custom-footer a { color: #60a5fa; text-decoration: none; margin: 0 10px; }
    .custom-footer a:hover { text-decoration: underline; }

    .legal-text {
        font-size: 0.95rem; line-height: 1.7; color: #e2e8f0; text-align: justify;
        background: rgba(255, 255, 255, 0.03); padding: 30px;
        border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .legal-text h3 { color: #f8fafc !important; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; margin-bottom: 20px; }
    .legal-text h4 { color: #e2e8f0 !important; margin-top: 20px; font-weight: bold; }
    .legal-text strong { color: #f8fafc !important; }
</style>

<div class="fixed-bg"></div>
<div class="fixed-blobs"></div>
""", unsafe_allow_html=True)


# ==========================================
# 3. Helper Functions
# ==========================================
def load_html_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        return f"<div style='padding:20px; color:red;'>⚠️ File not found: {file_path}</div>"


def load_stock_dna_with_injection():
    html_path = os.path.join("FamaFrench", "index.html")
    csv_path = os.path.join("FamaFrench", "stock_factor_data.csv")

    if not os.path.exists(html_path):
        return f"<div style='color:red'>找不到 HTML: {html_path}</div>"

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_data = f.read()
        injection_js = f"""
        var csvData = `{csv_data}`;
        Papa.parse(csvData, {{
            download: false, 
        """
        target_str = 'Papa.parse("stock_factor_data.csv", {'
        if target_str in html_content:
            html_content = html_content.replace(target_str, injection_js)
            html_content = html_content.replace('download: true,', '')
    return html_content


def get_latest_file_content(folder_path):
    if not os.path.exists(folder_path):
        return None, f"Directory not found: {folder_path}"

    search_pattern = os.path.join(folder_path, "*.html")
    list_of_files = glob.glob(search_pattern)

    if not list_of_files:
        return None, "No HTML files found."

    latest_file = max(list_of_files, key=os.path.getctime)

    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            return f.read(), os.path.basename(latest_file)
    except Exception as e:
        return None, str(e)


# ==========================================
# 4. Main App Interface (Mixed Navigation)
# ==========================================

# --- Sidebar ---
with st.sidebar:
    st.markdown("""
    <div style='padding: 20px 0px; text-align: center; border-bottom: 1px solid #374151; margin-bottom: 20px;'>
        <h2 style='color: #F3F4F6; margin:0; letter-spacing: 1px; font-weight: 700;'>ParisTrader</h2>
        <p style='color: #9CA3AF; font-size: 0.85em; margin-top:5px;'>Algo & Quant Research</p>
    </div>
    """, unsafe_allow_html=True)

    # 主導航菜單 (混合模式：部分是直接連結，部分是群組)
    selected_nav = option_menu(
        menu_title="Navigation",
        options=[
            "Home",
            "Market Intelligence",  # Group
            "Stock",  # Group
            "Option",  # Option
            "Future",       # Future
            "My Trade",  # Direct
            "MT5 EA",  # Direct
            "Legal"  # Direct
        ],
        icons=[
            "house",
            "globe",
            "search",
            "layers",
            "graph-up-arrow",
            "briefcase",
            "robot",
            "file-text"
        ],
        menu_icon="compass",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#9CA3AF", "font-size": "15px"},
            "nav-link": {
                "font-size": "15px", "text-align": "left", "margin": "5px",
                "color": "#D1D5DB", "--hover-color": "#1F2937",
            },
            "nav-link-selected": {"background-color": "#2563EB", "color": "#FFFFFF", "font-weight": "600"},
        }
    )

    # 路由變數
    target_page = None

    # --- 邏輯處理 ---
    if selected_nav == "Home":
        target_page = "Home"

    elif selected_nav == "Market Intelligence":
        st.caption("MARKET MODULES")
        target_page = option_menu(
            menu_title=None,
            # 👇 Added "SPX vs VIX Scatter"
            options=["Market Dashboard", "Market Risk", "Market Breadth", "Industry Sector Heatmap"],
            # 👇 Added "crosshair" icon
            icons=["speedometer2", "activity", "bar-chart-line", "grid-3x3", "crosshair"],
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    elif selected_nav == "Stock":
        st.caption("STOCK RESEARCH")
        target_page = option_menu(
            menu_title=None,
            options=["Earnings", "Stock DNA", "Thematic Basket", "Volatility Target"], # Added Volatility Target
            icons=["cash-coin", "radar", "basket", "bullseye"], # Added icon for VolTarget
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    # Option 路由邏輯
    elif selected_nav == "Option":
        target_page = "Option"

        # 👇 [修改] Future 區塊邏輯 (包含 Volume Profile 和 Intraday Volatility)
    elif selected_nav == "Future":
        st.caption("FUTURES & TRENDS")
        target_page = option_menu(
            menu_title=None,
            options=["Volume Profile", "Intraday Volatility"],
            icons=["bar-chart-steps", "lightning-charge"],  # 為 Volatility 加上圖標
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    elif selected_nav == "My Trade":
        target_page = "My Trade"

    elif selected_nav == "MT5 EA":
        target_page = "MT5 EA"

    elif selected_nav == "Legal":
        target_page = "Legal & Compliance"

    st.markdown("---")
    st.link_button("✈️VIP Channel", "https://parisprogram.uk/", use_container_width=True)

# --- Content Routing ---

# [PAGE] HOME
if target_page == "Home":
    col_main, col_profile = st.columns([0.7, 0.3], gap="large")

    with col_main:
        st.markdown("""
        <h1 style='color:white;'>這裡是您的量化交易指揮中心</h1>
        <h3 style='color:#94a3b8;'>這是一款能幫助你戰勝市場的機構級 APP。</h3>
        <p style='font-size: 1.1em; color: #64748b;'>
        僅限尊貴谷友實時解鎖所有強大功能。請從左側導航欄選擇工具開始分析。
        </p>
        """, unsafe_allow_html=True)

        st.markdown("---")

        st.subheader("📊 Market Overview")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown("""
            <div class="metric-card">
                <h4>Risk Appetite</h4>
                <h2 style="color:#10B981 !important;">Risk-On</h2>
                <span style="color:#10B981; font-weight:bold; font-size:0.9em;">▲ Momentum not very strong</span>
            </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown("""
            <div class="metric-card">
                <h4>Sector Rotation</h4>
                <h2 style="color:#3b82f6 !important;">Health care & Insurance & Materials</h2>
                <span style="color:#3b82f6; font-weight:bold; font-size:0.9em;">Flow Inflow</span>
            </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown("""
            <div class="metric-card">
                <h4>Volatility (VIX)</h4>
                <h2 style="color:#94a3b8 !important;">16.6</h2>
                <span style="color:#64748b; font-weight:bold; font-size:0.9em;">low vol</span>
            </div>
            """, unsafe_allow_html=True)

    with col_profile:
        img_path = "static/profile.jpg"
        if not os.path.exists(img_path):
            img_src = "https://ui-avatars.com/api/?name=Paris+Trader&background=0D8ABC&color=fff&size=150"
        else:
            img_src = img_path

        st.markdown('<div class="profile-card">', unsafe_allow_html=True)
        if os.path.exists(img_path):
            st.image(img_path, width=120)
        else:
            st.image(img_src, width=120)

        st.markdown("""
            <h3 style="margin-top:10px; color:#F3F4F6;">Paris Trader</h3>
            <p style="color: #9CA3AF; font-size: 0.9em;">Quantitative Analyst | Trader</p>
            <hr style="margin: 15px 0; border-top: 1px solid rgba(255,255,255,0.1);">
            <p style="text-align: left; font-size: 0.9em; line-height: 1.6; color: #e2e8f0;">
                專注於量化因子挖掘與演算法交易。擅長將複雜的金融模型轉化為可執行的交易策略。提供TradingView指標及回測。
                <br><br>
                <b>主力策略：</b><br>
                • Multi-Factor Long/Short<br>
                • Equity Future HSI/NQ Scapling by Fate Engine<br>
                • XAU M1 EA Scapling<br>
            </p>
            <a href="https://t.me/ParisTrader" target="_blank" style="text-decoration: none;">
                <button style="background-color:#2563EB; color:white; border:none; padding:10px 20px; border-radius:6px; cursor:pointer; width:100%; margin-top:10px; font-weight:bold;">
                    Contact Me
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)

# [PAGE] Market Dashboard
elif target_page == "Market Dashboard":
    st.title("Market Dashboard")
    path = os.path.join("MarketDashboard", "main_auto", "output")
    html_content, filename = get_latest_file_content(path)

    if html_content:
        components.html(html_content, height=2500, scrolling=False)
    else:
        st.warning("⚠️ No dashboard files found.")
        st.error(f"Error: {filename}")

# [PAGE] Market Risk
elif target_page == "Market Risk":
    st.title("⚠️ Market Implied Risk")
    path = "ImpliedParameters"
    specific_file = os.path.join(path, "implied_params.html")

    if os.path.exists(specific_file):
        with open(specific_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
            # CSS 修復：取消垂直置中
            fix_style = """
            <style>
                body {
                    display: block !important;
                    height: auto !important;
                    min-height: 100vh;
                    padding-top: 50px;
                    background-color: #020617 !important;
                }
                .card { margin: 0 auto !important; }
            </style>
            """
            html_content = html_content.replace("<head>", "<head>" + fix_style)
            components.html(html_content, height=2200, scrolling=False)
    else:
        html_content, filename = get_latest_file_content(path)
        if html_content:
            components.html(html_content, height=2200, scrolling=False)
        else:
            st.warning("⚠️ No risk reports found.")
            st.info("Please ensure `ImpliedParameters/implied_params.html` exists.")

# [PAGE] Market Breadth (New Added)
elif target_page == "Market Breadth":
    st.title("🌊 Market Breadth")

    # Path to the file generated by the new script
    path = os.path.join("MarketDashboard", "market_breadth.html")

    # Check if file exists and load it
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            components.html(html_content, height=2200, scrolling=True)
    else:
        st.warning("⚠️ Market Breadth report not found.")
        st.info(f"Please run `MarketDashboard/generate_market_breadth.py` to generate the report.")

# [PAGE] Industry Sector Heatmap (New Independent Page)
elif target_page == "Industry Sector Heatmap":
    st.title("🔥 Industry Sector Heatmap")
    st.caption("Daily Return Heatmap (Last 20 Days)")

    # Path to the Heatmap HTML
    path = os.path.join("MarketDashboard", "sector_etf_heatmap.html")

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            # Heatmaps are wide, give it plenty of height and scrolling
            components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ Sector Heatmap not found.")
        st.info("Please run `MarketDashboard/ETF_sector_heatmap.py`.")

# [PAGE] Earnings
elif target_page == "Earnings":
    st.title("📅 Earnings Calendar Analysis")
    path = "Earnings"
    html_content, filename = get_latest_file_content(path)

    if html_content:
        components.html(html_content, height=2500, scrolling=False)
    else:
        st.warning("⚠️ No earnings reports found.")
        st.info("請確認根目錄下有 `Earnings` 資料夾，並且裡面有 .html 檔案。")

# [PAGE] Stock DNA
elif target_page == "Stock DNA":
    st.title("🧬 Stock Factor DNA")
    html_content = load_stock_dna_with_injection()
    if html_content and "找不到 HTML" not in html_content:
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.error("找不到 FamaFrench/index.html")

# [PAGE] Thematic Basket
elif target_page == "Thematic Basket":
    st.title("🧺 Thematic Basket Analysis")
    path = "ThematicBasket"
    html_content, filename = get_latest_file_content(path)

    if html_content:
        st.caption(f"📅 Strategy Report: {filename}")
        components.html(html_content, height=6000, scrolling=False)
    else:
        st.warning("⚠️ No basket reports found.")
        st.info(f"Checking path: {os.path.abspath(path)}")

# [PAGE] Volatility Target (New Added)
elif target_page == "Volatility Target":
    st.title("📉 Volatility Target Strategy")
    html_path = os.path.join("VolTarget", "vol_tool.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=1500, scrolling=True)
    else:
        st.warning("⚠️ Volatility Tool not found.")
        st.info(f"Please ensure {html_path} exists.")

# [PAGE] Option
elif target_page == "Option":
    st.title("🎲 Option Analytics")
    st.markdown("""
    <div style='text-align: center; padding: 50px; background: rgba(255,255,255,0.03); border-radius: 10px; border: 1px dashed rgba(255,255,255,0.1); margin-top: 20px;'>
        <h2 style='color: #94A3B8; margin-bottom: 10px;'>🚧 Module Under Construction</h2>
        <p style='color: #64748B;'>Advanced Option Chain & Volatility Surface analysis tools are currently in development.</p>
    </div>
    """, unsafe_allow_html=True)

# [PAGE] Volume Profile
elif target_page == "Volume Profile":
    st.title("📊 Volume Profile Analysis")
    # 假設舊有的路徑是在 VP 資料夾下，如果路徑不同請自行調整
    html_path = os.path.join("VP", "volume_profile_dashboard.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=1000, scrolling=True)
    else:
        st.warning("⚠️ 尚未部署 Volume Profile 模組 (VP/volume_profile_dashboard.html)")

# [PAGE] Future -> Intraday Volatility (新增)
elif target_page == "Intraday Volatility":
    st.title("⚡ Intraday Volatility Analysis")

    # 根據您上一輪的描述，檔案名稱為 "Intraday_Volatility.html"
    # 這裡假設該檔案位於根目錄，如果是在 MarketDashboard 資料夾下，請改為 os.path.join("MarketDashboard", "Intraday_Volatility.html")
    html_path = "Intraday_Volatility.html"

    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        # 設定足夠的高度以顯示兩個圖表
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ 找不到 Intraday Volatility 報告")
        st.info(f"請確認檔案 `{html_path}` 是否存在。")
        
# [PAGE] My Trade
elif target_page == "My Trade":
    if 'trade_app' in locals():
        trade_app.render_trade_page()
    else:
        st.error("Trade module not loaded.")

# [PAGE] MT5 EA
elif target_page == "MT5 EA":
    st.title("🤖 MT5 Expert Advisor")
    path = "MT5EA"
    html_content, filename = get_latest_file_content(path)

    if html_content:
        components.html(html_content, height=3000, scrolling=False)
    else:
        st.warning("⚠️ No marketing content found.")
        st.info("請將行銷 HTML 放入專案根目錄的 `MT5EA` 資料夾中。")

# [PAGE] LEGAL
elif target_page == "Legal & Compliance":
    st.title("📜 Legal & Compliance")

    tab1, tab2, tab3 = st.tabs(["Disclaimer", "Privacy Policy", "Terms of Use"])

    with tab1:
        html = load_html_file(os.path.join("Legal", "disclaimer.html"))
        st.html(html)
    with tab2:
        html = load_html_file(os.path.join("Legal", "privacy.html"))
        st.html(html)
    with tab3:
        html = load_html_file(os.path.join("Legal", "terms.html"))
        st.html(html)

# ==========================================
# 5. Global Footer
# ==========================================
st.markdown("""
<div class="custom-footer">
    <p>
        © 2026 Paris Trader. All rights reserved.<br>
        <span style="font-size: 0.75rem; color: #6B7280;">
        Not financial advice · For informational and educational purposes only · I am not a licensed financial advisor in Hong Kong or any jurisdiction · Investments carry risk of total loss · Paris Trader accepts no liability.
        </span>
    </p>
    <p>
        <a href="https://t.me/algoparistrader" target="_blank">@ParisTrader on TG</a>
    </p>
</div>
""", unsafe_allow_html=True)