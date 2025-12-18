"""
期权数据分析脚本

1. 输入：
   - CSV文件路径（包含期权交易数据）
   - 输入字段（期望在CSV中存在，部分可选）：
     * trade_date: 交易日期
     * ul: 标的资产代码
     * expiration 或 contract_s_expiration: 到期日期
     * strike: 执行价格
     * ul_price: 标的资产价格
     * last_price: 期权最后成交价
     * volume: 交易量
     * open_interest: 持仓量
     * opt_multiplier: 期权乘数（可缺省，默认100）
     * days_to_expiration: 到期天数（可选）
     * option_premium: 期权溢价（可选，若不存在则自动计算）
     * premium_threshold: 溢价阈值（可选，若不存在则基于market_cap计算）
     * market_cap: 市值（可选，用于计算premium_threshold）
     * moneyness: 价内/价外状态（例如OTM/ATM/ITM）
     * contract_type: 合约类型（CALL或PUT）

2. 过滤条件：
   - 只处理满足以下所有条件的数据：
     * abnormal_volume = True（即 volume > open_interest * 2 且 option_premium > premium_threshold 且 dte <= 35 且 moneyness == 'OTM'）
     * open_interest > 0（排除持仓量为0的数据）
   - premium_threshold基于market_cap计算：如果market_cap < 10e9、< 20e9或其他情况，均使用300000作为阈值

3. 计算公式：
   - dte（到期天数）：优先使用days_to_expiration字段，否则用expiration_dt - trade_date_dt计算自然日差（不小于0）
   - option_premium（期权溢价）：如果不存在，则计算为 last_price * volume * opt_multiplier
   - premium_threshold（溢价阈值）：如果不存在，基于market_cap计算（默认300000）
   - otm_pct（OTM百分比）：
     * Call期权：OTM是strike > ul_price，otm_pct = (strike - ul_price) / ul_price * 100
     * Put期权：OTM是strike < ul_price，otm_pct = (ul_price - strike) / ul_price * 100
   - premium_musd（溢价百万美元）：(last_price * volume * opt_multiplier) / 1e6
   - vol_oi（交易量持仓比）：volume / open_interest（当open_interest为0时设为NaN）
   - abnormal_volume（异常交易量标记）：满足 volume > open_interest * 2 且 option_premium > premium_threshold 且 dte <= 35 且 moneyness == 'OTM' 的为True

4. 输出：
   - 输出CSV文件包含以下字段：
     * trade_date: 交易日期
     * ul: 标的资产代码
     * expiration: 到期日期
     * strike: 执行价格
     * ul_price: 标的资产价格
     * last_price: 期权最后成交价
     * volume: 交易量
     * open_interest: 持仓量
     * otm_pct: OTM百分比
     * premium_musd: 溢价（百万美元）
     * dte: 到期天数（自然日，非负，整数）
     * vol_oi: 交易量持仓比
     * qc_flags: 质检标签（以分号分隔）
   - 生成交互式HTML网页（包含图表和数据表格）
"""

import math
import warnings
from datetime import datetime
from typing import Optional, Tuple
import os
import json

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

try:
	import plotly.graph_objects as go
	import plotly.express as px
	PLOTLY_AVAILABLE = True
except ImportError:
	PLOTLY_AVAILABLE = False
	print("Warning: Plotly not available. Install with 'pip install plotly' for interactive web visualization.")

# Ignore FutureWarning
warnings.filterwarnings('ignore', category=FutureWarning)

TENOR = 35  # Tenor for option selection

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DEFAULT_INPUT_CSV = os.path.join(BASE_DIR, "OtmPremium_db.csv")


def ensure_output_dir(dir_path: Optional[str] = None) -> str:
	"""
	Ensure the target output directory exists and return its absolute path.
	If dir_path is None, use the module-level DEFAULT_OUTPUT_DIR.
	"""
	target_dir = dir_path or DEFAULT_OUTPUT_DIR
	abs_dir = os.path.abspath(target_dir)
	os.makedirs(abs_dir, exist_ok=True)
	return abs_dir


