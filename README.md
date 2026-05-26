# V4 Trading Bot Dashboard

AWS Lambda 기반 자동 트레이딩 봇의 Streamlit 대시보드.

## 기능

- 💎 자산 요약 (총자산, 현금, 수익률)
- 💼 보유 종목 상세
- 📊 거래 통계 (승률, P&L)
- 🔄 거래 이력
- 📰 시그널 모니터링

## 호스팅

Streamlit Community Cloud에 배포되어 폰/PC 브라우저로 접속 가능.

## 시스템 구조

- AWS Lambda 6개 함수
- DynamoDB 4개 테이블
- EventBridge 7개 스케줄
- 평일 시장 시간에 자동 매매

자세한 내용은 [v4-trading-bot 메인 README](별도) 참조.
