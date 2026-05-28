import streamlit as st
import boto3
import decimal
import pandas as pd
from datetime import datetime, timedelta, timezone


# 페이지 설정
st.set_page_config(
    page_title="V4 Trading Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# AWS 클라이언트 (Streamlit secrets에서 자격증명)
@st.cache_resource
def get_dynamodb():
    return boto3.resource(
        'dynamodb',
        region_name='ap-northeast-2',
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"]
    )


dynamodb = get_dynamodb()
KST = timezone(timedelta(hours=9))
TIER_EMOJI = {'core': '🏛️', 'active': '⚡', 'watch': '👀', 'value': '💎'}


def now_kst():
    return datetime.now(KST)


def to_float(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_float(item) for item in obj]
    return obj


def scan_all(table_name):
    """페이지네이션으로 모든 데이터 가져오기"""
    table = dynamodb.Table(table_name)
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
    return [to_float(item) for item in items]


# 데이터 가져오기 (캐시 5분)
@st.cache_data(ttl=300)
def get_portfolio():
    table = dynamodb.Table('v4-portfolio')
    response = table.get_item(Key={'id': 'current'})
    if 'Item' in response:
        return to_float(response['Item'])
    return None


@st.cache_data(ttl=300)
def get_trades():
    items = scan_all('v4-trades')
    items.sort(key=lambda x: x.get('timestamp', ''))
    return items


@st.cache_data(ttl=300)
def get_signals():
    items = scan_all('v4-analysis-results')
    items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return items


# ============ UI ============
st.title("🤖 V4 Trading Bot Dashboard")
st.caption(f"마지막 새로고침: {now_kst().strftime('%Y-%m-%d %H:%M KST')}")

# 새로고침 버튼
if st.button("🔄 새로고침"):
    st.cache_data.clear()
    st.rerun()

# 데이터 로드
portfolio = get_portfolio()
if not portfolio:
    st.error("❌ 포트폴리오 데이터 없음")
    st.stop()

trades = get_trades()
signals = get_signals()

# ============ 자산 요약 ============
st.header("💎 자산 요약")

initial = portfolio.get('initial_capital', 50000)
cash = portfolio.get('cash', 0)
total = portfolio.get('total_value', cash)
return_pct = ((total - initial) / initial) * 100 if initial > 0 else 0
return_dollar = total - initial

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("총 자산", f"${total:,.2f}", f"${return_dollar:+,.2f}")
with col2:
    st.metric("현금", f"${cash:,.2f}")
with col3:
    holdings_count = len(portfolio.get('holdings', {}))
    st.metric("보유 종목", f"{holdings_count}개")
with col4:
    st.metric("누적 수익률", f"{return_pct:+.2f}%")

# ============ 보유 종목 ============
st.header("💼 보유 종목")

holdings = portfolio.get('holdings', {})
if holdings:
    holdings_data = []
    for symbol, h in holdings.items():
        market = h.get('market', 'US')
        flag = '🇺🇸' if market == 'US' else '🇰🇷'
        tier = h.get('tier', 'unknown')
        tier_disp = f"{TIER_EMOJI.get(tier, '❓')} {tier}"
        name = h.get('name', symbol)
        shares = h.get('shares', 0)
        avg_price = h.get('avg_price', 0)
        total_cost = h.get('total_cost', 0)
        current_value = h.get('current_value', total_cost)
        pnl = current_value - total_cost
        pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0

        if market == 'KR':
            avg_str = f"₩{avg_price:,.0f}"
        else:
            avg_str = f"${avg_price:.2f}"

        holdings_data.append({
            '시장': flag,
            'Tier': tier_disp,
            '종목': name,
            '수량': shares,
            '평균가': avg_str,
            '매수액 (USD)': f"${total_cost:.2f}",
            '현재가치 (USD)': f"${current_value:.2f}",
            'P&L': f"${pnl:+.2f}",
            '수익률': f"{pnl_pct:+.2f}%"
        })

    df = pd.DataFrame(holdings_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 비중 파이차트
    pie_data = pd.DataFrame([
        {'종목': h.get('name', s), '가치': h.get('current_value', h.get('total_cost', 0))}
        for s, h in holdings.items()
    ])
    pie_data.loc[len(pie_data)] = {'종목': '현금', '가치': cash}

    st.subheader("자산 배분")
    st.bar_chart(pie_data, x='종목', y='가치')
else:
    st.info("보유 종목 없음")

# ============ 거래 통계 ============
st.header("📊 거래 통계")

if trades:
    sells = [t for t in trades if t.get('action') == 'SELL']
    buys = [t for t in trades if t.get('action') == 'BUY']
    wins = [t for t in sells if t.get('pnl', 0) > 0]
    losses = [t for t in sells if t.get('pnl', 0) <= 0]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("총 거래", f"{len(trades)}건")
    with col2:
        st.metric("매수/매도", f"{len(buys)} / {len(sells)}")
    with col3:
        if sells:
            win_rate = len(wins) / len(sells) * 100
            st.metric("승률", f"{win_rate:.1f}%", f"{len(wins)}승 {len(losses)}패")
        else:
            st.metric("승률", "N/A")
    with col4:
        total_pnl = sum(t.get('pnl', 0) for t in sells)
        st.metric("실현 P&L", f"${total_pnl:+.2f}")
else:
    st.info("거래 기록 없음")

# ============ 거래 이력 ============
st.header("🔄 거래 이력")

if trades:
    trades_data = []
    for t in reversed(trades[-20:]):  # 최근 20건
        market = t.get('market', 'US')
        flag = '🇺🇸' if market == 'US' else '🇰🇷'
        tier = t.get('tier', 'unknown')
        tier_disp = f"{TIER_EMOJI.get(tier, '❓')} {tier}"
        action = t.get('action', '?')
        action_emoji = "🟢" if action == 'BUY' else "🔴"
        name = t.get('name', t.get('symbol', '?'))
        shares = t.get('shares', 0)
        price = t.get('price', 0)
        ts = t.get('timestamp', '')[:16].replace('T', ' ')

        if market == 'KR':
            price_str = f"₩{price:,.0f}"
        else:
            price_str = f"${price:.2f}"

        row = {
            '시간 (KST)': ts,
            '시장': flag,
            'Tier': tier_disp,
            '액션': f"{action_emoji} {action}",
            '종목': name,
            '수량': shares,
            '가격': price_str,
        }

        if action == 'SELL':
            pnl = t.get('pnl', 0)
            pnl_pct = t.get('pnl_pct', 0)
            row['P&L'] = f"${pnl:+.2f} ({pnl_pct:+.2f}%)"
        else:
            row['P&L'] = '-'

        trades_data.append(row)

    df = pd.DataFrame(trades_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("거래 기록 없음")

# ============ 한국 종목 수급 ============
st.header("🇰🇷 한국 종목 수급 현황")


@st.cache_data(ttl=300)
def get_kr_supply_data():
    """보유 KR 종목의 최근 수급 시그널"""
    signals = scan_all('v4-analysis-results')
    kr_signals = [s for s in signals if s.get('market') == 'KR' and s.get('supply')]
    latest_by_symbol = {}
    for s in sorted(kr_signals, key=lambda x: x.get('timestamp', ''), reverse=True):
        symbol = s.get('symbol')
        if symbol and symbol not in latest_by_symbol:
            latest_by_symbol[symbol] = s
    return latest_by_symbol


kr_supply = get_kr_supply_data()
if portfolio and kr_supply:
    holdings = portfolio.get('holdings', {})
    kr_holdings = {s: h for s, h in holdings.items() if h.get('market') == 'KR'}

    if kr_holdings:
        supply_table = []
        for symbol, h in kr_holdings.items():
            sig = kr_supply.get(symbol, {})
            supply = sig.get('supply', {})

            if not supply:
                continue

            name = h.get('name', symbol)

            foreign_amt = supply.get('foreign_5day_amount_eok', 0)
            inst_amt = supply.get('institution_5day_amount_eok', 0)
            personal_amt = supply.get('personal_5day_amount_eok', 0)
            foreign_streak = supply.get('foreign_streak', 0)
            inst_streak = supply.get('institution_streak', 0)
            personal_streak = supply.get('personal_streak', 0)

            # 패턴 판정
            big_money = foreign_amt + inst_amt
            if big_money < -500 and personal_amt > 500:
                pattern = "👥 동학개미"
            elif foreign_amt > 100 and inst_amt > 100 and personal_amt > 0:
                pattern = "🔥 전방위 매수"
            elif foreign_amt > 100 and inst_amt > 100:
                pattern = "📈 외국인+기관"
            elif foreign_amt < -100 and inst_amt < -100 and personal_amt < -100:
                pattern = "❄️ 전방위 매도"
            elif foreign_amt < -100 and inst_amt < -100:
                pattern = "📉 외국인+기관 매도"
            else:
                pattern = "➖ 혼조"

            supply_table.append({
                '종목': name,
                '외국인': f"{foreign_amt:+,.0f}억",
                '기관': f"{inst_amt:+,.0f}억",
                '개인': f"{personal_amt:+,.0f}억",
                '패턴': pattern
            })

        if supply_table:
            df = pd.DataFrame(supply_table)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # 차트
            st.subheader("📊 보유 종목 수급 비교 (5일 누적)")
            chart_data = []
            for symbol, h in kr_holdings.items():
                sig = kr_supply.get(symbol, {})
                supply = sig.get('supply', {})
                if not supply:
                    continue
                chart_data.append({
                    '종목': h.get('name', symbol),
                    '외국인': supply.get('foreign_5day_amount_eok', 0),
                    '기관': supply.get('institution_5day_amount_eok', 0),
                    '개인': supply.get('personal_5day_amount_eok', 0)
                })

            if chart_data:
                chart_df = pd.DataFrame(chart_data)
                chart_df_melted = chart_df.melt(
                    id_vars='종목',
                    value_vars=['외국인', '기관', '개인'],
                    var_name='주체',
                    value_name='5일 순매수 (억원)'
                )
                st.bar_chart(chart_df_melted, x='종목', y='5일 순매수 (억원)', color='주체')
        else:
            st.info("KR 보유 종목 수급 데이터 없음")
    else:
        st.info("한국 보유 종목 없음")
else:
    st.info("수급 데이터 없음 (Phase 1 적용 후 새 시그널부터 표시)")


# ============ 최근 시그널 ============
st.header("📰 최근 시그널")

if signals:
    signal_data = []
    for s in signals[:20]:
        market = s.get('market', 'US')
        flag = '🇺🇸' if market == 'US' else '🇰🇷'
        signal_type = s.get('signal', '?')

        emoji_map = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡', 'WATCH': '⚪'}
        emoji = emoji_map.get(signal_type, '❓')

        confidence = s.get('confidence', 0)
        if isinstance(confidence, float) and confidence <= 1:
            confidence = confidence * 100

        name = s.get('name', s.get('symbol', '?'))
        ts = s.get('timestamp', '')[:16].replace('T', ' ')

        signal_data.append({
            '시간 (UTC)': ts,
            '시장': flag,
            '시그널': f"{emoji} {signal_type}",
            '종목': name,
            '신뢰도': f"{confidence:.0f}%"
        })

    df = pd.DataFrame(signal_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("시그널 기록 없음")

# Footer
st.divider()
st.caption("V4 Cloud Trading Bot · AWS Lambda + DynamoDB · 매시간 자동 매매")