def resolve_output_path(user_path: Optional[str], default_filename: str) -> str:
	"""
	Return an absolute file path for outputs, creating parent directories as needed.
	If user_path is provided, respect it; otherwise place the file inside DEFAULT_OUTPUT_DIR.
	"""
	if user_path:
		abs_path = os.path.abspath(user_path)
		parent_dir = os.path.dirname(abs_path)
		if parent_dir:
			os.makedirs(parent_dir, exist_ok=True)
		else:
			os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
			abs_path = os.path.join(DEFAULT_OUTPUT_DIR, os.path.basename(abs_path))
		return abs_path
	output_dir = ensure_output_dir()
	return os.path.join(output_dir, default_filename)


def compute_metrics_and_qc(
	input_csv_path: str,
	output_csv_path: Optional[str] = None,
	default_opt_multiplier: int = 100,
)	-> Tuple[pd.DataFrame, Optional[pd.DataFrame], Optional[pd.DataFrame]]:
	

	df = pd.read_csv(input_csv_path)

	# Handle column name compatibility
	if "contract_s_expiration" in df.columns and "expiration" not in df.columns:
		df = df.rename(columns={"contract_s_expiration": "expiration"})
	if "open_inter" in df.columns and "open_interest" not in df.columns:
		df = df.rename(columns={"open_inter": "open_interest"})

	# Parse dates
	def _to_date(s: pd.Series) -> pd.Series:
		return pd.to_datetime(s, errors="coerce").dt.tz_localize(None)

	df["trade_date_dt"] = _to_date(df.get("trade_date"))
	df["expiration_dt"] = _to_date(df.get("expiration"))

	# DTE: prefer days_to_expiration field, otherwise calculate date difference (calendar days, not less than 0)
	if "days_to_expiration" in df.columns:
		df["dte_calc"] = pd.to_numeric(df["days_to_expiration"], errors="coerce")
	else:
		df["dte_calc"] = pd.NA

	mask_need_diff = df["dte_calc"].isna()
	if mask_need_diff.any():
		date_diff = (df.loc[mask_need_diff, "expiration_dt"] - df.loc[mask_need_diff, "trade_date_dt"]).dt.days
		df.loc[mask_need_diff, "dte_calc"] = date_diff

	# Normalize DTE to be non-negative
	df["dte"] = pd.to_numeric(df["dte_calc"], errors="coerce").clip(lower=0)

	# Set default opt_multiplier
	if "opt_multiplier" not in df.columns:
		df["opt_multiplier"] = default_opt_multiplier
	else:
		df["opt_multiplier"] = pd.to_numeric(df["opt_multiplier"], errors="coerce").fillna(default_opt_multiplier)

	# Convert key inputs to numeric
	for col in ["strike", "ul_price", "last_price", "volume", "open_interest", "option_premium", "premium_threshold", "market_cap"]:
		if col in df.columns:
			df[col] = pd.to_numeric(df[col], errors="coerce")

	# Calculate option_premium (if missing)
	if "option_premium" not in df.columns:
		df["option_premium"] = df["last_price"] * df["volume"] * df["opt_multiplier"]

	# First, apply rules to rows with moneyness=UNKNOWN:
	# - Put with ul_price > strike -> OTM
	# - Call with strike > ul_price -> OTM
	if "moneyness" in df.columns and "contract_type" in df.columns:
		mny_upper = df["moneyness"].astype(str).str.upper()
		# Include common spellings: UNKNOWN/UNKONWN
		is_unknown = mny_upper.isin(["UNKNOWN", "UNKONWN", "UNK", "NA", "NAN", "", "NONE"])
		ct_lower = df["contract_type"].astype(str).str.lower()
		put_otm = (ct_lower == "put") & (df["ul_price"] > df["strike"]) 
		call_otm = (ct_lower == "call") & (df["strike"] > df["ul_price"]) 
		infer_otm = is_unknown & (put_otm | call_otm)
		df.loc[infer_otm, "moneyness"] = "OTM"

	# Calculate premium_threshold (based on market_cap, consistent with opt_mon_ahs_new.py)
	if "premium_threshold" not in df.columns:
		if "market_cap" in df.columns:
			df["premium_threshold"] = df["market_cap"].apply(lambda x: 300000 if x < 10e9 else 300000 if x < 20e9 else 300000)
		else:
			# If market_cap doesn't exist, use default value
			df["premium_threshold"] = 300000

	# Calculate abnormal_volume
	if "moneyness" in df.columns:
		is_otm = df["moneyness"].astype(str).str.upper() == 'OTM'
	else:
		is_otm = pd.Series(False, index=df.index)
	
	# Use days_to_expiration or dte (consistent with opt_mon_ahs_new.py, use days_to_expiration)
	dte_col = "days_to_expiration" if "days_to_expiration" in df.columns else "dte"
	
	df["abnormal_volume"] = (
		(df["volume"] > df["open_interest"] * 2) &
		(df["option_premium"] > df["premium_threshold"]) &
		(df[dte_col] <= TENOR) &
		is_otm
	)

	# OTM% (calculated for both Call and Put)
	contract_type_col = "contract_type" if "contract_type" in df.columns else None
	if contract_type_col:
		is_call = df[contract_type_col].str.lower().eq("call")
		is_put = df[contract_type_col].str.lower().eq("put")
	else:
		is_call = pd.Series(False, index=df.index)
		is_put = pd.Series(False, index=df.index)
	
	with pd.option_context("mode.use_inf_as_na", True):
		# Call: OTM is strike > ul_price, otm_pct = (strike - ul_price) / ul_price * 100
		# Put: OTM is strike < ul_price, otm_pct = (ul_price - strike) / ul_price * 100
		call_otm_pct = ((df["strike"] - df["ul_price"]) / df["ul_price"] * 100.0).where(is_call)
		put_otm_pct = ((df["ul_price"] - df["strike"]) / df["ul_price"] * 100.0).where(is_put)
		df["otm_pct"] = call_otm_pct.fillna(0) + put_otm_pct.fillna(0)
		# If neither Call nor Put, set to NaN
		df["otm_pct"] = df["otm_pct"].where(is_call | is_put)

	# Premium (in million USD)
	premium_usd = df["last_price"] * df["volume"] * df["opt_multiplier"]
	df["premium_musd"] = premium_usd / 1e6

	# vol/oi
	df["vol_oi"] = df["volume"] / df["open_interest"].replace({0: pd.NA})

	# QC flags
	qc_flags = []
	for idx, row in df.iterrows():
		flags = []
		# Set default multiplier
		if math.isclose(row.get("opt_multiplier", float("nan")), default_opt_multiplier) and "opt_multiplier" in df.columns and pd.isna(df.loc[idx, "opt_multiplier"]):
			flags.append("opt_multiplier_missing_defaulted")
		# Premium cross-validation (if option_premium exists and is comparable)
		option_premium = row.get("option_premium")
		computed_premium = row.get("last_price") * row.get("volume") * row.get("opt_multiplier")
		if pd.notna(option_premium) and pd.notna(computed_premium):
			# Allow tolerance of the larger of 1% or $10
			abs_tol = max(10.0, 0.01 * computed_premium)
			if not (abs(option_premium - computed_premium) <= abs_tol):
				flags.append("premium_mismatch")
		# Do not output negative_dte_input; expiration date equal to trade date (dte=0) is considered normal
		# Missing required fields
		for req in ("strike", "ul_price", "last_price", "volume", "open_interest"):
			if pd.isna(row.get(req)):
				flags.append(f"missing_{req}")
		qc_flags.append(";".join(flags))

	df["qc_flags"] = qc_flags

	# Filter: only process data where abnormal_volume is True, and exclude data where open_interest is 0
	has_valid_oi = df["open_interest"] > 0
	df_filtered = df.loc[(df["abnormal_volume"] == True) & has_valid_oi].copy()

	# Keep only output-related columns (include original primary key columns if they exist for tracking)
	# Note: abnormal_volume, contract_type, opt_multiplier, moneyness are not output, but contract_type needs to be kept for filtering
	output_cols = [
		"trade_date",
		"ul",
		"expiration",
		"strike",
		"ul_price",
		"last_price",
		"volume",
		"open_interest",
		"otm_pct",
		"premium_musd",
		"dte",
		"vol_oi",
	]
	# Ensure abnormal_volume is not in output columns
	if "abnormal_volume" in output_cols:
		output_cols.remove("abnormal_volume")
	# Ensure contract_type is included for grouping (but not output)
	if "contract_type" in df_filtered.columns:
		# Temporarily save contract_type for filtering
		contract_type_temp = df_filtered["contract_type"].copy()
	else:
		contract_type_temp = None
	
	final_cols = [c for c in output_cols if c in df_filtered.columns]
	result = df_filtered[final_cols].reset_index(drop=True)
	
	# Temporarily add contract_type to result for filtering (will be removed after filtering)
	if contract_type_temp is not None:
		result["contract_type"] = contract_type_temp.values

	# Filter top 20 for CALL and PUT (by premium_musd)
	call_top20_df = None
	put_top20_df = None
	
	if "contract_type" in result.columns and "premium_musd" in result.columns and "ul" in result.columns and "trade_date" in result.columns:
		# Parse trade_date as date type for sorting
		result["trade_date_parsed"] = pd.to_datetime(result["trade_date"], errors="coerce")
		
		# Process CALL and PUT separately
		for contract_type in ["CALL", "PUT"]:
			# Filter data for corresponding type
			type_mask = result["contract_type"].astype(str).str.upper() == contract_type
			type_df = result[type_mask].copy()
			
			if len(type_df) > 0:
				# If an underlying has multiple dates, keep the record with the latest date first
				type_df = type_df.sort_values(["ul", "trade_date_parsed"], ascending=[True, False])
				type_df = type_df.drop_duplicates(subset=["ul"], keep="first")
				
				# Sort by premium_musd in descending order, take top 20
				type_df = type_df.sort_values("premium_musd", ascending=False).head(20)
				
				# Remove temporary columns
				if "trade_date_parsed" in type_df.columns:
					type_df = type_df.drop(columns=["trade_date_parsed"])
				
				# Remove contract_type, abnormal_volume, opt_multiplier, moneyness (if they exist)
				columns_to_drop = ["contract_type", "abnormal_volume", "opt_multiplier", "moneyness"]
				type_df = type_df.drop(columns=[col for col in columns_to_drop if col in type_df.columns])
				
				# Convert dte column to integer
				if "dte" in type_df.columns:
					type_df["dte"] = type_df["dte"].fillna(0).astype(int)
				
				# Round other numeric columns to 2 decimal places
				for col in type_df.columns:
					if col != "dte" and type_df[col].dtype in ['float64', 'float32']:
						type_df[col] = type_df[col].round(2)
				
				# Store top 20 data
				if contract_type == "CALL":
					call_top20_df = type_df
				else:
					put_top20_df = type_df

	return result, call_top20_df, put_top20_df


