import streamlit as st
from streamlit_option_menu import option_menu
import streamlit.components.v1 as components
import os
import sys
import glob
import time

# Add Trade folder path
sys.path.append('Trade')
try:
    from Trade import trade_app
except ImportError:
    pass


# ==========================================
# 🔐 Security Login System
# ==========================================
def login_system():
    """
    Simple login verification: Checks if Email is in whitelist + verifies universal password
    """
    if "authentication_status" in st.session_state and st.session_state["authentication_status"]:
        return True

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
            try:
                valid_emails = st.secrets["allowed_users"]["emails"]
                correct_password = st.secrets["access_password"]
            except FileNotFoundError:
                st.error("⚠️ System Error: Secrets not set (Please contact admin)")
                return False

            if email_input in valid_emails and password_input == correct_password:
                st.session_state["authentication_status"] = True
                st.session_state["user_email"] = email_input
                st.success("Login Successful! Redirecting...")
                time.sleep(1)
                st.rerun()
            else:
                st.session_state["authentication_status"] = False
                st.error("❌ Access Denied: Email not in whitelist or wrong password.")

    return False


# --- Main Program Logic ---
# Uncomment to enable login
# if not login_system():
#    st.stop()

# ==========================================
# 1. Page Configuration
# ==========================================
st.set_page_config(
    page_title="ParisTrader - Quant Trading & Market Analysis | 2026香港投資銀行學習",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. Custom CSS
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;500;700&display=swap');

    .stApp {
        background: transparent !important;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', 'Microsoft JhengHei', sans-serif;
        color: #e2e8f0;
    }

    @media (min-width: 768.1px) {
        header { visibility: hidden !important; }
        [data-testid="stSidebarCollapseButton"] { display: none !important; }
        section[data-testid="stSidebar"] button { display: none !important; }
        [data-testid="stToolbar"], [data-testid="stHeaderActionElements"] { visibility: hidden !important; display: none !important; }
        #MainMenu { visibility: hidden !important; display: none !important; }
    }

    @media (max-width: 768px) {
        header { visibility: visible !important; background: transparent !important; }
        header button[kind="header"] {
            background-color: rgba(17, 24, 39, 0.6) !important;
            color: white !important;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
        }
        .block-container {
            padding-top: 3rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        h1 { font-size: 1.8rem !important; }
        h2 { font-size: 1.5rem !important; }
        h3 { font-size: 1.2rem !important; }
    }

    footer { visibility: hidden !important; display: none !important; }
    div[data-testid="stDecoration"] { display: none !important; }

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

    section[data-testid="stSidebar"] {
        background-color: #111827; 
        border-right: 1px solid #374151;
        z-index: 999999 !important;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div {
        color: #F3F4F6 !important;
    }

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

def load_weekly_analysis():
    file_path = os.path.join("WeeklyContent", "latest_analysis.md")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        return "⚠️ Weekly analysis not uploaded yet (File not found: WeeklyContent/latest_analysis.md)"


def load_html_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        return f"<div style='padding:20px; color:red;'>⚠️ File not found: {file_path}</div>"


import os
import streamlit.components.v1 as components


def load_stock_dna_with_injection():
    # 1. Get absolute paths to ensure it works from any directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, "FamaFrench", "index.html")
    csv_factor_path = os.path.join(current_dir, "FamaFrench", "stock_factor_data.csv")
    csv_returns_path = os.path.join(current_dir, "FamaFrench", "stock_returns_data.csv")

    if not os.path.exists(html_path):
        return f"<div style='color:red'>HTML not found: {html_path}</div>"

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # ---------------------------------------------------------
    # 1. Inject Factor Data (Your original logic)
    # ---------------------------------------------------------
    if os.path.exists(csv_factor_path):
        with open(csv_factor_path, 'r', encoding='utf-8') as f:
            csv_data = f.read()
            # Clean up backticks just in case
            csv_data = csv_data.replace('`', '')

        # JS to inject: Create variable -> Parse variable -> Disable download
        injection_js = f"""
        var csvData = `{csv_data}`;
        Papa.parse(csvData, {{
            download: false, 
        """

        target_str = 'Papa.parse("stock_factor_data.csv", {'
        if target_str in html_content:
            html_content = html_content.replace(target_str, injection_js)

    # ---------------------------------------------------------
    # 2. Inject Returns Data (The NEW addition)
    # ---------------------------------------------------------
    if os.path.exists(csv_returns_path):
        with open(csv_returns_path, 'r', encoding='utf-8') as f:
            returns_data = f.read()
            returns_data = returns_data.replace('`', '')

        # JS to inject: Use a DIFFERENT variable name (returnsCSVData)
        injection_js_ret = f"""
        var returnsCSVData = `{returns_data}`;
        Papa.parse(returnsCSVData, {{
            download: false, 
        """

        target_str_ret = 'Papa.parse("stock_returns_data.csv", {'
        if target_str_ret in html_content:
            html_content = html_content.replace(target_str_ret, injection_js_ret)

    # ---------------------------------------------------------
    # 3. Global Cleanup
    # ---------------------------------------------------------
    # Since we injected 'download: false', we remove the original 'download: true'
    # to avoid syntax errors or conflicting keys in the JS object.
    html_content = html_content.replace('download: true,', '')

    return html_content


def get_latest_file_content(folder_path, pattern="*.html"):
    if not os.path.exists(folder_path):
        return None, f"Directory not found: {folder_path}"

    search_pattern = os.path.join(folder_path, pattern)
    list_of_files = glob.glob(search_pattern)

    if not list_of_files:
        return None, f"No files found matching {pattern}."

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

    # 4. Create Navigation Menu
    selected_nav = option_menu(
        menu_title="Navigation",
        options=[
            "Home", "Market Intelligence", "Stock", "Option",
            "Future", "My Trade", "MT5 EA", "Legal", "Resources", "Promotion"
        ],
        icons=[
            "house", "globe", "search", "layers",
            "graph-up-arrow", "briefcase", "robot", "file-text", "collection", "gift"
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

    # 在您的 option_menu 下方加入這段，將選單同步到網址參數
    if selected_nav:
        st.query_params["page"] = selected_nav

    # 程式啟動時，讀取參數來決定預設頁面
    default_index = 0
    if "page" in st.query_params:
        try:
            # 找出該參數對應的 index
            # (這裡需要您維護一個選單 list 來查找 index)
            pass
        except:
            pass


    # Default routing: Assume target is what is clicked in main sidebar
    target_page = selected_nav

    # --- Sub-menu Logic ---
    if selected_nav == "Market Intelligence":
        st.caption("MARKET MODULES")
        target_page = option_menu(
            # [NEW] Added Economic Calendar to options
            menu_title=None,
            options=["Market Risk", "Market Breadth", "Economic Calendar"],
            icons=["activity", "bar-chart-line", "calendar-event"],
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    elif selected_nav == "Stock":
        st.caption("STOCK RESEARCH")
        # [UPDATE] Added "Short Squeeze"
        target_page = option_menu(
            menu_title=None,
            options=["Earnings", "Stock DNA", "Thematic Basket", "ETF Smart Money", "Insider Trading",
                     "Short Squeeze",
                     "Volatility Target", "Industry Sector Heatmap"],
            icons=["cash-coin", "radar", "basket", "graph-up-arrow", "people", "lightning-charge", "bullseye",
                   "grid-3x3"],
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    elif selected_nav == "Future":
        st.caption("FUTURES & TRENDS")
        target_page = option_menu(
            menu_title=None,
            options=["Volume Profile", "Intraday Volatility", "HSI CBBC Ladder"],
            icons=["bar-chart-steps", "lightning-charge", "distribute-vertical"],
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    elif selected_nav == "Option":
        st.caption("DERIVATIVES ANALYTICS")
        target_page = option_menu(
            menu_title=None,
            options=["US Option", "HK Option"],
            icons=["currency-dollar", "globe-asia-australia"],  # US用美元符號, HK用亞洲地球符號
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    elif selected_nav == "MT5 EA":
        st.caption("AUTOMATED TRADING")
        target_page = option_menu(
            menu_title=None,
            options=["EA Introduction", "Daily Report"],
            icons=["robot", "file-earmark-bar-graph"],
            styles={
                "container": {"padding": "0!important", "background-color": "rgba(255,255,255,0.03)",
                              "border-radius": "10px"},
                "nav-link": {"font-size": "14px", "margin": "3px", "--hover-color": "#374151"},
                "nav-link-selected": {"background-color": "#4B5563"},
            }
        )

    st.markdown("---")
    st.link_button("✈️VIP Channel", "https://parisprogram.uk/", use_container_width=True)


# ==========================================
# 🔒 權限控制中心 (Security Check)
# ==========================================
# 定義需要鎖定（強制登入）的頁面名稱
# 這裡包含：My Trade, 指定的 Stock 功能, 以及所有 Option 和 Future 的子頁面
locked_pages = [
    "My Trade",
    "Stock DNA",
    "ETF Smart Money",
    "Insider Trading",
    "Short Squeeze",
    "Volatility Target",
    # Option 的子頁面
    "US Option", "HK Option",
    # Future 的子頁面
    "Volume Profile", "Intraday Volatility", "HSI CBBC Ladder"
]

# 邏輯：如果當前目標頁面在鎖定清單中，且未登入，則呼叫 login_system() 並停止執行
if target_page in locked_pages:
    if not login_system():
        st.stop()



# --- Content Routing (Based on target_page) ---
# [PAGE] HOME
if target_page == "Home":
    col_main, col_profile = st.columns([0.7, 0.3], gap="large")

    with col_main:
        st.markdown("""
        <h1 style='color:white;'>前Ibanker開發-香港首個機構級數據</h1>
        <h3 style='color:#94a3b8;'>美股分析|期權策略|期貨自動交易EA Algo</h3>
        <p style='font-size: 1.1em; color: #64748b;'>
        2026散戶黑科技,你不是只看圖表交易吧?!
        </p>
                <p style='font-size: 1.1em; color: #64748b;'>
        有志加入投行工作,或成為持續盈利交易員必備學習資源平台!
        </p>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # [RESTORED] TradingView Widget
        components.html("""
        <div class="tradingview-widget-container">
          <div class="tradingview-widget-container__widget"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
          {
          "symbols": [
            {"proName": "FOREXCOM:SPXUSD", "title": "S&P 500"},
            {"proName": "FOREXCOM:NSXUSD", "title": "US 100"},
            {"description": "Gold", "proName": "OANDA:XAUUSD"}
          ],
          "showSymbolLogo": true,
          "colorTheme": "dark",
          "isTransparent": true,
          "displayMode": "adaptive",
          "locale": "en"
          }
          </script>
        </div>
        """, height=100)

        st.markdown("<br>", unsafe_allow_html=True)

        # ==========================================
        # 🆕 新增功能：網站教學影片 & 分析文章連結
        # ==========================================
        st.subheader("📺 網站使用教學")
        st.video("https://www.youtube.com/watch?v=HCR5DDy8Nb0")

        st.markdown("<br>", unsafe_allow_html=True)

        # 下周大市分析連結按鈕
        st.link_button(
            label="📊 點擊閱讀：下周大市分析 (Weekly Market Analysis)",
            url="https://parisprogram.uk/zh/member/post/RPT-20260103199214386?hash=df6a6830b6176c7ea95cc12ebe1c8de50a2b1f90fa8a79ddbbb5be18dcd92c39",
            type="primary",  # 使用主要按鈕樣式使其更顯眼
            use_container_width=True
        )

        st.markdown("---")
        # ==========================================

        st.subheader("🧠 Week Ahead")

        with st.container():
            analysis_content = load_weekly_analysis()
            with st.expander("📖 Click to expand/collapse full analysis", expanded=True):
                st.markdown(analysis_content)

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
                Focusing on quantitative factor mining and algorithmic trading. Specialized in transforming complex financial models into executable trading strategies. Providing TradingView indicators and backtesting.
                <br><br>
                <b>Main Strategies:</b><br>
                • Multi-Factor Long/Short<br>
                • Future Scapling on HSI/NQ/GC <br>
                • Unusual Options Activity Trading Strategies on U.S. market<br>
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
        components.html(html_content, height=2500, scrolling=True)
    else:
        st.warning("⚠️ No dashboard files found.")
        st.error(f"Error: {filename}")

# [PAGE] Market Risk
elif target_page == "Market Risk":
    st.title("⚠️ Market Implied Risk")
    path = "ImpliedParameters"

    html_content, filename = get_latest_file_content(path)

    if html_content:
        st.caption(f"Displaying Report: {filename}")
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
        components.html(html_content, height=2200, scrolling=True)
    else:
        st.warning("⚠️ No risk reports found.")
        st.info("Please ensure `ImpliedParameters/implied_params_*.html` exists.")

# [PAGE] Market Breadth
elif target_page == "Market Breadth":
    st.title("🌊 Market Breadth")

    # [修正] 路徑指向新的子資料夾 MarketBreadth
    path = os.path.join("MarketDashboard", "MarketBreadth")

    # [修正] 自動讀取該資料夾內最新的 html 檔案 (market_breadth_*.html)
    html_content, filename = get_latest_file_content(path, "market_breadth_*.html")

    if html_content:
        st.caption(f"Displaying Report: {filename}")
        components.html(html_content, height=2200, scrolling=True)
    else:
        st.warning("⚠️ Market Breadth report not found.")
        st.info(f"Please ensure `{path}` contains `market_breadth_*.html` files.")

# [PAGE] Economic Calendar (NEW)
elif target_page == "Economic Calendar":
    st.title("📅 Weekly Economic Calendar")

    # Points to EconomicCalendar folder
    #path = "EconomicCalendar"
    path = os.path.join("MarketDashboard", "EconomicCalendar")

    # Matches the prefix defined in the python script: calendar_report_
    html_content, filename = get_latest_file_content(path, "calendar_report_*.html")

    if html_content:
        st.caption(f"📅 Report Generated: {filename}")
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ No Economic Calendar report found.")
        st.info("Please run `python macro_dashboard.py` to generate the latest report.")

# [PAGE] Industry Sector Heatmap
elif target_page == "Industry Sector Heatmap":
    st.title("🔥 Industry Sector Heatmap")
    st.caption("Daily Return Heatmap (Last 20 Days)")

    path = "MarketDashboard"
    pattern = "sector_etf_heatmap_*.html"
    html_content, filename = get_latest_file_content(path, pattern)

    if html_content:
        st.caption(f"Displaying Report: {filename}")
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ Sector Heatmap not found.")
        st.info(f"Please ensure `{path}/{pattern}` exists.")

# [PAGE] Earnings
elif target_page == "Earnings":
    st.title("📅 Earnings Calendar Analysis")

    # Use get_latest_file_content to automatically fetch the latest html
    path = "Earnings"
    html_content, filename = get_latest_file_content(path)

    if html_content:
        st.caption(f"Displaying Report: {filename}")
        components.html(html_content, height=2500, scrolling=True)
    else:
        st.warning("⚠️ No earnings reports found.")
        st.info("Please ensure there is an `Earnings` folder in the root directory containing .html files.")

# [PAGE] Stock DNA
elif target_page == "Stock DNA":
    st.title("🧬 Stock Factor DNA")
    html_content = load_stock_dna_with_injection()
    if html_content and "HTML not found" not in html_content:
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.error("FamaFrench/index.html not found")



# [PAGE] Thematic Basket
elif target_page == "Thematic Basket":
    st.title("🧺 Thematic Basket Analysis")
    path = "ThematicBasket"
    html_content, filename = get_latest_file_content(path, "elite_signal_dashboard_*.html")

    if html_content:
        st.caption(f"📅 Strategy Report: {filename}")
        components.html(html_content, height=6000, scrolling=True)
    else:
        st.warning("⚠️ No basket reports found.")
        st.info(f"Checking path: {os.path.abspath(path)}")

# [PAGE] ETF Smart Money
elif target_page == "ETF Smart Money":
    st.title("🚀 ETF Smart Money Tracker")
    st.caption("Tracking Leveraged ETF Relative Volume Spikes")

    path = "xETF"
    html_content, filename = get_latest_file_content(path, "ETF_Smart_Money_Report_*.html")

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No ETF Smart Money reports found.")
        st.info(f"Please ensure `{path}` folder exists and contains `ETF_Smart_Money_Report_*.html` files.")

# [PAGE] Insider Trading
elif target_page == "Insider Trading":
    st.title("🕴️ Insider Trading Activity")
    st.caption("Daily Cluster Buys & Significant Insider Transactions")

    path = "Insider"
    html_content, filename = get_latest_file_content(path, "Insider_Trading_Report_*.html")

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No Insider Trading reports found.")
        st.info(f"Please ensure `{path}` folder exists and contains `Insider_Trading_Report_*.html` files.")

# [PAGE] Short Squeeze (NEW)
elif target_page == "Short Squeeze":
    st.title("⚡ Short Squeeze Scanner")
    st.caption("Retail Hype & High Short Interest Candidates")

    path = "Short_squeeze"
    # Match the filename format from your Python script: Short_squeeze_YYYYMMDD_HHMMSS.html
    html_content, filename = get_latest_file_content(path, "Short_squeeze_*.html")

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No Short Squeeze reports found.")
        st.info(f"Please ensure `{path}` folder exists and contains `Short_squeeze_*.html` files.")


# [PAGE] Reddit Sentiment (NEW)
elif target_page == "Reddit Sentiment":
    # st.title("🤖 Reddit Sentiment Scanner")
    path = "Rddt"
    # Assuming your script outputs files like reddit_scanner_YYYY-MM-DD.html
    html_content, filename = get_latest_file_content(path, "reddit_scanner_*.html")

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No Reddit reports found.")
        st.info(f"Please ensure `{path}` folder exists and contains `reddit_scanner_*.html` files.")

# [PAGE] Volatility Target
elif target_page == "Volatility Target":
    st.title("📉 Volatility Target Strategy")
    path = "VolTarget"
    html_content, filename = get_latest_file_content(path, "vol_tool_*.html")

    if html_content:
        st.caption(f"Displaying Report: {filename}")
        components.html(html_content, height=1500, scrolling=True)
    else:
        st.warning("⚠️ Volatility Tool not found.")
        st.info("Please ensure `vol_tool_*.html` exists in the `VolTarget` folder.")

# ==========================================
# [PAGE] US Option (原有的 Option Strike Analysis)
# ==========================================
elif target_page == "US Option":
    st.title("🇺🇸 US Option Strike Analysis")
    st.caption("Tracking Unusual Options Activity & Gamma Levels")

    # 設定資料夾路徑
    path = "Option"

    # 設定 US Option 的檔案搜尋模式
    search_pattern = "option_strike_analysis_*.html"

    html_content, filename = get_latest_file_content(path, search_pattern)

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No US Option reports found.")
        st.info(f"Please ensure `{path}` folder exists and contains `{search_pattern}` files.")

# ==========================================
# [PAGE] HK Option (新的 Market Analysis v6)
# ==========================================
elif target_page == "HK Option":
    st.title("🇭🇰 HK Option Market Analysis")
    st.caption("Market Scanner, Stock Ranking & Heatmaps")

    # 設定資料夾路徑 (假設 HK 檔案也在 Option 資料夾內)
    path = "Option"

    # 設定 HK Option 的檔案搜尋模式 (v6 版本)
    search_pattern = "HK_Option_Market_Analysis_v6_*.html"

    html_content, filename = get_latest_file_content(path, search_pattern)

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No HK Option reports found.")
        st.info(f"Please ensure `{path}` folder exists and contains `{search_pattern}` files.")

# [PAGE] Volume Profile
elif target_page == "Volume Profile":
    st.title("📊 Volume Profile Analysis")
    path = "VP"
    html_content, filename = get_latest_file_content(path)

    if html_content:
        st.caption(f"Displaying Report: {filename}")
        components.html(html_content, height=1000, scrolling=True)
    else:
        st.warning("⚠️ 尚未部署 Volume Profile 模組 (VP 資料夾為空)")

# [PAGE] Future -> Intraday Volatility
elif target_page == "Intraday Volatility":
    st.title("⚡ Intraday Volatility Analysis")
    html_path = os.path.join("MarketDashboard", "Intraday_Volatility.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ 找不到 Intraday Volatility 報告")
        st.info(f"請確認檔案 `{html_path}` 是否存在。")

# [PAGE] Future -> HSI CBBC Ladder
elif target_page == "HSI CBBC Ladder":
    st.title("🐻 HSI CBBC Heavy Zone (牛熊重貨區)")
    html_path = os.path.join("MarketDashboard", "HSI_CBBC_Ladder.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ 尚未生成牛熊證分佈報告")
        st.info(f"請確認檔案 `{html_path}` 是否存在。")

# [PAGE] My Trade
elif target_page == "My Trade":
    # st.title("💼 My Trade Journal") # Title is already inside the HTML

    path = "Trade"
    # Search for files matching the timestamp pattern generated by your script
    html_content, filename = get_latest_file_content(path, "trade_record_*.html")

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=1200, scrolling=True)
    else:
        st.warning("⚠️ Trade Record HTML not found.")
        st.info(
            "Please verify that the GitHub Action has run successfully and generated a `trade_record_*.html` file in the `Trade` folder.")

# [PAGE] MT5 EA - Introduction
elif target_page == "EA Introduction":
    st.title("🤖 MT5 Expert Advisor")
    html_path = os.path.join("MT5EA", "ea_marketing.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=3000, scrolling=True)
    else:
        st.warning("⚠️ No marketing content found.")
        st.info("Please ensure `MT5EA/ea_marketing.html` exists.")

# [PAGE] MT5 EA - Daily Report (NEW)
elif target_page == "Daily Report":
    st.title("📄 Algo Daily Report")
    path = "MT5EA"
    html_content, filename = get_latest_file_content(path, "DailyReport_*.html")

    if html_content:
        st.caption(f"📅 Report Date: {filename}")
        components.html(html_content, height=2000, scrolling=True)
    else:
        st.warning("⚠️ No Daily Reports found.")
        st.info("Please ensure files named `DailyReport_*.html` exist in `MT5EA` folder.")

# [PAGE] LEGAL
elif target_page == "Legal":
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

# [PAGE] Resources
elif target_page == "Resources":
    st.title("🔗 Trading Resources")
    html_path = os.path.join("Resources", "external_links.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=1000, scrolling=True)
    else:
        st.warning("⚠️ Resources file not found.")
        st.info(f"Please ensure `{html_path}` exists.")

# [PAGE] Promotion (NEW)
elif target_page == "Promotion":
    html_path = os.path.join("Promotion", "promo.html")
    html_content = load_html_file(html_path)
    if html_content and "File not found" not in html_content:
        components.html(html_content, height=1600, scrolling=True)
    else:
        st.warning("⚠️ Promotion page not found.")
        st.info(f"Please ensure `{html_path}` exists.")

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