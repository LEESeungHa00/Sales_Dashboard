import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from hubspot import HubSpot
from hubspot.crm.deals.exceptions import ApiException
from hubspot.crm.owners.exceptions import ApiException as OwnersApiException

# --- 페이지 설정 ---
st.set_page_config(layout="wide", page_title="GS KR Sales Dashboard")

# --- 담당자 리스트 ---
BDR_NAMES = ['Sohee (Blair) Kim', 'Soorim Yu', 'Gyeol Jang', 'Minyoung Kim']
AE_NAMES = ['Seheon Bok', 'Buheon Shin', 'Ethan Lee', 'Iseul Lee', 'Samin Park', 'Haran Bae']
ALL_PICS = ['All'] + sorted(BDR_NAMES + AE_NAMES)

# --- 데이터 로딩 및 캐싱 ---
@st.cache_data(ttl=3600) # 1시간마다 데이터 새로고침
def load_data_from_hubspot():
    """
    HubSpot API를 통해 Deals 데이터를 불러오고 전처리합니다.
    """
    try:
        # Streamlit Secrets에서 HubSpot 접근 토큰 가져오기
        access_token = st.secrets["HUBSPOT_ACCESS_TOKEN"]
        hubspot_client = HubSpot(access_token=access_token)
    except KeyError:
        st.error("HubSpot 접근 토큰이 설정되지 않았습니다. Streamlit Cloud의 Secrets 설정을 확인하세요.")
        return None
    except Exception as e:
        st.error(f"HubSpot 클라이언트 초기화 중 오류 발생: {e}")
        return None

    all_deals = []
    after = None
    
    # 대시보드에 필요한 모든 속성 정의
    properties_to_fetch = [
        "dealname", "dealstage", "amount", "createdate", "closedate", 
        "lastmodifieddate", "hubspot_owner_id", "bdr", "hs_lost_reason",
        "close_lost_reason", "dropped_reason_remark", "contract_sent_date",
        "meeting_booked_date", "meeting_done_date", "contract_signed_date",
        "payment_complete_date", "hs_expected_close_date", 
        "hs_time_in_current_stage"
    ]

    # 페이지네이션을 통해 모든 Deal 데이터 가져오기
    with st.spinner("HubSpot에서 모든 Deal 데이터를 불러오는 중입니다... (시간이 걸릴 수 있습니다)"):
        try:
            while True:
                page = hubspot_client.crm.deals.basic_api.get_page(
                    limit=100,
                    after=after,
                    properties=properties_to_fetch,
                    archived=False
                )
                all_deals.extend(page.results)
                if page.paging and page.paging.next:
                    after = page.paging.next.after
                else:
                    break
        except ApiException as e:
            st.error(f"HubSpot API에서 데이터를 가져오는 중 오류가 발생했습니다: {e.reason}")
            return None

    if not all_deals:
        st.warning("HubSpot에서 불러올 Deal 데이터가 없습니다.")
        return pd.DataFrame() # 빈 데이터프레임 반환

    # API 결과(deal 객체)를 딕셔너리 리스트로 변환
    deals_list = [{'id': deal.id, **deal.to_dict()['properties']} for deal in all_deals]
    df = pd.DataFrame(deals_list)

    # --- 데이터 전처리 ---
    # 컬럼 이름 변경 (API 이름 -> 대시보드에서 사용하는 이름)
    rename_map = {
        'dealname': 'Deal name',
        'dealstage': 'Deal Stage',
        'createdate': 'Create Date',
        'closedate': 'Close Date',
        'lastmodifieddate': 'Last Modified Date',
        'id': 'Record ID',
        'hs_lost_reason': 'hs_lost_reason',
        'close_lost_reason': 'Close Lost Reason',
        'dropped_reason_remark': 'Dropped Reason (Remark)',
        'contract_sent_date': 'Contract Sent Date',
        'meeting_booked_date': 'Meeting Booked Date',
        'meeting_done_date': 'Meeting Done Date',
        'contract_signed_date': 'Contract Signed Date',
        'payment_complete_date': 'Payment Complete Date',
        'hs_expected_close_date': 'Expected Closing Date',
        'hs_time_in_current_stage': 'Time in current stage (HH:mm:ss)'
    }
    df.rename(columns=rename_map, inplace=True)
    
    # HubSpot Owners API를 호출하여 Owner ID와 이름 매핑 생성
    owner_id_to_name = {}
    with st.spinner("HubSpot에서 Owner 정보를 불러오는 중입니다..."):
        try:
            # 이 API 호출을 위해 HubSpot Private App에 'crm.objects.owners.read' 스코프가 필요합니다.
            owners_response = hubspot_client.crm.owners.owners_api.get_page(archived=False)
            owners = owners_response.results
            # Owner ID를 '이름 성' 형태의 전체 이름으로 매핑하는 딕셔너리 생성
            owner_id_to_name = {
                owner.id: f"{owner.first_name or ''} {owner.last_name or ''}".strip()
                for owner in owners
            }
        except OwnersApiException as e:
            # 권한 오류(Forbidden)가 발생하면 사용자에게 명확한 안내 메시지를 표시합니다.
            if e.status == 403:
                st.error("HubSpot Owner 정보를 가져올 권한이 없습니다. Private App의 Scopes에 'crm.objects.owners.read'를 추가하세요.")
            else:
                st.error(f"HubSpot Owners API에서 데이터를 가져오는 중 오류가 발생했습니다: {e.reason}")
            # Owner 정보를 가져오지 못해도 대시보드는 계속 진행되도록 빈 맵을 사용합니다.
            owner_id_to_name = {}


    # Deal Owner ID를 이름으로 변환
    if 'hubspot_owner_id' in df.columns and owner_id_to_name:
        df['Deal owner'] = df['hubspot_owner_id'].map(owner_id_to_name)
        # 매핑되지 않은 경우(예: 삭제된 오너)를 'Unassigned'로 처리
        df['Deal owner'].fillna('Unassigned', inplace=True)
    else:
        # 'hubspot_owner_id' 컬럼이 없거나 owner 정보를 가져오지 못한 경우
        df['Deal owner'] = 'Unassigned'

    # 실패/드랍 사유 통합 컬럼 생성
    df['Failure Reason'] = df.get('hs_lost_reason', pd.Series(index=df.index, dtype=object))
    if 'Close Lost Reason' in df.columns:
        df['Failure Reason'].fillna(df['Close Lost Reason'], inplace=True)
    if 'Dropped Reason (Remark)' in df.columns:
        dropped_mask = df['Deal Stage'] == 'Dropped'
        df.loc[dropped_mask, 'Failure Reason'] = df.loc[dropped_mask, 'Dropped Reason (Remark)']

    # 날짜 컬럼 변환
    date_cols = [
        'Create Date', 'Close Date', 'Contract Sent Date', 'Last Modified Date',
        'Meeting Booked Date', 'Meeting Done Date', 'Contract Signed Date', 'Payment Complete Date',
        'Expected Closing Date'
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.tz_localize(None)

    # 'Effective Close Date' 생성
    if 'Expected Closing Date' in df.columns:
        df['Effective Close Date'] = df['Expected Closing Date'].fillna(df['Close Date'])
    elif 'Close Date' in df.columns:
        df['Effective Close Date'] = df['Close Date']
    else:
        df['Effective Close Date'] = pd.NaT


    # 숫자 및 기타 컬럼 처리
    if 'amount' in df.columns:
        df['Amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    df['BDR'] = df.get('bdr', pd.Series(index=df.index, dtype=object)).fillna('Unassigned')
    
    return df

# --- 시간 변환 함수 ---
def hhmmss_to_days(time_str):
    if pd.isna(time_str): return None
    try:
        # HubSpot의 hs_time_in_current_stage는 밀리초(ms) 단위일 수 있음
        total_seconds = int(time_str) / 1000
        return total_seconds / (24 * 3600)
    except (ValueError, TypeError, IndexError):
        return None

# --- 대시보드 UI ---
st.title("🎯8월_AUG_Augment, Upgrade, Grow")
st.markdown("HubSpot Live! 팀의 영업 현황을 진단하고, 데이터를 기반으로 **성장 전략**을 수립합니다.")

df = load_data_from_hubspot()
# --- 사이드바: 파일 업로드 및 필터 ---
with st.sidebar:
    st.header("⚙️ 설정")
    if df is None:
        st.error("데이터 로딩에 실패했습니다. HubSpot 연결을 확인하세요.")
        st.stop()
    elif df.empty:
        st.info("분석할 데이터가 없습니다.")
        st.stop()
    else:
        st.success("데이터 로딩 완료!")
        sales_quota = st.number_input("분기/월별 Sales Quota (목표 매출, USD) 입력", min_value=0, value=500000, step=10000)
                
        # 날짜 필터 기준 선택
        st.markdown("---")
        filter_type = st.radio(
            "**날짜 필터 기준 선택**",
            ('생성일 기준 (Create Date)', '예상/확정 마감일 기준', '최종 수정일 기준 (Last Modified Date)'),
            help="**생성일 기준:** 특정 기간에 생성된 딜 분석\n\n**예상/확정 마감일 기준:** 특정 기간에 마감될 딜 분석 (Open 딜은 Expected Closing Date 기준)\n\n**최종 수정일 기준:** 특정 기간에 업데이트된 딜 분석"
        )
        st.markdown("---")

        # 선택된 기준에 따라 날짜 범위 설정
        if filter_type == '생성일 기준 (Create Date)':
            filter_col = 'Create Date'
        elif filter_type == '예상/확정 마감일 기준':
            filter_col = 'Effective Close Date'
        else: # 최종 수정일 기준
            filter_col = 'Last Modified Date'
            
        if not df[filter_col].isna().all():
            min_date = df[filter_col].min().date()
            max_date = df[filter_col].max().date()
            date_range = st.date_input(
                f"분석할 '{filter_col}' 범위 선택",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )
        else:
            st.error(f"'{filter_col}' 컬럼에 데이터가 없어 날짜 필터를 설정할 수 없습니다.")
            st.stop()
            

# --- 메인 대시보드 영역 ---
if 'date_range' in locals() and df is not None and not df.empty:
    start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    
    # BDR 및 AE 담당자 딜 필터링 (데이터 로딩 후 필터링)
    unfiltered_df = df.copy() # 디버깅용 원본
    df = df[(df['Deal owner'].isin(AE_NAMES)) | (df['BDR'].isin(BDR_NAMES))].copy()
    if df.empty:
        st.warning("지정된 담당자(AE, BDR)에 해당하는 Deal이 없습니다.")
        st.subheader("API 원본 데이터 확인 (디버깅용)")
        st.info("아래 표의 'Deal owner'와 'BDR' 컬럼에 있는 이름이 코드의 담당자 리스트와 정확히 일치하는지 확인해주세요.")
        st.dataframe(unfiltered_df[['Deal name', 'Deal owner', 'BDR']])
        st.stop()

    base_df = df[(df[filter_col] >= start_date) & (df[filter_col] <= end_date)].copy()
    
    if base_df.empty:
        st.warning("선택된 조건에 해당하는 데이터가 없습니다.")
        st.stop()

    # 계약 성사(Won) 및 실패(Lost) 단계 목록 정의
    won_stages = ['Closed Won', 'Payment Complete', 'Contract Signed']
    lost_stages = ['Closed Lost', 'Dropped']

    
    # --- 탭 구성 ---
    tab1, tab2, tab3, tab4 = st.tabs(["🚀 통합 대시보드", "🧑‍💻 담당자별 상세 분석", "⚠️ 기회 & 리스크 관리", "📉 실패/드랍 분석"])

    # --- Tab 1: 통합 대시보드 ---
    with tab1:
        st.header("팀 전체 현황 요약")
        
        # KPI 계산 (base_df 기준)
        won_deals_total = base_df[base_df['Deal Stage'].isin(won_stages)]
        lost_deals_total = base_df[base_df['Deal Stage'].isin(lost_stages)]
        open_deals_total = base_df[~base_df['Deal Stage'].isin(won_stages + lost_stages)]

        total_revenue = won_deals_total['Amount'].sum()
        num_won_deals = len(won_deals_total)
        num_lost_deals = len(lost_deals_total)
        win_rate = num_won_deals / (num_won_deals + num_lost_deals) if (num_won_deals + num_lost_deals) > 0 else 0
        avg_deal_value = total_revenue / num_won_deals if num_won_deals > 0 else 0
        
        if not won_deals_total.empty and 'Close Date' in won_deals_total.columns and 'Create Date' in won_deals_total.columns:
            won_deals_total.loc[:, 'Sales Cycle'] = (won_deals_total['Close Date'] - won_deals_total['Create Date']).dt.days
            avg_sales_cycle = won_deals_total['Sales Cycle'].mean()
        else:
            avg_sales_cycle = 0

        open_pipeline_amount = open_deals_total['Amount'].sum()
        pipeline_coverage = open_pipeline_amount / sales_quota if sales_quota > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 매출 (USD)", f"${total_revenue:,.0f}")
        col2.metric("승률 (Win Rate)", f"{win_rate:.2%}")
        col3.metric("평균 계약 금액 (USD)", f"${avg_deal_value:,.0f}")
        col4.metric("평균 영업 사이클", f"{avg_sales_cycle:.1f} 일")

        st.markdown("---")
        
        st.subheader("파이프라인 효율성 분석")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**단계별 전환율 (Funnel)**")
            funnel_stages_map = {
                'Meeting Booked': "Meeting Booked Date",
                'Meeting Done': "Meeting Done Date",
                'Contract Sent': "Contract Sent Date",
                'Closed Won': "Close Date" 
            }
            funnel_data = []
            
            for stage, date_col in funnel_stages_map.items():
                if date_col in base_df.columns:
                    # 'Closed Won' 단계는 won_stages에 포함된 딜만 카운트
                    if stage == 'Closed Won':
                        count = base_df[base_df['Deal Stage'].isin(won_stages)][date_col].notna().sum()
                    else:
                        count = base_df[date_col].notna().sum()
                    funnel_data.append({'Stage': stage, 'Count': count})

            if len(funnel_data) > 1:
                funnel_df = pd.DataFrame(funnel_data)
                fig_funnel = go.Figure(go.Funnel(
                    y = funnel_df['Stage'], x = funnel_df['Count'],
                    textposition = "inside", textinfo = "value+percent initial"))
                st.plotly_chart(fig_funnel, use_container_width=True)
            else:
                st.error("Funnel 차트를 그리기에 데이터가 부족합니다.")
                missing_cols = [col for stage, col in funnel_stages_map.items() if col not in base_df.columns]
                if missing_cols:
                    st.warning(f"**아래 컬럼이 파일에 없어 Funnel을 그릴 수 없습니다:**\n\n - " + "\n - ".join(missing_cols))

        with col2:
            st.markdown("**단계별 평균 소요 시간 (일)**")
            
            # 'Deal Won Date' 계산: Close, Signed, Payment 날짜 중 가장 빠른 날짜
            temp_df = base_df.copy()
            done_date_cols = ['Close Date', 'Contract Signed Date', 'Payment Complete Date']
            existing_done_cols = [col for col in done_date_cols if col in temp_df.columns]
            
            if existing_done_cols:
                temp_df['Deal Won Date'] = temp_df[existing_done_cols].min(axis=1)

            stage_transitions = [
                {'label': 'Deal Create → Meeting Booked', 'start': 'Create Date', 'end': 'Meeting Booked Date'},
                {'label': 'Meeting Booked → Meeting Done', 'start': 'Meeting Booked Date', 'end': 'Meeting Done Date'},
                {'label': 'Meeting Done → Contract Sent', 'start': 'Meeting Done Date', 'end': 'Contract Sent Date'},
                {'label': 'Contract Sent → Deal Done', 'start': 'Contract Sent Date', 'end': 'Deal Won Date'}
            ]
            
            avg_times = []
            for transition in stage_transitions:
                start_col, end_col = transition['start'], transition['end']
                
                # end_col이 Deal Won Date일 경우, temp_df를 사용
                df_to_use = temp_df if end_col == 'Deal Won Date' else base_df

                if start_col in df_to_use.columns and end_col in df_to_use.columns:
                    
                    if transition['label'] == 'Contract Sent → Deal Done':
                        target_deals = df_to_use[df_to_use['Deal Stage'].isin(won_stages)]
                    else:
                        target_deals = df_to_use

                    valid_deals = target_deals.dropna(subset=[start_col, end_col])
                    if not valid_deals.empty:
                        time_diff = (valid_deals[end_col] - valid_deals[start_col]).dt.days
                        avg_days = time_diff[time_diff >= 0].mean() # 음수 값 제외
                        if pd.notna(avg_days):
                            avg_times.append({'Transition': transition['label'], 'Avg Days': avg_days})
            
            if avg_times:
                time_df = pd.DataFrame(avg_times)
                fig_time = px.bar(time_df, x='Avg Days', y='Transition', orientation='h', 
                                  title="단계별 평균 소요 시간", text='Avg Days')
                fig_time.update_traces(texttemplate='%{text:.1f}일', textposition='auto')
                # y축 순서를 영업 단계 순서대로 고정
                category_order = [t['label'] for t in stage_transitions]
                fig_time.update_layout(yaxis={'categoryorder':'array', 'categoryarray': category_order})
                st.plotly_chart(fig_time, use_container_width=True)
            else:
                st.info("단계별 소요 시간을 계산할 데이터가 부족합니다. (예: Meeting Booked Date, Meeting Done Date 등)")

    # --- Tab 2: 담당자별 상세 분석 ---
    with tab2:
        selected_pic = st.selectbox("분석할 담당자를 선택하세요.", ALL_PICS)
        st.header(f"'{selected_pic}' 상세 분석")

        # 담당자 선택에 따라 필터링된 DF 생성
        if selected_pic != 'All':
            if selected_pic in AE_NAMES:
                filtered_df = base_df[base_df['Deal owner'] == selected_pic]
            elif selected_pic in BDR_NAMES:
                filtered_df = base_df[base_df['BDR'] == selected_pic]
        else:
            filtered_df = base_df

        if selected_pic == 'All':
            st.info("위 드롭다운 메뉴에서 특정 담당자를 선택하여 개인별 상세 성과를 확인하세요.")
            
            st.subheader("AE Leaderboard")
            ae_base_df = base_df[base_df['Deal owner'].isin(AE_NAMES)]
            if not ae_base_df.empty:
                ae_stats = ae_base_df.groupby('Deal owner').apply(lambda x: pd.Series({
                    'Deals_Won': (x['Deal Stage'].isin(won_stages)).sum(),
                    'Deals_Lost': (x['Deal Stage'].isin(lost_stages)).sum(),
                    'Meetings_Done': x['Meeting Done Date'].notna().sum(),
                    'Total_Revenue': x.loc[x['Deal Stage'].isin(won_stages), 'Amount'].sum(),
                    'Avg_Sales_Cycle': (x.loc[x['Deal Stage'].isin(won_stages), 'Close Date'] - x.loc[x['Deal Stage'].isin(won_stages), 'Create Date']).dt.days.mean() if not x[x['Deal Stage'].isin(won_stages)].empty else 0
                })).reset_index()
                ae_stats['Win_Rate'] = ae_stats['Deals_Won'] / (ae_stats['Deals_Won'] + ae_stats['Deals_Lost'])
                ae_stats['Conversion_Rate (Meeting→Won)'] = ae_stats['Deals_Won'] / ae_stats['Meetings_Done']
                ae_stats = ae_stats.sort_values(by='Total_Revenue', ascending=False).fillna(0)
                
                # 딜 개수를 정수형으로 변환
                ae_stats['Deals_Won'] = ae_stats['Deals_Won'].astype(int)
                ae_stats['Deals_Lost'] = ae_stats['Deals_Lost'].astype(int)
                ae_stats['Meetings_Done'] = ae_stats['Meetings_Done'].astype(int)

                st.dataframe(ae_stats.style.format({
                    'Total_Revenue': '${:,.0f}', 
                    'Avg_Sales_Cycle': '{:.1f}일',
                    'Win_Rate': '{:.2%}',
                    'Conversion_Rate (Meeting→Won)': '{:.2%}'
                }), use_container_width=True, hide_index=True)
            else:
                st.info("선택된 기간에 AE 데이터가 없습니다.")

            st.subheader("BDR Leaderboard")
            bdr_base_df = base_df[base_df['BDR'].isin(BDR_NAMES)]
            if not bdr_base_df.empty:
                bdr_stats = bdr_base_df.groupby('BDR').apply(lambda x: pd.Series({
                    'Deals_Created': len(x),
                    'Meetings_Booked': x['Meeting Booked Date'].notna().sum()
                })).reset_index()
                bdr_stats['Conversion_Rate (Create→Booked)'] = bdr_stats['Meetings_Booked'] / bdr_stats['Deals_Created']
                bdr_stats = bdr_stats.sort_values(by='Meetings_Booked', ascending=False).fillna(0)
                st.dataframe(bdr_stats.style.format({'Conversion_Rate (Create→Booked)': '{:.2%}'}), use_container_width=True, hide_index=True)
            else:
                st.info("선택된 기간에 BDR 데이터가 없습니다.")

        elif selected_pic in BDR_NAMES:
            st.subheader(f"{selected_pic} (BDR) 성과 요약")
            deals_created_count = len(filtered_df)
            meetings_booked_count = filtered_df['Meeting Booked Date'].notna().sum()
            conversion_rate = meetings_booked_count / deals_created_count if deals_created_count > 0 else 0
            
            col1, col2 = st.columns(2)
            col1.metric("총 생성 딜", f"{deals_created_count} 건")
            col2.metric("미팅 확정 건수", f"{meetings_booked_count} 건")
            st.metric("미팅 전환율 (Create → Booked)", f"{conversion_rate:.2%}")
            
            st.markdown("---")
            st.subheader("미팅 확정 딜 목록")
            booked_deals = filtered_df[filtered_df['Meeting Booked Date'].notna()]
            st.dataframe(booked_deals[['Deal name', 'Deal owner', 'Deal Stage', 'Meeting Booked Date']], use_container_width=True)

        elif selected_pic in AE_NAMES:
            # 공통 데이터 계산
            won_deals_pic = filtered_df[filtered_df['Deal Stage'].isin(won_stages)]
            lost_deals_pic = filtered_df[filtered_df['Deal Stage'].isin(lost_stages)]
            open_deals_pic = filtered_df[~filtered_df['Deal Stage'].isin(won_stages + lost_stages)]

            st.subheader(f"{selected_pic} (AE) 성과 요약")
            
            # KPIs
            meetings_done_count = filtered_df['Meeting Done Date'].notna().sum()
            contracts_sent_count = filtered_df['Contract Sent Date'].notna().sum()
            deals_done_count = len(won_deals_pic)
            conversion_rate_ae = deals_done_count / meetings_done_count if meetings_done_count > 0 else 0
            total_revenue_pic = won_deals_pic['Amount'].sum()
            win_rate_pic = deals_done_count / (deals_done_count + len(lost_deals_pic)) if (deals_done_count + len(lost_deals_pic)) > 0 else 0
            avg_deal_value_pic = total_revenue_pic / deals_done_count if deals_done_count > 0 else 0

            col1, col2, col3 = st.columns(3)
            col1.metric("미팅 완료 건수", f"{meetings_done_count} 건")
            col2.metric("계약서 발송 건수", f"{contracts_sent_count} 건")
            col3.metric("계약 성사 건수", f"{deals_done_count} 건")
            
            st.metric("계약 전환율 (Meeting Done → Deal Done)", f"{conversion_rate_ae:.2%}")

            col1, col2, col3 = st.columns(3)
            col1.metric("총 매출 (USD)", f"${total_revenue_pic:,.0f}")
            col2.metric("승률 (Win Rate)", f"{win_rate_pic:.2%}")
            col3.metric("평균 계약 금액 (USD)", f"${avg_deal_value_pic:,.0f}")

            st.markdown("---")
            
            # 담당자별 진행 중인 딜 현황 (Stage별)
            st.subheader("진행 중인 딜 현황 (Stage별)")
            if not open_deals_pic.empty:
                stage_counts = open_deals_pic['Deal Stage'].value_counts().reset_index()
                stage_counts.columns = ['Deal Stage', 'Count']
                fig_stage_dist = px.bar(stage_counts, x='Count', y='Deal Stage', orientation='h', text='Count')
                fig_stage_dist.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_stage_dist, use_container_width=True)
            else:
                st.info("현재 진행 중인 딜이 없습니다.")

            st.subheader("계약 성사 딜 목록")
            if not won_deals_pic.empty:
                st.dataframe(won_deals_pic[['Deal name', 'Amount', 'Close Date']].sort_values(by='Amount', ascending=False), use_container_width=True)
            else:
                st.info("선택된 기간에 계약 성사된 딜이 없습니다.")

            st.subheader("30일 내 마감 예정 딜")
            today = datetime.now()
            thirty_days_later = today + timedelta(days=30)
            
            expected_deals = open_deals_pic[
                (open_deals_pic['Effective Close Date'].notna()) &
                (open_deals_pic['Effective Close Date'] >= pd.to_datetime(today.date())) &
                (open_deals_pic['Effective Close Date'] <= pd.to_datetime(thirty_days_later.date()))
            ].sort_values('Amount', ascending=False)
            
            if not expected_deals.empty:
                expected_deals['Days to Close'] = (expected_deals['Effective Close Date'] - today).dt.days
                st.dataframe(expected_deals[['Deal name', 'Amount', 'Effective Close Date', 'Days to Close']].rename(columns={'Effective Close Date': 'Expected Close Date'}), use_container_width=True)
            else:
                st.info("30일 내 마감 예정인 딜이 없습니다.")


    # --- Tab 3: 기회 & 리스크 관리 ---
    with tab3:
        st.header("주요 딜 관리 및 리스크 분석")

        # "Next Focus" 섹션 수정
        st.subheader("🎯 Next Focus")
        focus_days = st.selectbox(
            "집중할 기간(일)을 선택하세요:",
            (30, 60, 90),
            index=2 # 기본값 90일
        )
        st.markdown(f"오늘로부터 **예상 마감일이 {focus_days}일 이내**인, 금액이 큰 기회 목록입니다.")
        
        today = datetime.now()
        days_later = today + timedelta(days=focus_days)
        
        # 전체 데이터(df)에서 필터링하여 현재 시점의 모든 기회를 확인
        all_open_deals = df[~df['Deal Stage'].isin(won_stages + lost_stages)]
        
        focus_deals = all_open_deals[
            (all_open_deals['Effective Close Date'].notna()) &
            (all_open_deals['Effective Close Date'] >= pd.to_datetime(today.date())) &
            (all_open_deals['Effective Close Date'] <= pd.to_datetime(days_later.date()))
        ].sort_values('Amount', ascending=False)
        
        if not focus_deals.empty:
            focus_deals['Days to Close'] = (focus_deals['Effective Close Date'] - today).dt.days
            st.dataframe(focus_deals[['Deal name', 'Deal owner', 'Amount', 'Effective Close Date', 'Days to Close']].rename(columns={'Effective Close Date': 'Expected Close Date'}).style.format({'Amount': '${:,.0f}'}), use_container_width=True)
        else:
            st.info(f"향후 {focus_days}일 내에 마감될 것으로 예상되는 딜이 없습니다.")
            # 상세 현황 안내
            total_open_count = len(all_open_deals)
            open_with_date_count = all_open_deals['Effective Close Date'].notna().sum()
            st.markdown(f"""
            - 현재 진행 중인 총 딜: **{total_open_count}** 건
            - 그 중 예상/확정 마감일이 설정된 딜: **{open_with_date_count}** 건
            - {focus_days}일 내 마감 예정 딜이 없거나, 'Expected Closing Date'가 설정되지 않았을 수 있습니다.
            """)
        
        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("💰 Top 10 Open Deals (기회)")
            st.markdown("진행 중인 딜(Dropped 제외) 중 가장 금액이 큰 Top 10 입니다.")
            top_deals = base_df[~base_df['Deal Stage'].isin(won_stages + lost_stages)].sort_values('Amount', ascending=False).head(10)
            if not top_deals.empty:
                st.dataframe(top_deals[['Deal name', 'Deal owner', 'Amount', 'Deal Stage']].style.format({'Amount': '${:,.0f}'}), use_container_width=True)
            else:
                st.info("진행 중인 딜이 없습니다.")

        with col2:
            st.subheader("📝 계약서 발송 후 진행 중인 딜")
            st.markdown("계약서가 발송되었지만 아직 성사/실패가 결정되지 않은 딜 목록입니다.")
            
            contract_sent_deals = df[
                (df['Contract Sent Date'].notna()) &
                (~df['Deal Stage'].isin(won_stages + lost_stages))
            ].sort_values('Amount', ascending=False)

            if not contract_sent_deals.empty:
                today = datetime.now()
                contract_sent_deals['Days Since Sent'] = (today - contract_sent_deals['Contract Sent Date']).dt.days
                st.dataframe(
                    contract_sent_deals[['Deal name', 'Deal owner', 'Amount', 'Contract Sent Date', 'Days Since Sent']].style.format({'Amount': '${:,.0f}'}),
                    use_container_width=True
                )
            else:
                st.info("현재 계약서 발송 후 진행 중인 딜이 없습니다.")
        
        st.markdown("---")
        st.subheader("👀 장기 체류 딜 (Stale Deals) 관리")
        
        open_deals_base = base_df[~base_df['Deal Stage'].isin(won_stages + lost_stages)]
        
        # Stage 선택 드롭다운
        available_stages = ['All Stages'] + sorted(open_deals_base['Deal Stage'].unique().tolist())
        selected_stage = st.selectbox("분석할 Deal Stage를 선택하세요:", available_stages)

        if selected_stage != 'All Stages':
            open_deals_base = open_deals_base[open_deals_base['Deal Stage'] == selected_stage]

        stale_threshold = st.slider("며칠 이상 같은 단계에 머물면 '장기 체류'로 볼까요?", 7, 90, 30, key='stale_slider')
        
        stale_col = 'Time in current stage (HH:mm:ss)'
        if stale_col in open_deals_base.columns:
            open_deals_stale = open_deals_base.copy()
            open_deals_stale['Days in Stage'] = open_deals_stale[stale_col].apply(hhmmss_to_days)
            
            stale_deals_df = open_deals_stale[open_deals_stale['Days in Stage'] > stale_threshold]

            if not stale_deals_df.empty:
                st.warning(f"{stale_threshold}일 이상 같은 단계에 머물러 있는 '주의'가 필요한 딜 목록입니다.")
                st.dataframe(stale_deals_df[['Deal name', 'Deal owner', 'Deal Stage', 'Amount', 'Days in Stage']].sort_values('Days in Stage', ascending=False).style.format({'Amount': '${:,.0f}', 'Days in Stage': '{:.1f}일'}), use_container_width=True)
            else:
                st.success(f"선택된 조건에 해당하는 장기 체류 딜이 없습니다. 👍")
        else:
            st.warning(f"'장기 체류 딜' 분석을 위해서는 HubSpot에서 **'{stale_col}'** 속성을 포함하여 Export해야 합니다.")


    # --- Tab 4: 실패/드랍 분석 ---
    with tab4:
        st.header("실패 및 드랍 딜 회고")
        
        st.subheader("실패/드랍 딜 목록 (최신순)")
        # 전체 데이터(df)에서 필터링
        lost_dropped_deals = df[df['Deal Stage'].isin(lost_stages)]

        if not lost_dropped_deals.empty:
            # 최종 수정일 기준으로 정렬
            sorted_deals = lost_dropped_deals.sort_values(by='Last Modified Date', ascending=False)
            
            # 보여줄 컬럼 리스트 정의
            display_cols = ['Deal name', 'Deal owner', 'Amount', 'Deal Stage', 'Last Modified Date', 'Failure Reason']
            
            st.dataframe(
                sorted_deals[display_cols].style.format({'Amount': '${:,.0f}'}),
                use_container_width=True
            )
        else:
            st.info("'Closed Lost' 또는 'Dropped' 상태의 딜이 없습니다.")
