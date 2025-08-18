import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from hubspot import HubSpot
from hubspot.crm.deals.exceptions import ApiException
from hubspot.crm.owners.exceptions import ApiException as OwnersApiException
import pytz

# --- 페이지 설정 ---
st.set_page_config(layout="wide", page_title="GS KR Sales Dashboard")

# --- 담당자 리스트 ---
BDR_NAMES = ['Sohee (Blair) Kim', 'Soorim Yu', 'Gyeol Jang', 'Minyoung Kim']
AE_NAMES = ['Seheon Bok', 'Buheon Shin', 'Ethan Lee', 'Iseul Lee', 'Samin Park', 'Haran Bae']
ALL_PICS = ['All'] + sorted(BDR_NAMES + AE_NAMES)

# --- Deal Stage ID 매핑 ---
DEAL_STAGE_MAPPING = {
    'closedwon': 'Proposal Sent & Service Validation', 
    '108159779': 'Contract Sent', 
    '108877850': 'Payment Complete',
    'qualifiedtobuy': 'Meeting Booked',
    'decisionmakerboughtin': 'Meeting Done',
    '998897766': 'Initial Contact',
    '998897767': 'Response Received',
    '109960046': 'Dropped',
    '129259600': 'Price Negotiation',
    '108159780': 'Contract Signed',
    'closedlost': 'Closed Lost',
    'appointmentscheduled': 'New',
    '107905727': 'Lost',
    '1105439053': 'Cancel'
}

# '계약 성사' 및 '실패' 기준
won_stages = ['Contract Signed', 'Payment Complete']
lost_stages = ['Closed Lost', 'Dropped', 'Lost', 'Cancel']

