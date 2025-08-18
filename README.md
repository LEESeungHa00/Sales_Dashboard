# 🎯 HubSpot Sales Dashboard

> **HubSpot API와 실시간으로 연동하여 영업 현황을 진단하고, 데이터를 기반으로 성장 전략을 수립하는 인터랙티브 대시보드입니다.**
> 더 이상 감에 의존하지 않고, 데이터를 통해 다음 액션을 결정하세요.

<br>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Badge"/>
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit Badge"/>
  <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="Pandas Badge"/>
  <img src="https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" alt="Plotly Badge"/>
  <img src="https://img.shields.io/badge/HubSpot-FF7A59?style=for-the-badge&logo=hubspot&logoColor=white" alt="HubSpot Badge"/>
</p>

---

## 🎯 The Problem
본 대시보드 도입 이전, 영업팀은 다음과 같은 여러 문제에 직면해 있었습니다.

-   **파편화된 데이터**: 분석을 위해 HubSpot 데이터를 매번 수동으로 취합해야 하는 번거로움
-   **성과 측정의 어려움**: 팀과 개인의 성과를 객관적인 데이터로 파악하고 비교하기 어려움
-   **비효율적인 파이프라인 관리**: 딜이 정체되는 병목 구간을 직관적으로 파악하기 힘듦
-   **직감에 의존한 의사결정**: 명확한 데이터 근거 없이 감이나 개별 보고에 의존한 전략 수립
-   **미래 예측의 부재**: 다음 분기에 집중할 핵심 딜과 파이프라인의 목표 달성 가능성 예측 불가

---

## 💡 The Solution
이러한 문제들을 해결하기 위해 HubSpot API와 직접 연동되는 **실시간 Sales Dashboard**를 구축했습니다.

-   **데이터 중앙화 및 자동화**: 수동 작업 없이 HubSpot의 최신 데이터를 자동으로 동기화하여 시각화합니다.
-   **명확한 성과 측정**: 팀과 개인(BDR/AE)의 핵심 지표(KPI)를 심층 분석하고 리더보드로 투명하게 공유합니다.
-   **효율적인 파이프라인 진단**: Funnel 차트와 단계별 평균 소요 시간 분석으로 병목 구간을 명확하게 진단합니다.
-   **데이터 기반 의사결정 지원**: `Top 10 Deals`, `장기 체류 딜` 등 집중해야 할 딜의 우선순위를 명확하게 제시합니다.
-   **학습하는 조직 문화 조성**: `실패/드랍 분석` 기능을 통해 놓친 딜의 원인을 데이터로 회고하고 같은 실수를 반복하지 않도록 돕습니다.

---

## 🚀 Getting Started

### **Prerequisites**
-   Python 3.8 이상
-   HubSpot Private App Access Token

### **Installation & Setup**
1.  **저장소 복제 (Clone the repository)**:
    ```bash
    git clone [저장소 URL]
    cd [프로젝트 폴더]
    ```

2.  **필요한 라이브러리 설치**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **HubSpot Access Token 설정**:
    프로젝트 폴더 내에 `.streamlit/secrets.toml` 파일을 생성하고 아래 내용을 추가합니다.
    ```toml
    HUBSPOT_ACCESS_TOKEN = "Your_HubSpot_Private_App_Access_Token"
    ```

4.  **Streamlit 앱 실행**:
    ```bash
    streamlit run dashboard.py
    ```

---

## ✨ Impact
이 대시보드 도입을 통해 우리 팀은 다음과 같은 긍정적인 효과를 얻었습니다.

-   **업무 효율성 증대**: 데이터 취합 및 보고서 작성 시간을 없애고, 모든 팀원이 동일한 데이터를 보며 논의를 시작합니다.
-   **영업 속도(Sales Velocity) 향상**: 병목 구간 개선과 핵심 딜 집중을 통해 전체 영업 사이클을 단축했습니다.
-   **승률(Win Rate) 증가**: 클로징 직전의 이탈을 방지하고, 실패 원인 분석을 통해 성공 전략을 고도화했습니다.
-   **데이터 기반 문화 정착**: 모든 팀원이 숫자를 기반으로 소통하고 전략을 수립하는 문화가 만들어졌습니다.
-   **정확한 미래 예측**: 목표 매출 대비 현재 파이프라인 상태를 객관적으로 파악하여 더 정확한 실적 예측이 가능해졌습니다.