def plot_otm_vs_premium(call_csv_path: str = None, put_csv_path: str = None, output_dir: str = None):
	"""
	Generate scatter plots for CALL and PUT top 20 data
	
	Parameters:
	- call_csv_path: Path to CALL top 20 CSV file
	- put_csv_path: Path to PUT top 20 CSV file
	- output_dir: Output image directory (if None, use CSV file directory)
	"""
	if call_csv_path is None and put_csv_path is None:
		print("Warning: No CSV files provided for plotting")
		return
	
	output_dir_path = ensure_output_dir(output_dir)
	
	# Set Chinese font (if Chinese display is needed)
	plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
	plt.rcParams['axes.unicode_minus'] = False
	
	for contract_type, csv_path in [("CALL", call_csv_path), ("PUT", put_csv_path)]:
		if csv_path is None or not os.path.exists(csv_path):
			continue
		
		# Read data
		df = pd.read_csv(csv_path)
		
		if len(df) == 0:
			print(f"Warning: {contract_type} CSV is empty")
			continue
		
		# Check required columns
		required_cols = ["otm_pct", "premium_musd", "dte"]
		missing_cols = [col for col in required_cols if col not in df.columns]
		if missing_cols:
			print(f"Warning: {contract_type} CSV missing columns: {missing_cols}")
			continue
		
		# Create figure
		fig, ax = plt.subplots(figsize=(10, 8))
		
		# Prepare data (remove missing values)
		plot_df = df[required_cols].dropna()
		
		if len(plot_df) == 0:
			print(f"Warning: {contract_type} has no valid data after removing NaN")
			continue
		
		# Prepare color mapping: larger DTE (further from expiration) is bluer, smaller DTE (closer to expiration) is whiter
		dte_values = plot_df["dte"].values
		# Normalize DTE values to 0-1 range (0=minimum DTE=white, 1=maximum DTE=blue)
		dte_min, dte_max = dte_values.min(), dte_values.max()
		if dte_max > dte_min:
			dte_normalized = (dte_values - dte_min) / (dte_max - dte_min)
		else:
			dte_normalized = pd.Series([0.5] * len(dte_values))
		
		# Create blue color scale: from white(1,1,1) to blue(0,0,1)
		# Use linear interpolation: white -> light blue -> dark blue
		colors = [(1, 1, 1), (0.7, 0.85, 1), (0.3, 0.6, 1), (0, 0, 1)]  # White to dark blue
		n_bins = 100
		cmap = mcolors.LinearSegmentedColormap.from_list('blue_scale', colors, N=n_bins)
		
		# Plot scatter chart (increase circle size)
		scatter = ax.scatter(
			plot_df["otm_pct"],
			plot_df["premium_musd"],
			c=dte_normalized,
			cmap=cmap,
			s=200,  # Increase scatter point size
			alpha=0.7,
			edgecolors='black',
			linewidths=1.0
		)
		
		# Set title and labels
		ax.set_xlabel('OTM%', fontsize=12)
		ax.set_ylabel('Premium (M USD)', fontsize=12)
		ax.set_title(f'{contract_type} - OTM vs Premium', fontsize=14, fontweight='bold')
		
		# Add colorbar and annotate DTE range on vertical axis
		cbar = plt.colorbar(scatter, ax=ax)
		cbar.set_label('DTE (Days to Expiration)', fontsize=10)
		
		# Set colorbar tick labels to show actual DTE values
		# Select several key points for annotation (min, median, max)
		dte_min_val = int(dte_min)
		dte_max_val = int(dte_max)
		dte_mid_val = int((dte_min + dte_max) / 2)
		
		# Set tick positions (normalized values)
		tick_positions = [0.0, 0.5, 1.0]
		tick_labels = [f'{dte_min_val}', f'{dte_mid_val}', f'{dte_max_val}']
		
		# If DTE range is small, add more annotation points
		if dte_max_val - dte_min_val <= 10:
			# If range is less than or equal to 10, annotate more points
			if dte_max_val - dte_min_val <= 5:
				# Annotate every integer
				tick_positions = []
				tick_labels = []
				for i in range(dte_min_val, dte_max_val + 1):
					if dte_max > dte_min:
						pos = (i - dte_min) / (dte_max - dte_min)
					else:
						pos = 0.5
					tick_positions.append(pos)
					tick_labels.append(str(i))
			else:
				# Annotate several key points
				quarter1 = dte_min_val + (dte_max_val - dte_min_val) // 4
				quarter3 = dte_min_val + 3 * (dte_max_val - dte_min_val) // 4
				tick_positions = []
				tick_labels = []
				for val in [dte_min_val, quarter1, dte_mid_val, quarter3, dte_max_val]:
					if dte_max > dte_min:
						pos = (val - dte_min) / (dte_max - dte_min)
					else:
						pos = 0.5
					tick_positions.append(pos)
					tick_labels.append(str(val))
		
		cbar.set_ticks(tick_positions)
		cbar.set_ticklabels(tick_labels)
		
		# Grid
		ax.grid(True, alpha=0.3, linestyle='--')
		
		# Save image
		output_path = os.path.join(output_dir_path, f"{contract_type}_OTM_vs_Premium.png")
		plt.tight_layout()
		plt.savefig(output_path, dpi=300, bbox_inches='tight')
		plt.close()
		
		print(f"Saved {contract_type} plot to {output_path}")