# --- 데이터 로딩 및 전처리 함수 ---
@st.cache_data(ttl=3600, show_spinner=False)
def load_data_from_hubspot():
    try:
        access_token = st.secrets["HUBSPOT_ACCESS_TOKEN"]
        hubspot_client = HubSpot(access_token=access_token)
    except KeyError:
        st.error("HubSpot 접근 토큰이 설정되지 않았습니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
        return None
    
    owner_id_to_name = {}
    with st.spinner("HubSpot에서 Owner 정보를 불러오는 중입니다..."):
        try:
            all_owners = []
            after_owner = None
            while True:
                page = hubspot_client.crm.owners.owners_api.get_page(after=after_owner)
                all_owners.extend(page.results)
                if page.paging and page.paging.next: after_owner = page.paging.next.after
                else: break
            owner_id_to_name = {owner.id: f"{owner.first_name or ''} {owner.last_name or ''}".strip() for owner in all_owners}
        except Exception as e:
            st.error(f"Owner 데이터 로딩 중 오류 발생: {e}"); return None

    properties_to_fetch = [
        "dealname", "dealstage", "amount", "createdate", "closedate", 
        "hs_lastmodifieddate", "hubspot_owner_id", "bdr", "hs_lost_reason",
        "dropped_reason", "remark__fre_text_",
        "expected_closing_date", "hs_v2_date_entered_current_stage",
        "contract_sent_date", "contract_signed_date", 
        "payment_complete_date", "demo_booked", "demo_done_date"
    ]

    all_deals = []
    after = None
    with st.spinner("HubSpot에서 모든 Deal 데이터를 불러오는 중입니다... (시간이 걸릴 수 있습니다)"):
        try:
            while True:
                page = hubspot_client.crm.deals.basic_api.get_page(limit=100, after=after, properties=properties_to_fetch)
                all_deals.extend([deal.to_dict() for deal in page.results])
                if page.paging and page.paging.next: after = page.paging.next.after
                else: break
        except ApiException as e:
            st.error(f"HubSpot Deals API 호출 중 오류 발생: {e}"); return None
        
    if not all_deals: return pd.DataFrame()
    df = pd.DataFrame([deal['properties'] for deal in all_deals])
    if df.empty: return df

    for col in properties_to_fetch:
        if col not in df.columns:
            df[col] = pd.NaT if 'date' in col else None
              
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['dealstage'] = df['dealstage'].map(DEAL_STAGE_MAPPING).fillna(df['dealstage'])
    df['Deal owner'] = df['hubspot_owner_id'].map(owner_id_to_name).fillna('Unassigned')
    
    if 'bdr' in df.columns:
        df['BDR'] = df['bdr'].map(owner_id_to_name).fillna('Unassigned')
    else:
        st.warning("주의: 'bdr' 속성을 HubSpot에서 찾을 수 없습니다. BDR 리더보드가 비어있을 수 있습니다.")
        df['BDR'] = 'Unassigned'
    
    date_cols = [
        'closedate', 'createdate', 'hs_lastmodifieddate', 'expected_closing_date',
        'hs_v2_date_entered_current_stage', 'contract_sent_date', 'contract_signed_date',
        'payment_complete_date', 'demo_booked', 'demo_done_date'
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)
            if df[col].notna().any():
                df[col] = df[col].dt.tz_convert('Asia/Seoul')

    rename_map = {
        'dealname': 'Deal name', 'dealstage': 'Deal Stage', 'amount': 'Amount',
        'createdate': 'Create Date', 'closedate': 'Close Date',
        'hs_lastmodifieddate': 'Last Modified Date', 
        'expected_closing_date': 'Expected Closing Date',
        'hs_lost_reason': 'Failure Reason', 
        'hs_v2_date_entered_current_stage': 'Date Entered Stage',
        'dropped_reason': 'Dropped Reason',
        'remark__fre_text_': 'Dropped Reason (Remark)',
        'contract_sent_date': 'Contract Sent Date',
        'contract_signed_date': 'Contract Signed Date',
        'payment_complete_date': 'Payment Complete Date',
        'demo_booked': 'Meeting Booked Date',
        'demo_done_date': 'Meeting Done Date'
    }
    df.rename(columns=rename_map, inplace=True)
    
    if 'Expected Closing Date' in df.columns and 'Close Date' in df.columns:
        df['Effective Close Date'] = df['Expected Closing Date'].fillna(df['Close Date'])
    elif 'Close Date' in df.columns: df['Effective Close Date'] = df['Close Date']
    else: df['Effective Close Date'] = pd.NaT
    
    df = df[(df['Deal owner'].isin(AE_NAMES)) | (df['BDR'].isin(BDR_NAMES))].copy()
    return df

# --- UI 및 대시보드 시작 ---
st.title("🎯 Sales Dashboard")
st.markdown("데이터를 기반으로 **성장 전략**을 수립합니다.")

df = load_data_from_hubspot()

if df is None or df.empty:
    st.warning("분석할 데이터가 없거나 로딩에 실패했습니다."); st.stop()

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    st.success("데이터 로딩 완료!")
    csv_data = df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        label="📥 HubSpot DEAL LIST",
        data=csv_data,
        file_name=f"hubspot_deals_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
    
    sales_quota = st.number_input("분기/월별 Sales Quota (목표 매출, USD) 입력", min_value=0, value=500000, step=10000)
    st.markdown("---")
    filter_type = st.radio(
        "**날짜 필터 기준 선택**",
        ('생성일 기준 (Create Date)', '예상/확정 마감일 기준', '최종 수정일 기준 (Last Modified Date)'),
        help="**생성일 기준:** 특정 기간에 생성된 딜 분석\n\n**예상/확정 마감일 기준:** 특정 기간에 마감될 딜 분석\n\n**최종 수정일 기준:** 특정 기간에 업데이트된 딜 분석"
    )
    if filter_type == '생성일 기준 (Create Date)': filter_col = 'Create Date'
    elif filter_type == '예상/확정 마감일 기준': filter_col = 'Effective Close Date'
    else: filter_col = 'Last Modified Date'
    
    if not df[filter_col].isna().all():
        min_date, max_date = df[filter_col].min().date(), df[filter_col].max().date()
        date_range = st.date_input("분석할 날짜 범위 선택", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    else:
        st.error(f"'{filter_col}' 데이터가 없어 필터를 설정할 수 없습니다."); st.stop()

# --- 데이터 필터링 ---
korea_tz = pytz.timezone('Asia/Seoul')
start_date = korea_tz.localize(datetime.combine(date_range[0], datetime.min.time()))
end_date = korea_tz.localize(datetime.combine(date_range[1], datetime.max.time()))

base_df = df[df[filter_col].between(start_date, end_date)].copy()

# ✅ FIX: '계약 성사' 카운팅 로직을 'Contract Signed Date' 또는 'Payment Complete Date' 기준으로 변경
# 1. 먼저 'won_stages'에 해당하는 모든 딜을 필터링합니다.
won_deals_df = df[df['Deal Stage'].isin(won_stages)].copy()
# 2. 두 날짜 컬럼 중 하나라도 선택된 기간에 포함되는지 확인합니다.
signed_in_period = won_deals_df['Contract Signed Date'].between(start_date, end_date)
paid_in_period = won_deals_df['Payment Complete Date'].between(start_date, end_date)
# 3. 두 조건 중 하나라도 만족하는 딜을 최종 '기간 내 성사' 딜로 정의합니다.
deals_won_in_period = won_deals_df[signed_in_period.fillna(False) | paid_in_period.fillna(False)]

if base_df.empty and deals_won_in_period.empty:
    st.warning("선택된 조건에 해당하는 데이터가 없습니다.");

# --- 메인 대시보드 ---
tab1, tab2, tab3, tab4 = st.tabs(["🚀 통합 대시보드", "🧑‍💻 담당자별 상세 분석", "⚠️ 기회 & 리스크 관리", "📉 실패/드랍 분석"])

with tab1:
    st.header("팀 전체 현황 요약")
    
    won_deals_total = deals_won_in_period # 새로운 기준으로 교체
    
    total_revenue, num_won_deals = won_deals_total['Amount'].sum(), len(won_deals_total)
    avg_deal_value = total_revenue / num_won_deals if num_won_deals > 0 else 0
    
    # ✅ FIX: 평균 영업 사이클 계산 기준을 'Contract Signed Date'로 변경
    if not won_deals_total.empty and won_deals_total['Contract Signed Date'].notna().all() and won_deals_total['Create Date'].notna().all():
        avg_sales_cycle = (won_deals_total['Contract Signed Date'] - won_deals_total['Create Date']).dt.days.mean()
    else:
        avg_sales_cycle = 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 계약 금액 (USD)", f"${total_revenue:,.0f}")
    col2.metric("계약 성사 건수", f"{num_won_deals:,} 건")
    col3.metric("평균 계약 금액 (USD)", f"${avg_deal_value:,.0f}")
    col4.metric("평균 영업 사이클", f"{avg_sales_cycle:.1f} 일")

    # ... (tab1의 나머지 부분은 동일하게 유지)
    ...

with tab2:
    selected_pic = st.selectbox("분석할 담당자를 선택하세요.", ALL_PICS)
    st.header(f"'{selected_pic}' 상세 분석")

    if selected_pic == 'All':
        st.subheader("AE Leaderboard")
        # ✅ FIX: AE 리더보드도 새로운 '기간 내 성사' 기준으로 집계
        ae_won_stats = deals_won_in_period[deals_won_in_period['Deal owner'].isin(AE_NAMES)]\
            .groupby('Deal owner')\
            .agg(
                Deals_Won=('Deal name', 'count'),
                Total_Revenue=('Amount', 'sum')
            ).reset_index()

        all_ae_df = pd.DataFrame(AE_NAMES, columns=['Deal owner'])
        ae_stats = pd.merge(all_ae_df, ae_won_stats, on='Deal owner', how='left').fillna(0)
        ae_stats = ae_stats.sort_values(by='Total_Revenue', ascending=False)
        st.dataframe(ae_stats.style.format({'Total_Revenue': '${:,.0f}','Deals_Won': '{:,}'}), use_container_width=True, hide_index=True)
        
        # BDR 리더보드는 기존 로직(base_df 기준)이 더 적합하므로 유지
        st.subheader("BDR Leaderboard")
        # ... (BDR 리더보드 코드는 기존과 동일)
        ...

    else:
        # 개인별 상세 분석도 won_deals 계산 로직 변경 필요 (아래 예시 참고)
        # filtered_df = base_df[...]
        # person_won_deals = deals_won_in_period[deals_won_in_period['Deal owner'] == selected_pic]
        # num_won_deals_pic = len(person_won_deals)
        st.info(f"'{selected_pic}'의 개인 상세 분석 기능은 이 곳에 구현됩니다.")


with tab3:
    st.header("주요 딜 관리 및 리스크 분석")
    st.subheader("🎯 Next Focus (마감 임박 딜)")
    focus_days = st.selectbox("집중할 기간(일)을 선택하세요:", (30, 60, 90), index=0)
    today = datetime.now(korea_tz)
    days_later = today + timedelta(days=focus_days)
    all_open_deals = df[~df['Deal Stage'].isin(won_stages + lost_stages)]
    focus_deals = all_open_deals[
        (all_open_deals.get('Effective Close Date').notna()) &
        (all_open_deals.get('Effective Close Date') >= today) &
        (all_open_deals.get('Effective Close Date') <= days_later)
    ].sort_values('Amount', ascending=False)
    if not focus_deals.empty:
        focus_deals['Days to Close'] = (focus_deals['Effective Close Date'] - today).dt.days
        st.dataframe(focus_deals[['Deal name', 'Deal owner', 'Amount', 'Effective Close Date', 'Days to Close']].style.format({'Amount': '${:,.0f}'}), use_container_width=True)
    else:
        st.info(f"향후 {focus_days}일 내에 마감될 것으로 예상되는 딜이 없습니다.")

    st.markdown("---")
    st.subheader("👀 장기 체류 딜 (Stale Deals) 관리")
    open_deals_base = base_df[~base_df['Deal Stage'].isin(won_stages + lost_stages)]
    stale_threshold = st.slider("며칠 이상 같은 단계에 머물면 '장기 체류'로 볼까요?", 7, 90, 30)
    
    if 'Date Entered Stage' in open_deals_base.columns:
        open_deals_stale = open_deals_base.copy().dropna(subset=['Date Entered Stage'])
        if pd.api.types.is_datetime64_any_dtype(open_deals_stale['Date Entered Stage']):
            open_deals_stale['Days in Stage'] = (today - open_deals_stale['Date Entered Stage']).dt.days
            stale_deals_df = open_deals_stale[open_deals_stale['Days in Stage'] > stale_threshold]
            if not stale_deals_df.empty:
                st.warning(f"{stale_threshold}일 이상 같은 단계에 머물러 있는 '주의'가 필요한 딜 목록입니다.")
                st.dataframe(stale_deals_df[['Deal name', 'Deal owner', 'Deal Stage', 'Amount', 'Days in Stage']].sort_values('Days in Stage', ascending=False).style.format({'Amount': '${:,.0f}', 'Days in Stage': '{:.0f}일'}), use_container_width=True)
            else:
                st.success("선택된 조건에 해당하는 장기 체류 딜이 없습니다. 👍")
        else:
            st.error("'Date Entered Stage' 컬럼이 날짜 형식이 아니어서 '장기 체류 딜'을 계산할 수 없습니다.")
    else:
        st.warning("'장기 체류 딜' 분석을 위해서는 HubSpot에서 'hs_v2_date_entered_current_stage' 속성을 포함하여 가져와야 합니다.")

with tab4:
    st.header("실패 및 드랍 딜 회고")
    lost_dropped_deals = df[df['Deal Stage'].isin(lost_stages)]
    if not lost_dropped_deals.empty:
        sorted_deals = lost_dropped_deals.sort_values(by='Last Modified Date', ascending=False)
        display_cols = ['Deal name', 'Deal owner', 'Amount', 'Deal Stage', 'Last Modified Date', 'Failure Reason', 'Dropped Reason', 'Dropped Reason (Remark)']
        existing_display_cols = [col for col in display_cols if col in sorted_deals.columns]
        st.dataframe(sorted_deals[existing_display_cols].style.format({'Amount': '${:,.0f}'}), use_container_width=True)
    else:
        st.info("'Closed Lost', 'Dropped', 'Lost', 'Cancel' 상태의 딜이 없습니다.")
