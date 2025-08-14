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

# --- 담당자 리스트 (우리 팀에 해당하는 인원만 정의) ---
BDR_NAMES = ['Sohee (Blair) Kim', 'Soorim Yu', 'Gyeol Jang', 'Minyoung Kim']
AE_NAMES = ['Seheon Bok', 'Buheon Shin', 'Ethan Lee', 'Iseul Lee', 'Samin Park', 'Haran Bae']

# --- Deal Stage ID 매핑 ---
DEAL_STAGE_MAPPING = {
    '109960046': 'Prospecting', '108877850': 'Proposal Submitted', 'qualifiedtobuy': 'Qualified To Buy',
    'decisionmakerboughtin': 'Decision Maker Bought-In', 'closedwon': 'Closed Won', 'closedlost': 'Closed Lost',
    '108159780': 'Closing', '129259600': 'Follow Up', '998897767': 'Follow Up',
    'appointmentscheduled': 'Appointment Scheduled', '998897766': 'Qualified', '108159779': 'Negotiation',
    '998897768': 'Follow Up', '1079056027': 'Lost', 'unassigned': 'Unassigned',
    'qualified': 'Qualified', 'prospecting': 'Prospecting'
}

# --- 데이터 로딩 및 캐싱 ---
@st.cache_data(ttl=3600, show_spinner=False)
def load_data_from_hubspot():
    """
    HubSpot API를 통해 Deals 데이터를 불러오고 전처리합니다.
    Owner 정보와 Deal 정보를 가져와서 하나의 DataFrame으로 만듭니다.
    """
    try:
        access_token = st.secrets["HUBSPOT_ACCESS_TOKEN"]
        hubspot_client = HubSpot(access_token=access_token)
    except KeyError:
        st.error("HubSpot 접근 토큰이 설정되지 않았습니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
        return None
    except Exception as e:
        st.error(f"HubSpot 클라이언트 초기화 중 오류 발생: {e}")
        return None

    with st.spinner("HubSpot에서 Owner 정보를 불러오는 중입니다..."):
        try:
            all_owners = hubspot_client.crm.owners.get_all()
            owner_id_to_name = {owner.id: f"{owner.first_name or ''} {owner.last_name or ''}".strip() for owner in all_owners}
        except OwnersApiException as e:
            st.error(f"HubSpot Owners 정보를 가져오는 데 실패했습니다: {e.body}")
            return None
        except Exception as e:
            st.error(f"Owner 정보 로딩 중 오류 발생: {e}")
            return None

    properties_to_fetch = [
        "dealname", "dealstage", "amount", "createdate", "closedate", "hs_lastmodifieddate",
        "hubspot_owner_id", "bdr", "hs_lost_reason", "contract_sent_date", "meeting_booked_date",
        "meeting_done_date", "contract_signed_date", "payment_complete_date",
        "hs_expected_close_date", "hs_time_in_current_stage"
    ]

    with st.spinner("HubSpot에서 모든 Deal 데이터를 불러오는 중입니다..."):
        try:
            all_deals_from_api = hubspot_client.crm.deals.get_all(properties=properties_to_fetch)
            all_deals = [deal.to_dict() for deal in all_deals_from_api]
        except ApiException as e:
            st.error(f"HubSpot Deal 정보를 가져오는 데 실패했습니다: {e.body}")
            return None
        except Exception as e:
            st.error(f"Deal 정보 로딩 중 오류 발생: {e}")
            return None

    if not all_deals:
        return pd.DataFrame()

    df = pd.DataFrame([deal['properties'] for deal in all_deals])

    if not df.empty:
        for col in properties_to_fetch:
            if col not in df.columns:
                df[col] = pd.NaT if 'date' in col else None

        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        df['dealstage'] = df['dealstage'].astype(str).map(DEAL_STAGE_MAPPING).fillna(df['dealstage'])
        df['Deal owner'] = df['hubspot_owner_id'].astype(str).map(owner_id_to_name).fillna('Unassigned')
        df['BDR'] = df['bdr'].astype(str).map(owner_id_to_name).fillna('Unassigned')

        date_cols = [
            'closedate', 'createdate', 'contract_sent_date', 'contract_signed_date',
            'payment_complete_date', 'hs_expected_close_date', 'hs_lastmodifieddate',
            'meeting_booked_date', 'meeting_done_date'
        ]
        korea_tz = pytz.timezone('Asia/Seoul')
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce', utc=True).dt.tz_convert(korea_tz)

        if 'hs_time_in_current_stage' in df.columns:
            df['hs_time_in_current_stage'] = pd.to_numeric(df['hs_time_in_current_stage'], errors='coerce') / 86400000

        rename_map = {
            'dealname': 'Deal name', 'dealstage': 'Deal Stage', 'amount': 'Amount',
            'createdate': 'Create Date', 'closedate': 'Close Date', 'hs_lastmodifieddate': 'Last Modified Date',
            'hs_time_in_current_stage': 'Days in Stage', 'hs_expected_close_date': 'Expected Closing Date',
            'hs_lost_reason': 'Failure Reason', 'contract_sent_date': 'Contract Sent Date',
            'meeting_booked_date': 'Meeting Booked Date', 'meeting_done_date': 'Meeting Done Date',
            'contract_signed_date': 'Contract Signed Date', 'payment_complete_date': 'Payment Complete Date'
        }
        df.rename(columns=rename_map, inplace=True)

        df['Effective Close Date'] = df['Close Date'].fillna(df['Expected Closing Date'])
        df = df[(df['Deal owner'].isin(AE_NAMES)) | (df['BDR'].isin(BDR_NAMES))].copy()
        
    return df

# --- Streamlit UI 시작 ---
st.title("🎯 GS KR Sales Dashboard")
st.markdown("HubSpot Live! 팀의 영업 현황을 진단하고, 데이터를 기반으로 **성장 전략**을 수립합니다.")
df = load_data_from_hubspot()

if df is None or df.empty:
    st.info("HubSpot에서 분석할 데이터를 찾을 수 없습니다.")
    st.stop()

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    st.success(f"데이터 로딩 완료! (총 {len(df)}개 Deal)")
    csv_data = df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button("📥 DEAL LIST 다운로드", csv_data, f"hubspot_deals_{datetime.now().strftime('%Y%m%d')}.csv")
    sales_quota = st.number_input("분기/월별 Sales Quota (USD)", value=500000, step=10000)
    st.markdown("---")
    filter_type = st.radio("**날짜 필터 기준**", ('생성일 기준 (Create Date)', '마감일 기준 (Effective Close Date)', '최종 수정일 기준 (Last Modified Date)'))
    filter_col_map = {'생성일 기준 (Create Date)': 'Create Date', '마감일 기준 (Effective Close Date)': 'Effective Close Date', '최종 수정일 기준 (Last Modified Date)': 'Last Modified Date'}
    filter_col = filter_col_map[filter_type]
    if df[filter_col].notna().any():
        min_date, max_date = df[filter_col].min().date(), df[filter_col].max().date()
        date_range = st.date_input(f"'{filter_col}' 범위 선택", (min_date, max_date), min_date, max_date)
    else:
        st.error(f"'{filter_col}'에 유효한 데이터가 없어 필터링할 수 없습니다.")
        st.stop()

# --- 데이터 필터링 ---
korea_tz = pytz.timezone('Asia/Seoul')
start_date = korea_tz.localize(datetime.combine(date_range[0], datetime.min.time()))
end_date = korea_tz.localize(datetime.combine(date_range[1], datetime.max.time()))
base_df = df[df[filter_col].notna() & (df[filter_col] >= start_date) & (df[filter_col] <= end_date)].copy()
if base_df.empty:
    st.warning("선택된 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# --- 메인 대시보드 ---
won_stages = ['Closed Won', 'Contract Signed', 'Payment Complete']
lost_stages = ['Closed Lost', 'Dropped', 'Lost']
open_stages = [stage for stage in base_df['Deal Stage'].unique() if stage not in won_stages + lost_stages]

# 모든 탭을 포함하여 생성
tab1, tab2, tab3, tab4 = st.tabs(["🚀 통합 대시보드", "🧑‍💻 담당자별 상세 분석", "⚠️ 기회 & 리스크 관리", "📉 실패/드랍 분석"])

with tab1:
    st.header("팀 전체 현황 요약")
    won_deals_total = base_df[base_df['Deal Stage'].isin(won_stages)]
    lost_deals_total = base_df[base_df['Deal Stage'].isin(lost_stages)]
    total_revenue = won_deals_total['Amount'].sum()
    num_won_deals = len(won_deals_total)
    num_lost_deals = len(lost_deals_total)
    win_rate = num_won_deals / (num_won_deals + num_lost_deals) if (num_won_deals + num_lost_deals) > 0 else 0
    avg_deal_value = total_revenue / num_won_deals if num_won_deals > 0 else 0
    
    avg_sales_cycle = pd.NA
    if not won_deals_total.empty:
        valid_cycle_deals = won_deals_total.dropna(subset=['Create Date', 'Close Date'])
        if not valid_cycle_deals.empty:
            sales_cycles = (valid_cycle_deals['Close Date'] - valid_cycle_deals['Create Date']).dt.days
            avg_sales_cycle = sales_cycles[sales_cycles >= 0].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 매출 (USD)", f"${total_revenue:,.0f}")
    col2.metric("승률 (Win Rate)", f"{win_rate:.2%}")
    col3.metric("평균 계약 금액 (USD)", f"${avg_deal_value:,.0f}")
    col4.metric("평균 영업 사이클", f"{avg_sales_cycle:.1f} 일" if pd.notna(avg_sales_cycle) else "N/A")

    st.markdown("---")
    st.subheader("파이프라인 분석")
    # ... (tab1의 나머지 코드는 이전과 동일)

with tab2:
    st.header("담당자별 상세 분석")
    st.subheader("AE Leaderboard")
    # ... (tab2의 코드는 이전과 동일)

with tab3:
    st.header("기회 및 리스크 관리")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💰 Top 10 Open Deals (기회)")
        st.markdown("현재 진행 중인 딜 중 가장 금액이 큰 Top 10 입니다.")
        top_deals = base_df[base_df['Deal Stage'].isin(open_stages)].sort_values('Amount', ascending=False).head(10)
        if not top_deals.empty:
            st.dataframe(top_deals[['Deal name', 'Deal owner', 'Amount', 'Deal Stage']].style.format({'Amount': '${:,.0f}'}), use_container_width=True, hide_index=True)
        else:
            st.info("진행 중인 딜이 없습니다.")
    
    with col2:
        st.subheader("📝 계약서 발송 후 정체된 딜")
        st.markdown("계약서 발송 후 아직 성사/실패가 결정되지 않은 딜입니다.")
        contract_sent_deals = df[
            (df['Contract Sent Date'].notna()) &
            (~df['Deal Stage'].isin(won_stages + lost_stages))
        ].sort_values('Amount', ascending=False)
        if not contract_sent_deals.empty:
            today = datetime.now(korea_tz)
            contract_sent_deals['Days Since Sent'] = (today - contract_sent_deals['Contract Sent Date']).dt.days
            st.dataframe(
                contract_sent_deals[['Deal name', 'Deal owner', 'Amount', 'Days Since Sent']].style.format({'Amount': '${:,.0f}'}),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("현재 계약서 발송 후 진행 중인 딜이 없습니다.")

    st.markdown("---")
    st.subheader("👀 장기 체류 딜 (Stale Deals) 관리")
    stale_threshold = st.slider("며칠 이상 같은 단계에 머물면 '장기 체류'로 볼까요?", 7, 90, 30)
    if 'Days in Stage' in base_df.columns:
        stale_deals_df = base_df[(base_df['Deal Stage'].isin(open_stages)) & (base_df['Days in Stage'] > stale_threshold)]
        if not stale_deals_df.empty:
            st.warning(f"{stale_threshold}일 이상 같은 단계에 머물러 주의가 필요한 딜 목록입니다.")
            st.dataframe(stale_deals_df[['Deal name', 'Deal owner', 'Deal Stage', 'Amount', 'Days in Stage']].sort_values('Days in Stage', ascending=False).style.format({'Amount': '${:,.0f}', 'Days in Stage': '{:.1f}일'}), use_container_width=True, hide_index=True)
        else:
            st.success(f"선택된 조건에 장기 체류 딜이 없습니다. 👍")
    else:
        st.warning("'장기 체류 딜' 분석을 위해서는 HubSpot에서 'hs_time_in_current_stage' 속성을 가져와야 합니다.")

with tab4:
    st.header("실패 및 드랍 딜 회고")
    lost_dropped_deals = base_df[base_df['Deal Stage'].isin(lost_stages)]

    if not lost_dropped_deals.empty:
        st.subheader("실패/드랍 사유 분석")
        reason_col = 'Failure Reason'
        if reason_col in lost_dropped_deals.columns and lost_dropped_deals[reason_col].notna().any():
            reason_counts = lost_dropped_deals[reason_col].value_counts().reset_index()
            reason_counts.columns = ['Reason', 'Count']
            fig = px.pie(reason_counts, values='Count', names='Reason', title='실패/드랍 사유 분포', hole=0.3)
            fig.update_traces(textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("실패/드랍 사유 데이터가 충분하지 않습니다. HubSpot에 데이터를 입력해주세요.")

        st.subheader("실패/드랍 딜 상세 목록 (최신순)")
        display_cols = ['Deal name', 'Deal owner', 'Amount', 'Deal Stage', 'Last Modified Date', reason_col]
        existing_display_cols = [col for col in display_cols if col in lost_dropped_deals.columns]
        st.dataframe(
            lost_dropped_deals.sort_values(by='Last Modified Date', ascending=False)[existing_display_cols].style.format({'Amount': '${:,.0f}'}),
            use_container_width=True, hide_index=True
        )
    else:
        st.success("선택된 기간에 실패 또는 드랍된 딜이 없습니다.")
