import os
import io
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go

# 配置常量
BASE_URL = "https://api.etherscan.io/v2/api"
USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 5
DEFAULT_CHAIN_ID = 1  # Ethereum mainnet
USDT_DECIMALS = 6  # ERC20 USDT on Ethereum uses 6 decimals


class EtherscanError(Exception):
    pass


def get_api_key() -> str:
    """从Streamlit secrets或环境变量获取API Key"""
    try:
        # 优先使用Streamlit secrets（用于云端部署）
        key = st.secrets.get("ETHERSCAN_API_KEY_Reconciliation")
        if key:
            return key
    except:
        pass
    
    # 回退到环境变量（用于本地开发）
    key = os.getenv("ETHERSCAN_API_KEY_Reconciliation")
    if not key:
        raise EtherscanError("ETHERSCAN_API_KEY_Reconciliation not set in secrets or environment.")
    return key


def get_chain_id() -> int:
    """获取链ID"""
    try:
        chain_id = st.secrets.get("ETHERSCAN_CHAIN_ID")
        if chain_id:
            return int(chain_id)
    except:
        pass
    
    env_val = os.getenv("ETHERSCAN_CHAIN_ID")
    if not env_val:
        return DEFAULT_CHAIN_ID
    try:
        return int(env_val)
    except ValueError as exc:
        raise EtherscanError("ETHERSCAN_CHAIN_ID must be an integer.") from exc


@st.cache_data(ttl=300)  # 缓存5分钟
def fetch_usdt_transfers(
    api_key: str,
    chain_id: int,
    start_block: int = 0,
    end_block: int = 99999999,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    min_value: Optional[float] = None,
    sort: str = "desc",
    sleep_secs: float = 0.2,
) -> List[Dict]:
    """从Etherscan API获取USDT转账记录"""
    records: List[Dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "module": "account",
            "action": "tokentx",
            "contractaddress": USDT_CONTRACT,
            "chainid": chain_id,
            "page": page,
            "offset": page_size,
            "startblock": start_block,
            "endblock": end_block,
            "sort": sort,
            "apikey": api_key,
        }
        resp = requests.get(BASE_URL, params=params, timeout=15)
        if resp.status_code != 200:
            raise EtherscanError(f"Etherscan status {resp.status_code}: {resp.text}")
        payload = resp.json()
        status = payload.get("status")
        if status not in ("1", 1, True):
            message = payload.get("message") or "unknown error"
            if message.lower().strip() == "no records found":
                break
            raise EtherscanError(f"Etherscan error: {message}")
        page_result = payload.get("result") or []
        if not page_result:
            break
        filtered = list(_transform_and_filter(page_result, min_value))
        records.extend(filtered)
        if len(page_result) < page_size:
            break
        time.sleep(sleep_secs)
    return records


def _transform_and_filter(items: Iterable[Dict], min_value: Optional[float]) -> Iterable[Dict]:
    """转换和过滤数据"""
    for item in items:
        raw_value = item.get("value", "0")
        amount = int(raw_value) / (10 ** USDT_DECIMALS)
        if min_value is not None and amount < min_value:
            continue
        gas_price = int(item.get("gasPrice", "0"))
        gas_used = int(item.get("gasUsed", "0"))
        fee_eth = (gas_price * gas_used) / (10 ** 18)
        ts = int(item.get("timeStamp", "0"))
        yield {
            "from": item.get("from"),
            "to": item.get("to"),
            "amount_usdt": amount,
            "tx_hash": item.get("hash"),
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "fee_eth": fee_eth,
        }


def generate_excel_report(records: List[Dict]) -> bytes:
    """在内存中生成Excel文件"""
    if not records:
        raise ValueError("No records to export.")
    
    df = pd.DataFrame(records)
    # 重命名列以便更好地展示
    df.rename(columns={
        "from": "付款方 (From)",
        "to": "收款方 (To)",
        "amount_usdt": "金额 (USDT)",
        "tx_hash": "交易哈希 (TxHash)",
        "timestamp": "交易时间",
        "fee_eth": "手续费 (ETH)"
    }, inplace=True)
    
    # 重新排列列顺序
    df = df[["交易时间", "付款方 (From)", "收款方 (To)", "金额 (USDT)", "手续费 (ETH)", "交易哈希 (TxHash)"]]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='USDT_Transfers')
    
    return output.getvalue()


def create_fund_flow_chart(df: pd.DataFrame, top_n: int = 10):
    """创建资金流向图 - 显示Top收款方和付款方"""
    from plotly.subplots import make_subplots
    
    # 计算Top收款方
    top_receivers = df.groupby("收款方 (To)")["金额 (USDT)"].sum().nlargest(top_n)
    # 计算Top付款方
    top_senders = df.groupby("付款方 (From)")["金额 (USDT)"].sum().nlargest(top_n)
    
    # 创建子图
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Top收款方', 'Top付款方'),
        horizontal_spacing=0.15
    )
    
    # 添加收款方柱状图
    fig.add_trace(
        go.Bar(
            x=top_receivers.values,
            y=top_receivers.index,
            name="收款方",
            orientation='h',
            marker_color='#2ecc71',
            showlegend=False
        ),
        row=1, col=1
    )
    
    # 添加付款方柱状图
    fig.add_trace(
        go.Bar(
            x=top_senders.values,
            y=top_senders.index,
            name="付款方",
            orientation='h',
            marker_color='#e74c3c',
            showlegend=False
        ),
        row=1, col=2
    )
    
    fig.update_xaxes(title_text="金额 (USDT)", row=1, col=1)
    fig.update_xaxes(title_text="金额 (USDT)", row=1, col=2)
    fig.update_yaxes(title_text="地址", row=1, col=1)
    fig.update_yaxes(title_text="地址", row=1, col=2)
    
    fig.update_layout(
        title_text=f"资金流向分析 - Top {top_n} 收款方/付款方",
        height=600,
        hovermode='closest'
    )
    
    return fig