def generate_webpage(
	call_df: pd.DataFrame = None,
	put_df: pd.DataFrame = None,
	output_html_path: Optional[str] = None,
) -> Optional[str]:
	"""
	Generate HTML webpage with interactive charts and tables
	
	Parameters:
	- call_df: DataFrame containing CALL top 20 data
	- put_df: DataFrame containing PUT top 20 data
	- output_html_path: Output HTML file path
	"""
	if not PLOTLY_AVAILABLE:
		print("Error: Plotly is required for web visualization. Install with 'pip install plotly'")
		return None
	
	if call_df is None and put_df is None:
		print("Warning: No data provided for webpage generation")
		return None
	
	# Collect JSON data for all charts
	chart_divs = []
	
	# Generate charts for CALL and PUT respectively
	for contract_type, df in [("CALL", call_df), ("PUT", put_df)]:
		if df is None or len(df) == 0:
			continue
		
		# Check required columns
		required_cols = ["otm_pct", "premium_musd", "dte", "ul"]
		if not all(col in df.columns for col in required_cols):
			continue
		
		# Prepare data (ensure correct data types)
		plot_df = df[required_cols].copy()
		
		# Convert numeric columns to numeric type, replace NaN
		for col in ["otm_pct", "premium_musd", "dte"]:
			plot_df[col] = pd.to_numeric(plot_df[col], errors='coerce')
		
		# Remove rows containing NaN
		plot_df = plot_df.dropna().copy()
		
		if len(plot_df) == 0:
			print(f"Warning: {contract_type} has no valid data after removing NaN")
			continue
		
		# Debug information
		print(f"Debug: {contract_type} plot data shape: {plot_df.shape}")
		print(f"Debug: {contract_type} first few rows:\n{plot_df.head()}")
		
		# Get underlying asset name (prefer nickname column, otherwise use ul)
		ul_name_col = None
		for col in ["name", "symbol_name", "ticker_name", "ul_name"]:
			if col in df.columns:
				ul_name_col = col
				break
		
		if ul_name_col:
			# Merge ul column and name column to plot_df
			name_map = df.set_index("ul")[ul_name_col].to_dict()
			plot_df["display_name"] = plot_df["ul"].map(lambda x: name_map.get(x, str(x)))
		else:
			plot_df["display_name"] = plot_df["ul"].astype(str)
		
		# Prepare color mapping
		dte_values = plot_df["dte"].values
		dte_min, dte_max = float(dte_values.min()), float(dte_values.max())
		
		# Ensure data is in list format (not pandas Series)
		x_data = plot_df["otm_pct"].tolist()
		y_data = plot_df["premium_musd"].tolist()
		dte_data = plot_df["dte"].tolist()
		
		print(f"Debug: {contract_type} x_data range: {min(x_data) if x_data else 'empty'} to {max(x_data) if x_data else 'empty'}")
		print(f"Debug: {contract_type} y_data range: {min(y_data) if y_data else 'empty'} to {max(y_data) if y_data else 'empty'}")
		print(f"Debug: {contract_type} dte_data range: {min(dte_data) if dte_data else 'empty'} to {max(dte_data) if dte_data else 'empty'}")
		
		# Create Plotly chart
		colorscale = [[0, 'rgb(255,255,255)'], [0.33, 'rgb(179,217,255)'], [0.67, 'rgb(77,153,255)'], [1, 'rgb(0,0,255)']]
		
		fig = go.Figure()
		
		# Add scatter plot (using list data)
		fig.add_trace(go.Scatter(
			x=x_data,
			y=y_data,
			mode='markers',
			marker=dict(
				size=20,
				color=dte_data,
				colorscale=colorscale,
				showscale=True,
				colorbar=dict(title="DTE (Days)"),
				line=dict(width=1, color='black'),
				cmin=dte_min,
				cmax=dte_max
			),
			text=[f"Underlying: {name}<br>OTM%: {otm:.2f}%<br>Premium: ${prem:.2f}M<br>DTE: {dte:.0f} days" 
				  for name, otm, prem, dte in zip(plot_df["display_name"], x_data, y_data, dte_data)],
			hovertemplate='<b>%{text}</b><extra></extra>',
			name=contract_type
		))
		
		fig.update_layout(
			title=dict(
				text=f'<b>{contract_type} - OTM vs Premium</b>',
				font=dict(size=20, color='black', family='Arial, sans-serif')
			),
			xaxis_title=dict(
				text='<b>OTM%</b>',
				font=dict(size=16, color='black', family='Arial, sans-serif')
			),
			yaxis_title=dict(
				text='<b>Premium (M USD)</b>',
				font=dict(size=16, color='black', family='Arial, sans-serif')
			),
			width=1100,
			height=700,
			hovermode='closest',
			showlegend=False
		)
		
		# Update axis tick labels font size
		fig.update_xaxes(tickfont=dict(size=18))
		fig.update_yaxes(tickfont=dict(size=18))
		
		# Ensure axis display correctly with margin for OTM minimum value
		if len(x_data) > 0 and len(y_data) > 0:
			x_min_val = min(x_data)
			x_max_val = max(x_data)
			x_range = x_max_val - x_min_val
			
			# Add margin for x-axis minimum: at least 0.5 absolute margin, or 5% of data range
			x_margin = max(0.5, x_range * 0.05) if x_range > 0 else 0.5
			x_lower = x_min_val - x_margin
			x_upper = x_max_val + x_margin
			
			# y-axis starts from 0 with upper margin
			y_max_val = max(y_data)
			y_range = y_max_val - min(y_data)
			y_margin = max(0.1, y_range * 0.05) if y_range > 0 else 0.1
			y_upper = y_max_val + y_margin
			
			fig.update_xaxes(range=[x_lower, x_upper])
			fig.update_yaxes(range=[0, y_upper])
		
		# Convert chart to JSON format for HTML rendering
		chart_json = fig.to_json()
		chart_divs.append((contract_type, chart_json, df))
	
	# Create HTML content
	html_content = """<!DOCTYPE html>
<html>
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>Option Analysis - CALL & PUT Top 20</title>
	<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
	<style>
		body {
			font-family: Arial, sans-serif;
			margin: 20px;
			background-color: #f5f5f5;
		}
		.container {
			background-color: white;
			padding: 20px;
			margin: 20px 0;
			border-radius: 8px;
			box-shadow: 0 2px 4px rgba(0,0,0,0.1);
		}
		h1 {
			color: #333;
			text-align: center;
		}
		h2 {
			color: #555;
			border-bottom: 2px solid #4CAF50;
			padding-bottom: 10px;
		}
		.chart-container {
			margin: 20px auto;
			display: flex;
			justify-content: center; /* Center chart horizontally */
		}
		table {
			width: 100%;
			border-collapse: collapse;
			margin: 20px 0;
		}
		th, td {
			padding: 12px;
			text-align: center;
			border-bottom: 1px solid #ddd;
		}
		th {
			background-color: #4CAF50;
			color: white;
			font-weight: bold;
		}
		tr:hover {
			background-color: #f5f5f5;
		}
	</style>
</head>
<body>
	<h1>Option Analysis - CALL & PUT Top 20</h1>
"""
	
	# Generate HTML section for each chart
	for contract_type, chart_json, df in chart_divs:
		chart_id = f"{contract_type.lower()}_chart"
		
		# Add to HTML content
		html_content += f"""
	<div class="container">
		<h2>{contract_type} - OTM vs Premium Chart</h2>
		<div class="chart-container">
			<div id="{chart_id}"></div>
		</div>
	</div>
"""
		
		# Generate table HTML
		table_html = f"""
	<div class="container">
		<h2>{contract_type} - Data Table</h2>
		<table>
			<thead>
				<tr>
"""
		# Table header
		for col in df.columns:
			table_html += f"					<th>{col}</th>\n"
		table_html += """				</tr>
			</thead>
			<tbody>
"""
		# Table data
		for _, row in df.iterrows():
			table_html += "				<tr>\n"
			for col in df.columns:
				val = row[col]
				if pd.isna(val):
					table_html += "					<td>-</td>\n"
				elif col == "dte":
					# Keep dte column as integer
					table_html += f"					<td>{int(val)}</td>\n"
				elif isinstance(val, (int, float)):
					# Display as integer if it's an integer, otherwise round to 2 decimal places
					if isinstance(val, float) and val.is_integer():
						table_html += f"					<td>{int(val)}</td>\n"
					else:
						table_html += f"					<td>{val:.2f}</td>\n"
				else:
					table_html += f"					<td>{val}</td>\n"
			table_html += "				</tr>\n"
		
		table_html += """			</tbody>
		</table>
	</div>
"""
		html_content += table_html
	
	# Add JavaScript code to render charts
	html_content += """
	<script>
	// Wait for page to load before rendering charts
	window.addEventListener('DOMContentLoaded', function() {
"""
	
	for contract_type, chart_json, df in chart_divs:
		chart_id = f"{contract_type.lower()}_chart"
		# Parse JSON to validate format, then escape for use in JavaScript strings
		chart_data = json.loads(chart_json)
		# Convert JSON back to string and escape special characters in JavaScript
		chart_json_safe = json.dumps(chart_data).replace('</script>', '<\\/script>').replace('</Script>', '<\\/Script>')
		html_content += f"""
		try {{
			var {chart_id}_data = {chart_json_safe};
			console.log('Rendering {contract_type} chart with', {chart_id}_data.data[0].x.length, 'points');
			Plotly.newPlot('{chart_id}', {chart_id}_data.data, {chart_id}_data.layout, {{
				responsive: true,
				displayModeBar: true
			}});
		}} catch (error) {{
			console.error('Error rendering {contract_type} chart:', error);
		}}
"""
	
	html_content += """	});
	</script>
"""
	
	html_content += """
</body>
</html>
"""
	
	# Save HTML file
	final_output_path = resolve_output_path(output_html_path, "option_analysis.html")
	
	with open(final_output_path, 'w', encoding='utf-8') as f:
		f.write(html_content)
	
	print(f"Saved interactive webpage to {final_output_path}")
	return final_output_path


