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
ALL_PICS = ['All'] + sorted(BDR_NAMES + AE_NAMES)

# --- Deal Stage ID 매핑 (HubSpot 계정 설정에 따라 달라질 수 있음) ---
DEAL_STAGE_MAPPING = {
    '109960046': 'Prospecting',
    '108877850': 'Proposal Submitted',
    'qualifiedtobuy': 'Qualified To Buy',
    'decisionmakerboughtin': 'Decision Maker Bought-In',
    'closedwon': 'Closed Won',
    'closedlost': 'Closed Lost',
    '108159780': 'Closing',
    '129259600': 'Follow Up',
    '998897767': 'Follow Up',
    'appointmentscheduled': 'Appointment Scheduled',
    '998897766': 'Qualified',
    '108159779': 'Negotiation',
    '998897768': 'Follow Up',
    '1079056027': 'Lost',
    'unassigned': 'Unassigned',
    'qualified': 'Qualified',
    'prospecting': 'Prospecting'
}

# --- 데이터 로딩 및 캐싱 ---
@st.cache_data(ttl=3600, show_spinner=False) # 캐시 유지 시간을 1시간(3600초)으로 설정
def load_data_from_hubspot():
    """
    HubSpot API를 통해 Deals 데이터를 불러오고 전처리합니다.
    Deal Stage, Owner ID 등의 매핑을 적용하고, 우리 팀의 Deal만 필터링합니다.
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

    owner_id_to_name = {}
    with st.spinner("HubSpot에서 Owner 정보를 불러오는 중입니다..."):
        try:
            all_owners = hubspot_client.crm.owners.get_all()
            owner_id_to_name = {
                owner.id: f"{owner.first_name or ''} {owner.last_name or ''}".strip()
                for owner in all_owners
            }
        except OwnersApiException as e:
            st.error(f"HubSpot Owners API 호출 중 오류 발생: {e.body}")
            return None
        except Exception as e:
            st.error(f"Owner 데이터 로딩 중 예상치 못한 오류 발생: {e}")
            return None

    if not owner_id_to_name:
        st.error("Owner 정보를 가져오지 못했습니다. API 권한을 확인하세요.")
        return None

    properties_to_fetch = [
        "dealname", "dealstage", "amount", "createdate", "closedate",
        "lastmodifieddate", "hubspot_owner_id", "bdr", "hs_lost_reason",
        "close_lost_reason", "dropped_reason_remark", "contract_sent_date",
        "meeting_booked_date", "meeting_done_date", "contract_signed_date",
        "payment_complete_date", "hs_expected_close_date",
        "hs_time_in_current_stage"
    ]

    all_deals = []
    with st.spinner("HubSpot에서 모든 Deal 데이터를 불러오는 중입니다..."):
        try:
            all_deals_from_api = hubspot_client.crm.deals.get_all(properties=properties_to_fetch)
            all_deals = [deal.to_dict() for deal in all_deals_from_api]
        except ApiException as e:
            st.error(f"HubSpot Deals API 호출 중 오류 발생: {e.body}")
            return None
        except Exception as e:
            st.error(f"데이터 로딩 중 예상치 못한 오류 발생: {e}")
            return None

    if not all_deals:
        st.warning("HubSpot에서 불러올 Deal 데이터가 없습니다.")
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
            'payment_complete_date', 'hs_expected_close_date', 'lastmodifieddate', 
            'meeting_booked_date', 'meeting_done_date'
        ]
        korea_tz = pytz.timezone('Asia/Seoul')
        for col in date_cols:
            if col in df.columns:
                # 📌 오류 수정: 날짜를 UTC 기준으로 인식(localize)한 후, 서울 시간으로 변환(convert)
                df[col] = pd.to_datetime(df[col], errors='coerce', utc=True).dt.tz_convert(korea_tz)
        
        if 'hs_time_in_current_stage' in df.columns:
            df['hs_time_in_current_stage'] = pd.to_numeric(df['hs_time_in_current_stage'], errors='coerce') / (86400000)
        
        rename_map = {
            'dealname': 'Deal name', 'dealstage': 'Deal Stage', 'amount': 'Amount',
            'createdate': 'Create Date', 'closedate': 'Close Date', 'lastmodifieddate': 'Last Modified Date',
            'bdr': 'BDR_ID', 'hs_time_in_current_stage': 'Days in Stage',
            'hs_expected_close_date': 'Expected Closing Date', 'hs_lost_reason': 'Failure Reason',
            'close_lost_reason': 'Close lost reason', 'dropped_reason_remark': 'Dropped Reason (Remark)',
            'contract_sent_date': 'Contract Sent Date', 'meeting_booked_date': 'Meeting Booked Date',
            'meeting_done_date': 'Meeting Done Date', 'contract_signed_date': 'Contract Signed Date',
            'payment_complete_date': 'Payment Complete Date'
        }
        df.rename(columns=rename_map, inplace=True)
        
        df['Effective Close Date'] = df['Close Date'].fillna(df['Expected Closing Date'])

        df = df[(df['Deal owner'].isin(AE_NAMES)) | (df['BDR'].isin(BDR_NAMES))].copy()

    return df

# --- Streamlit UI 시작 ---

st.title("🎯8월_AUG_Augment, Upgrade, Grow")
st.markdown("HubSpot Live! 팀의 영업 현황을 진단하고, 데이터를 기반으로 **성장 전략**을 수립합니다.")

df = load_data_from_hubspot()

if df is None:
    st.stop()
if df.empty:
    st.info("HubSpot에서 우리 팀에 해당하는 Deal 데이터를 찾을 수 없습니다.")
    st.stop()

# --- 사이드바: 파일 업로드 및 필터 ---
with st.sidebar:
    st.header("⚙️ 설정")
    st.success(f"데이터 로딩 완료! (총 {len(df)}개 Deal)")
    
    csv_data = df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        label="📥 HubSpot DEAL LIST 다운로드",
        data=csv_data,
        file_name=f"hubspot_deals_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

    sales_quota = st.number_input("분기/월별 Sales Quota (목표 매출, USD)", min_value=0, value=500000, step=10000)
    st.markdown("---")
    
    filter_type = st.radio(
        "**날짜 필터 기준 선택**",
        ('생성일 기준 (Create Date)', '마감일 기준 (Effective Close Date)', '최종 수정일 기준 (Last Modified Date)'),
        help="**생성일 기준:** 특정 기간에 생성된 딜 분석\n\n**마감일 기준:** 특정 기간에 마감되었거나 마감될 딜 분석\n\n**최종 수정일 기준:** 특정 기간에 업데이트된 딜 분석"
    )

    filter_col_map = {
        '생성일 기준 (Create Date)': 'Create Date',
        '마감일 기준 (Effective Close Date)': 'Effective Close Date',
        '최종 수정일 기준 (Last Modified Date)': 'Last Modified Date'
    }
    filter_col = filter_col_map[filter_type]

    if df[filter_col].notna().any():
        min_date = df[filter_col].min().date()
        max_date = df[filter_col].max().date()
        date_range = st.date_input(
            f"'{filter_col}' 범위 선택",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    else:
        st.error(f"'{filter_col}' 컬럼에 유효한 날짜 데이터가 없어 필터링할 수 없습니다.")
        st.stop()

# --- 메인 대시보드 영역 ---
korea_tz = pytz.timezone('Asia/Seoul')
start_date = korea_tz.localize(datetime.combine(date_range[0], datetime.min.time()))
end_date = korea_tz.localize(datetime.combine(date_range[1], datetime.max.time()))

base_df = df[(df[filter_col].notna()) & (df[filter_col] >= start_date) & (df[filter_col] <= end_date)].copy()

if base_df.empty:
    st.warning("선택된 기간 및 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# Deal Stage 그룹 정의
won_stages = ['Closed Won', 'Contract Signed', 'Payment Complete']
lost_stages = ['Closed Lost', 'Dropped', 'Lost']
open_stages = [stage for stage in base_df['Deal Stage'].unique() if stage not in won_stages + lost_stages]

# 탭 구성
tab1, tab2, tab3, tab4 = st.tabs(["🚀 통합 대시보드", "🧑‍💻 담당자별 상세 분석", "⚠️ 기회 & 리스크 관리", "📉 실패/드랍 분석"])

with tab1:
    st.header("팀 전체 현황 요약")
    
    won_deals_total = base_df[base_df['Deal Stage'].isin(won_stages)]
    lost_deals_total = base_df[base_df['Deal Stage'].isin(lost_stages)]
    open_deals_total = base_df[base_df['Deal Stage'].isin(open_stages)]

    total_revenue = won_deals_total['Amount'].sum()
    num_won_deals = len(won_deals_total)
    num_lost_deals = len(lost_deals_total)
    
    win_rate = num_won_deals / (num_won_deals + num_lost_deals) if (num_won_deals + num_lost_deals) > 0 else 0
    avg_deal_value = total_revenue / num_won_deals if num_won_deals > 0 else 0

    if not won_deals_total.empty and 'Close Date' in won_deals_total.columns and 'Create Date' in won_deals_total.columns:
        valid_cycle_deals = won_deals_total.dropna(subset=['Close Date', 'Create Date'])
        valid_cycle_deals = valid_cycle_deals.copy()
        valid_cycle_deals['Sales Cycle'] = (valid_cycle_deals['Close Date'] - valid_cycle_deals['Create Date']).dt.days
        avg_sales_cycle = valid_cycle_deals['Sales Cycle'][valid_cycle_deals['Sales Cycle'] >= 0].mean()
    else:
        avg_sales_cycle = 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 매출 (USD)", f"${total_revenue:,.0f}")
    col2.metric("승률 (Win Rate)", f"{win_rate:.2%}")
    col3.metric("평균 계약 금액 (USD)", f"${avg_deal_value:,.0f}")
    col4.metric("평균 영업 사이클", f"{avg_sales_cycle:.1f} 일" if pd.notna(avg_sales_cycle) and avg_sales_cycle > 0 else "N/A")

    st.markdown("---")
    st.subheader("파이프라인 효율성 분석")
    
    col1, col2 = st.columns([1,1])
    with col1:
        st.markdown("**단계별 전환율 (Funnel)**")
        funnel_stages_map = {
            'Meeting Booked': 'Meeting Booked Date',
            'Meeting Done': 'Meeting Done Date',
            'Contract Sent': 'Contract Sent Date',
            'Closed Won': 'Close Date'  
        }
        funnel_data = []
        initial_count = len(base_df)
        funnel_data.append({'Stage': 'Total Deals', 'Count': initial_count})

        for stage, date_col in funnel_stages_map.items():
            if date_col in base_df.columns:
                count = base_df[base_df['Deal Stage'].isin(won_stages)][date_col].notna().sum() if stage == 'Closed Won' else base_df[date_col].notna().sum()
                funnel_data.append({'Stage': stage, 'Count': count})

        if len(funnel_data) > 1:
            funnel_df = pd.DataFrame(funnel_data)
            fig_funnel = go.Figure(go.Funnel(
                y=funnel_df['Stage'], x=funnel_df['Count'],
                textposition="inside", textinfo="value+percent previous"))
            st.plotly_chart(fig_funnel, use_container_width=True)
        else:
            st.error("Funnel 차트를 그리기에 데이터가 부족합니다.")
            st.info("Funnel 차트는 'Meeting Booked Date', 'Meeting Done Date', 'Contract Sent Date', 'Close Date' 컬럼의 데이터가 필요합니다. HubSpot 데이터를 업데이트 해주세요.")
            
    with col2:
        st.markdown("**단계별 평균 소요 시간 (일)**")
        temp_df = base_df.copy()
        date_cols_for_won = ['Close Date', 'Contract Signed Date', 'Payment Complete Date']
        existing_won_date_cols = [col for col in date_cols_for_won if col in temp_df.columns and temp_df[col].notna().any()]
        
        if existing_won_date_cols:
            temp_df['Deal Won Date'] = temp_df[existing_won_date_cols].min(axis=1, skipna=True)

        stage_transitions = [
            {'label': 'Create → Meeting Booked', 'start': 'Create Date', 'end': 'Meeting Booked Date'},
            {'label': 'Booked → Meeting Done', 'start': 'Meeting Booked Date', 'end': 'Meeting Done Date'},
            {'label': 'Done → Contract Sent', 'start': 'Meeting Done Date', 'end': 'Contract Sent Date'},
            {'label': 'Sent → Deal Won', 'start': 'Contract Sent Date', 'end': 'Deal Won Date'}
        ]

        avg_times = []
        for transition in stage_transitions:
            start_col, end_col = transition['start'], transition['end']
            df_to_use = temp_df if end_col == 'Deal Won Date' else base_df

            if start_col in df_to_use.columns and end_col in df_to_use.columns:
                valid_deals = df_to_use.dropna(subset=[start_col, end_col])
                if not valid_deals.empty:
                    time_diff = (valid_deals[end_col] - valid_deals[start_col]).dt.days
                    avg_days = time_diff[time_diff >= 0].mean()
                    if pd.notna(avg_days):
                        avg_times.append({'Transition': transition['label'], 'Avg Days': avg_days})

        if avg_times:
            time_df = pd.DataFrame(avg_times).sort_values('Avg Days', ascending=True)
            fig_time = px.bar(time_df, x='Avg Days', y='Transition', orientation='h', text='Avg Days')
            fig_time.update_traces(texttemplate='%{text:.1f}일', textposition='outside')
            fig_time.update_layout(yaxis_title=None, xaxis_title="평균 소요 일수")
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.info("단계별 소요 시간을 계산할 데이터가 부족합니다. 각 단계별 날짜 데이터가 입력되었는지 확인해주세요.")


with tab2:
    selected_pic = st.selectbox("분석할 담당자를 선택하세요.", ALL_PICS, key="pic_selector")
    
    if selected_pic == 'All':
        st.header("팀 전체 담당자별 성과 비교")
        display_df = base_df
    else:
        st.header(f"'{selected_pic}' 상세 분석")
        if selected_pic in AE_NAMES:
            display_df = base_df[base_df['Deal owner'] == selected_pic]
        elif selected_pic in BDR_NAMES:
            display_df = base_df[base_df['BDR'] == selected_pic]

    if display_df.empty:
        st.info("선택된 조건에 해당하는 담당자의 데이터가 없습니다.")
        st.stop()
    
    if selected_pic == 'All' or selected_pic in AE_NAMES:
        st.subheader("AE Leaderboard")
        ae_base_df = base_df[base_df['Deal owner'].isin(AE_NAMES)]
        if not ae_base_df.empty:
            ae_stats = ae_base_df.groupby('Deal owner').apply(lambda x: pd.Series({
                'Deals Won': (x['Deal Stage'].isin(won_stages)).sum(),
                'Deals Lost': (x['Deal Stage'].isin(lost_stages)).sum(),
                'Meetings Done': x['Meeting Done Date'].notna().sum(),
                'Total Revenue': x.loc[x['Deal Stage'].isin(won_stages), 'Amount'].sum(),
            })).reset_index()
            ae_stats['Win Rate'] = (ae_stats['Deals Won'] / (ae_stats['Deals Won'] + ae_stats['Deals Lost'])).fillna(0)
            ae_stats['Conversion (Meeting→Won)'] = (ae_stats['Deals Won'] / ae_stats['Meetings Done']).fillna(0)
            
            st.dataframe(ae_stats.sort_values(by='Total Revenue', ascending=False).style.format({
                'Total Revenue': '${:,.0f}', 
                'Win Rate': '{:.2%}',
                'Conversion (Meeting→Won)': '{:.2%}'
            }), use_container_width=True, hide_index=True)
        else:
            st.info("선택된 조건에 AE 데이터가 없습니다.")

    if selected_pic == 'All' or selected_pic in BDR_NAMES:
        st.subheader("BDR Leaderboard")
        bdr_base_df = base_df[base_df['BDR'].isin(BDR_NAMES)]
        if not bdr_base_df.empty:
            bdr_stats = bdr_base_df.groupby('BDR').apply(lambda x: pd.Series({
                'Deals Created': len(x),
                'Meetings Booked': x['Meeting Booked Date'].notna().sum(),
            })).reset_index()
            bdr_stats['Conversion (Create→Booked)'] = (bdr_stats['Meetings Booked'] / bdr_stats['Deals Created']).fillna(0)
            
            st.dataframe(bdr_stats.sort_values(by='Meetings Booked', ascending=False).style.format({
                'Conversion (Create→Booked)': '{:.2%}'
            }), use_container_width=True, hide_index=True)
        else:
            st.info("선택된 조건에 BDR 데이터가 없습니다.")


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
        st.subheader("👀 장기 체류 딜 (Stale Deals)")
        st.markdown("특정 기간 이상 같은 단계에 머물러 있는 딜 목록입니다.")
        stale_threshold = st.slider("며칠 이상 머물면 '장기 체류'로 볼까요?", 7, 90, 30, key='stale_slider_tab3')
        
        if 'Days in Stage' in base_df.columns:
            stale_deals_df = base_df[(base_df['Deal Stage'].isin(open_stages)) & (base_df['Days in Stage'] > stale_threshold)]
            if not stale_deals_df.empty:
                st.dataframe(stale_deals_df[['Deal name', 'Deal owner', 'Deal Stage', 'Amount', 'Days in Stage']].sort_values('Days in Stage', ascending=False).style.format({'Amount': '${:,.0f}', 'Days in Stage': '{:.1f}일'}), use_container_width=True, hide_index=True)
            else:
                st.success(f"{stale_threshold}일 이상 장기 체류 중인 딜이 없습니다. 👍")
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
            
            fig = px.pie(reason_counts, values='Count', names='Reason', title='실패/드랍 사유 분포')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("실패/드랍 사유 데이터가 충분하지 않습니다. HubSpot에 데이터를 입력해주세요.")

        st.subheader("실패/드랍 딜 상세 목록 (최신순)")
        display_cols = ['Deal name', 'Deal owner', 'Amount', 'Deal Stage', 'Last Modified Date', reason_col]
        existing_display_cols = [col for col in display_cols if col in lost_dropped_deals.columns]
        st.dataframe(lost_dropped_deals.sort_values(by='Last Modified Date', ascending=False)[existing_display_cols].style.format({'Amount': '${:,.0f}'}), use_container_width=True, hide_index=True)
    else:
        st.success("선택된 기간에 실패 또는 드랍된 딜이 없습니다.")