def create_fee_fluctuation_chart(df: pd.DataFrame):
    """创建费率波动图 - 展示手续费随时间的变化"""
    # 转换时间列为datetime
    df['交易时间_datetime'] = pd.to_datetime(df['交易时间'])
    df_sorted = df.sort_values('交易时间_datetime')
    
    fig = go.Figure()
    
    # 添加手续费散点图
    fig.add_trace(go.Scatter(
        x=df_sorted['交易时间_datetime'],
        y=df_sorted['手续费 (ETH)'],
        mode='markers+lines',
        name='手续费 (ETH)',
        marker=dict(size=4, color='#3498db'),
        line=dict(width=1)
    ))
    
    fig.update_layout(
        title="手续费波动趋势",
        xaxis_title="交易时间",
        yaxis_title="手续费 (ETH)",
        height=400,
        hovermode='x unified',
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray'
        )
    )
    
    return fig


# Streamlit 界面
st.set_page_config(
    page_title="链上支付对账报告系统",
    page_icon="🔗",
    layout="wide"
)

st.title("🔗 链上支付对账报告系统")
st.write("此应用从以太坊链上实时获取最新的USDT转账记录，并将其处理成可供下载的对账Excel报表。")

# 获取API配置
try:
    api_key = get_api_key()
    chain_id = get_chain_id()
except EtherscanError as e:
    st.error(f"配置错误: {e}")
    st.info("""
    请设置API Key：
    - **本地开发**：在 `.streamlit/secrets.toml` 文件中添加 `ETHERSCAN_API_KEY_Reconciliation = "your_api_key"`
    - **云端部署**：在Streamlit Cloud的Secrets设置中添加 `ETHERSCAN_API_KEY_Reconciliation`
    """)
    st.stop()

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置选项")
    min_usdt = st.number_input(
        "最小USDT金额过滤",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help="只显示金额大于此值的交易"
    )
    max_pages = st.slider(
        "最大抓取页数",
        min_value=1,
        max_value=10,
        value=5,
        help="每页100条记录，最多抓取多少页"
    )
    preview_rows = st.number_input(
        "数据预览行数",
        min_value=5,
        max_value=50,
        value=10,
        step=5
    )

# 主按钮
if st.button('🚀 生成最新对账报告', type="primary", use_container_width=True):
    with st.spinner('正在从区块链抓取最新数据...'):
        try:
            records = fetch_usdt_transfers(
                api_key=api_key,
                chain_id=chain_id,
                min_value=min_usdt if min_usdt > 0 else None,
                max_pages=max_pages
            )
        except EtherscanError as e:
            st.error(f"数据抓取失败: {e}")
            st.stop()
    
    if not records:
        st.warning("未获取到任何数据，请检查过滤条件或稍后再试。")
        st.stop()
    
    st.success(f'✅ 数据抓取成功！共获取 {len(records)} 条记录')
    
    # 转换为DataFrame用于展示和生成Excel
    df_raw = pd.DataFrame(records)
    df_display = df_raw.copy()
    df_display.rename(columns={
        "from": "付款方 (From)",
        "to": "收款方 (To)",
        "amount_usdt": "金额 (USDT)",
        "tx_hash": "交易哈希 (TxHash)",
        "timestamp": "交易时间",
        "fee_eth": "手续费 (ETH)"
    }, inplace=True)
    df_display = df_display[["交易时间", "付款方 (From)", "收款方 (To)", "金额 (USDT)", "手续费 (ETH)", "交易哈希 (TxHash)"]]
    
    # 生成Excel
    with st.spinner('正在生成Excel报表...'):
        try:
            excel_data = generate_excel_report(records)
        except Exception as e:
            st.error(f"Excel生成失败: {e}")
            st.stop()
    
    st.success('✅ 报表生成成功！')
    
    # 数据预览
    st.subheader("📊 数据预览")
    st.dataframe(df_display.head(preview_rows), use_container_width=True)
    
    # 统计信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总交易数", len(records))
    with col2:
        st.metric("总金额 (USDT)", f"{df_display['金额 (USDT)'].sum():,.2f}")
    with col3:
        st.metric("平均金额 (USDT)", f"{df_display['金额 (USDT)'].mean():,.2f}")
    with col4:
        st.metric("总手续费 (ETH)", f"{df_display['手续费 (ETH)'].sum():.6f}")
    
    # 下载按钮
    st.subheader("📥 下载报告")
    st.download_button(
        label="📥 下载Excel报表",
        data=excel_data,
        file_name="onchain_reconciliation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    # 可视化图表
    st.subheader("📈 数据分析图表")
    
    # 资金流向图
    st.plotly_chart(
        create_fund_flow_chart(df_display, top_n=10),
        use_container_width=True
    )
    
    # 费率波动图
    st.plotly_chart(
        create_fee_fluctuation_chart(df_display),
        use_container_width=True
    )