def generate_otm_premium_dashboard(
	input_csv_path: Optional[str] = None,
	output_html_path: Optional[str] = None,
	default_opt_multiplier: int = 100,
) -> Optional[str]:
	"""
	Orchestrate the OTM premium analysis pipeline and return the generated HTML path.
	"""
	csv_path = input_csv_path or DEFAULT_INPUT_CSV
	if not csv_path or not os.path.exists(csv_path):
		print(f"[WARN] OtmPremium input CSV not found: {csv_path}")
		return None
	try:
		_, call_top20_df, put_top20_df = compute_metrics_and_qc(
			csv_path,
			output_csv_path=None,
			default_opt_multiplier=default_opt_multiplier,
		)
	except Exception as exc:
		print(f"[WARN] Failed to compute OtmPremium metrics: {exc}")
		return None

	if call_top20_df is None and put_top20_df is None:
		print("[WARN] OtmPremium analysis did not return qualifying CALL/PUT data.")
		return None

	return generate_webpage(
		call_df=call_top20_df,
		put_df=put_top20_df,
		output_html_path=output_html_path,
	)


if __name__ == "__main__":
	# Example run: read CSV from current directory and generate webpage only
	input_path = "OtmPremium_db.csv"
	df_out, call_top20_df, put_top20_df = compute_metrics_and_qc(input_path, output_csv_path=None)
	print(f"Processed rows: {len(df_out)}")
	
	# Generate interactive webpage directly from DataFrames
	if call_top20_df is not None or put_top20_df is not None:
		generate_webpage(call_df=call_top20_df, put_df=put_top20_df, output_html_path="option_analysis.html")
	else:
		print("Warning: No top 20 data available for webpage generation")


