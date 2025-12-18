import streamlit as st
import pandas as pd
import os
import textwrap


# ==========================================
# 1. CSS 樣式 (Glassmorphism & Pro UI)
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;500;700&display=swap');

        .trade-container { font-family: 'Inter', sans-serif; }

        /* 毛玻璃卡片容器 */
        .glass-panel {
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            transition: all 0.2s ease-in-out;
            color: #e2e8f0;
            position: relative;
            overflow: hidden;
        }

        .glass-panel:hover {
            transform: translateY(-2px);
            background: rgba(30, 41, 59, 0.8);
            border-color: rgba(255, 255, 255, 0.2);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.4);
        }

        /* 狀態邊框顏色 */
        .border-profit { border-left: 4px solid #10B981; }
        .border-loss { border-left: 4px solid #EF4444; }
        .border-neutral { border-left: 4px solid #64748b; }

        /* 文字樣式 */
        .font-mono { font-family: 'Roboto Mono', monospace; }
        .text-profit { color: #34d399; font-weight: bold; text-shadow: 0 0 10px rgba(16, 185, 129, 0.3); }
        .text-loss { color: #f87171; font-weight: bold; }
        .text-gray { color: #94a3b8; font-size: 0.8rem; letter-spacing: 0.05em; text-transform: uppercase; }
        .text-white { color: #f8fafc; font-weight: 600; }

        /* 標籤 Badge */
        .badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 700;
            display: inline-block;
            margin-left: 10px;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }
        .badge-long { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .badge-short { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.2); }
        .badge-status { background: rgba(255, 255, 255, 0.1); color: #e2e8f0; border: 1px solid rgba(255, 255, 255, 0.1); font-size: 0.65rem; }

        /* 數據網格 */
        .card-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        /* 底部筆記 */
        .note-section {
            margin-top: 15px;
            background: rgba(0, 0, 0, 0.25);
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.85rem;
            color: #cbd5e1;
            line-height: 1.5;
            border-left: 2px solid #3b82f6;
        }

        /* 進度條樣式 */
        .progress-bg {
            background-color: rgba(255,255,255,0.1);
            border-radius: 9999px;
            height: 8px;
            width: 100%;
            margin-top: 10px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            border-radius: 9999px;
            transition: width 0.5s ease-in-out;
        }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 2. HTML 卡片生成器 (支援多幣種)
# ==========================================
def create_trade_card(row, currency="USD"):
    # 提取數據
    ticker = str(row['Ticker'])
    direction = str(row['Direction']).upper()
    date = str(row['EntryDate'])
    qty = float(str(row['Quantity']).replace(',', ''))
    status = str(row['Status']).upper()
    notes = str(row['Notes'])

    # 價格處理
    try:
        entry_price = float(str(row['EntryPrice']).replace(',', '').replace('$', ''))
    except:
        entry_price = 0.0

    # 幣種邏輯
    try:
        if currency == "HKD":
            # 嘗試讀取 PnLHKD，如果沒有則用 PnLUSD * 7.8
            pnl_val = float(str(row.get('PnLHKD', row.get('PnLUSD', 0) * 7.8)).replace(',', ''))
            notional_val = float(str(row.get('HKDNotional', 0)).replace(',', ''))
            curr_symbol = "HK$"
        else:
            pnl_val = float(str(row.get('PnLUSD', 0)).replace(',', ''))
            notional_val = float(str(row.get('USDNotional', 0)).replace(',', ''))
            curr_symbol = "$"
    except:
        pnl_val, notional_val = 0.0, 0.0
        curr_symbol = "$"

    # ROI 計算
    roi_percent = (pnl_val / notional_val) * 100 if notional_val != 0 else 0

    # 樣式
    if pnl_val > 0:
        border_class = "border-profit"
        pnl_text_class = "text-profit"
        pnl_sign = "+"
    elif pnl_val < 0:
        border_class = "border-loss"
        pnl_text_class = "text-loss"
        pnl_sign = ""
    else:
        border_class = "border-neutral"
        pnl_text_class = "text-white"
        pnl_sign = ""

    badge_class = "badge-long" if direction == "LONG" else "badge-short"

    # HTML 模板
    html = textwrap.dedent(f"""
    <div class="glass-panel {border_class} trade-container">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div style="display: flex; align-items: center;">
                <div style="width: 45px; height: 45px; background: rgba(255,255,255,0.05); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 1.2rem; color: #f8fafc; margin-right: 15px;">
                    {ticker[0]}
                </div>
                <div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: #f8fafc; line-height: 1.2;">
                        {ticker} 
                        <span class="badge {badge_class}">{direction}</span>
                        <span class="badge badge-status">{status}</span>
                    </div>
                    <div style="color: #64748b; font-size: 0.8rem; margin-top: 4px;">{date}</div>
                </div>
            </div>

            <div style="text-align: right;">
                <div class="{pnl_text_class} font-mono" style="font-size: 1.5rem;">
                    {pnl_sign}{curr_symbol}{pnl_val:,.2f}
                </div>
                <div class="{pnl_text_class} font-mono" style="font-size: 0.85rem; opacity: 0.8;">
                    {pnl_sign}{roi_percent:.2f}% ROI
                </div>
            </div>
        </div>

        <div class="card-grid font-mono">
            <div>
                <div class="text-gray">Entry Price</div>
                <div class="text-white">${entry_price:,.2f}</div>
            </div>
            <div>
                <div class="text-gray">Quantity</div>
                <div class="text-white">{qty:,.0f}</div>
            </div>
            <div>
                <div class="text-gray">Notional ({currency})</div>
                <div class="text-white">{curr_symbol}{notional_val:,.2f}</div>
            </div>
            <div>
                <div class="text-gray">Action</div>
                <div style="color: #60a5fa; cursor: pointer; font-size: 0.8rem;">Edit Trade &rarr;</div>
            </div>
        </div>

        <div class="note-section">
            <div style="color: #60a5fa; font-size: 0.7rem; font-weight: 700; margin-bottom: 4px; text-transform: uppercase;">Alpha Logic</div>
            {notes}
        </div>
    </div>
    """)
    return html


# ==========================================
# 3. 曝險儀表板 HTML 生成器
# ==========================================
def create_exposure_dashboard_html(total_exposure_hkd, total_capital_hkd):
    cash_hkd = total_capital_hkd - total_exposure_hkd
    invested_pct = (total_exposure_hkd / total_capital_hkd) * 100
    cash_pct = 100 - invested_pct

    bar_color = "#3b82f6"
    if invested_pct > 80:
        bar_color = "#EF4444"
    elif invested_pct > 50:
        bar_color = "#EAB308"

    html = textwrap.dedent(f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 40px; font-family: 'Inter', sans-serif;">
        <div class="glass-panel" style="margin-bottom:0; display:flex; flex-direction:column; justify-content:space-between;">
            <h2 style="color:#94a3b8; font-size:0.75rem; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; margin:0;">Total Exposure (HKD)</h2>
            <div style="margin-top:10px;">
                <span class="font-mono" style="font-size:2rem; font-weight:700; color:#f8fafc;">{invested_pct:.1f}%</span>
                <span class="font-mono" style="color:#94a3b8; font-size:0.9rem; margin-left:8px;">Invested</span>
            </div>
            <div style="color:#64748b; font-size:0.8rem; margin-top:5px;">HK${total_exposure_hkd:,.0f} / HK${total_capital_hkd:,.0f}</div>
            <div class="progress-bg">
                <div class="progress-bar" style="width: {invested_pct}%; background-color: {bar_color};"></div>
            </div>
        </div>

        <div class="glass-panel" style="margin-bottom:0; display:flex; flex-direction:column; justify-content:space-between;">
            <h2 style="color:#94a3b8; font-size:0.75rem; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; margin:0;">Cash Reserves (HKD)</h2>
            <div style="margin-top:10px;">
                <span class="font-mono" style="font-size:2rem; font-weight:700; color:#60a5fa;">{cash_pct:.1f}%</span>
                <span class="font-mono" style="color:#94a3b8; font-size:0.9rem; margin-left:8px;">Cash</span>
            </div>
            <div style="color:#64748b; font-size:0.8rem; margin-top:5px;">HK${cash_hkd:,.0f} Available</div>
            <div class="progress-bg">
                <div class="progress-bar" style="width: {cash_pct}%; background-color: #60a5fa;"></div>
            </div>
        </div>

        <div class="glass-panel" style="margin-bottom:0; display:flex; flex-direction:column; justify-content:space-between;">
            <h2 style="color:#94a3b8; font-size:0.75rem; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; margin:0;">Portfolio Status</h2>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">
                <div>
                    <div style="font-size:1.5rem; font-weight:700; color:#10B981;" class="font-mono">ACTIVE</div>
                    <div style="font-size:0.8rem; color:#64748b;">Risk Level: Moderate</div>
                </div>
                <div style="width:40px; height:40px; border-radius:50%; background:rgba(16, 185, 129, 0.2); display:flex; align-items:center; justify-content:center;">
                    <span style="color:#10B981; font-size:1.2rem;">⚡</span>
                </div>
            </div>
            <div style="margin-top:10px; font-size:0.8rem; color:#94a3b8;">
                Strategy: Macro & Flow
            </div>
        </div>
    </div>
    """)
    return html


# ==========================================
# 4. 主渲染函數
# ==========================================
def render_trade_page():
    inject_custom_css()

    st.markdown("## 💼 My Trade Journal")

    # 總本金設定
    TOTAL_CAPITAL_HKD = 1000000

    # 幣種切換器
    currency_option = st.radio("Display Currency:", ["USD", "HKD"], horizontal=True)

    # 讀取 CSV
    swing_path = os.path.join("Trade", "swing_trades.csv")
    day_path = os.path.join("Trade", "day_trades.csv")

    swing_df = pd.DataFrame()
    day_df = pd.DataFrame()

    if os.path.exists(swing_path):
        swing_df = pd.read_csv(swing_path)
    if os.path.exists(day_path):
        day_df = pd.read_csv(day_path)

    # --- 計算曝險 (基於 HKDNotional & Status=OPEN) ---
    total_exposure = 0.0

    if not swing_df.empty and 'HKDNotional' in swing_df.columns:
        open_swing = swing_df[swing_df['Status'].str.upper() == 'OPEN'].copy()
        if not open_swing.empty:
            open_swing['HKDNotional'] = pd.to_numeric(open_swing['HKDNotional'], errors='coerce').fillna(0)
            total_exposure += open_swing['HKDNotional'].sum()

    if not day_df.empty and 'HKDNotional' in day_df.columns:
        open_day = day_df[day_df['Status'].str.upper() == 'OPEN'].copy()
        if not open_day.empty:
            open_day['HKDNotional'] = pd.to_numeric(open_day['HKDNotional'], errors='coerce').fillna(0)
            total_exposure += open_day['HKDNotional'].sum()

    # 1. 渲染儀表板 (使用 st.html)
    st.html(create_exposure_dashboard_html(total_exposure, TOTAL_CAPITAL_HKD))

    # --- Tabs ---
    tab_swing, tab_day = st.tabs(["🌊 Swing Trades", "⚡ Day Trades"])

    # Swing Tab
    with tab_swing:
        if not swing_df.empty:
            # 選擇對應的 PnL 欄位
            pnl_col = 'PnLHKD' if currency_option == 'HKD' else 'PnLUSD'

            # 安全讀取 PnL 總和
            if pnl_col in swing_df.columns:
                swing_df[pnl_col] = pd.to_numeric(swing_df[pnl_col], errors='coerce').fillna(0)
                total_pnl = swing_df[pnl_col].sum()
            else:
                total_pnl = 0.0

            curr_sym = "HK$" if currency_option == 'HKD' else "$"
            st.metric(f"Total Swing PnL ({currency_option})", f"{curr_sym}{total_pnl:,.2f}")

            st.markdown("---")

            # 2. 渲染交易卡片 (使用 st.html)
            html_content = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">'
            for _, row in swing_df.iterrows():
                html_content += create_trade_card(row, currency_option)
            html_content += '</div>'

            st.html(html_content)
        else:
            st.info("No swing trades found.")

    # Day Tab
    with tab_day:
        if not day_df.empty:
            pnl_col = 'PnLHKD' if currency_option == 'HKD' else 'PnLUSD'

            if pnl_col in day_df.columns:
                day_df[pnl_col] = pd.to_numeric(day_df[pnl_col], errors='coerce').fillna(0)
                total_pnl = day_df[pnl_col].sum()
            else:
                total_pnl = 0.0

            curr_sym = "HK$" if currency_option == 'HKD' else "$"
            st.metric(f"Total Day PnL ({currency_option})", f"{curr_sym}{total_pnl:,.2f}")

            st.markdown("---")

            html_content = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">'
            for _, row in day_df.iterrows():
                html_content += create_trade_card(row, currency_option)
            html_content += '</div>'

            st.html(html_content)
        else:
            st.info("No day trades found.")