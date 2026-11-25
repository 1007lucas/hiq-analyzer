"""`init` 명령이 만들어 주는 기본 설정 파일 내용.

저장소의 config.example.toml / .env.example 도 이 내용과 같습니다 (테스트로 확인).
"""

from __future__ import annotations

CONFIG_TOML = '''\
# ============================================================
#  자동매매 설정 파일 (config.toml)
#  - 비율은 소수로 적습니다.  5% → 0.05
#  - API 키·계좌번호 같은 비밀 값은 여기가 아니라 .env 파일에 적습니다.
#  - 고친 뒤에는  python -m autotrader doctor  로 점검해 보세요.
# ============================================================

[general]
# 매매 모드
#   "paper"    : 가상 매매 (실제 주문 없음, 봇 안에서만 사고팖) ← 처음에는 반드시 이것으로
#   "kis-mock" : 한국투자증권 모의투자 계좌로 주문
#   "kis-live" : 한국투자증권 실전 계좌로 주문 (아래 [live] enabled = true 도 필요)
mode = "paper"
data_dir = "data"        # 상태·기록·캐시가 저장되는 폴더
log_level = "INFO"

[universe]
# 매매 대상 종목코드 (6자리). 거래량이 많은 대형주·ETF 를 권장합니다.
symbols = ["005930", "000660", "035420", "005380", "069500"]

[universe.names]         # 화면·알림에 보여 줄 이름 (선택)
"005930" = "삼성전자"
"000660" = "SK하이닉스"
"035420" = "NAVER"
"005380" = "현대차"
"069500" = "KODEX 200"

[strategy]
# 전략 이름.  python -m autotrader strategies  로 목록과 설명을 볼 수 있습니다.
#   sma_cross            이동평균 골든크로스 추세추종 (매매 횟수 적음, 기본값)
#   volatility_breakout  변동성 돌파 (매매 횟수 많음 → 수수료·세금 부담 큼)
#   donchian_breakout / momentum / rsi_reversion / bollinger_reversion
name = "sma_cross"

[strategy.params]        # 전략 파라미터 (비워 두면 전략의 기본값)
fast = 5
slow = 20

[risk]
capital = 10_000_000         # 봇 운용자금(원). 봇은 계좌에 돈이 더 있어도 이 금액 안에서만 매매합니다.
max_positions = 3            # 동시에 보유할 최대 종목 수
position_pct = 0.30          # 1종목당 투입 비중 (봇 평가금 대비)
max_order_amount = 0         # 1회 매수 최대 금액(원). 0 = 제한 없음
cash_reserve_pct = 0.01      # 항상 남겨 둘 현금 비율
stop_loss_pct = 0.07         # 손절: 평균단가 대비 -7% 면 매도. 0 = 사용 안 함
take_profit_pct = 0.0        # 익절: 평균단가 대비 +N% 면 매도. 0 = 사용 안 함
trailing_stop_pct = 0.0      # 추적손절: 진입 후 최고가 대비 -N% 면 매도. 0 = 사용 안 함
cooldown_days = 3            # 손절·익절된 종목을 다시 사지 않는 거래일 수
breakout_max_chase_pct = 0.01  # 돌파 목표가보다 1% 넘게 오른 가격은 추격 매수하지 않음
daily_loss_limit_pct = 0.03  # 하루 손실이 -3% 에 이르면 그날 신규 매수 중단. 0 = 사용 안 함
daily_loss_action = "halt"   # "halt": 신규 매수만 중단 / "liquidate": 전량 매도 후 중단
max_drawdown_pct = 0.20      # 최고 평가금 대비 -20% 면 'resume' 명령 전까지 신규 매수 중단. 0 = 사용 안 함
max_orders_per_day = 30      # 하루 최대 매수 주문 수 (폭주 방지)

[costs]
# 백테스트·페이퍼 매매·봇 장부의 손익 계산에 쓰는 비용 가정
commission_rate = 0.00015    # 매매 수수료율 (매수·매도 각각 0.015%)
sell_tax_rate = 0.0020       # 매도 시 거래세 0.20% (ETF 는 면제지만 보수적으로 같이 적용합니다)
slippage_rate = 0.0005       # 슬리피지 가정 0.05% (체결가가 그만큼 불리하다고 가정)

[schedule]
entry_delay_sec = 30             # 장 시작 후 30초 뒤에 시가 주문
open_entry_deadline = "09:30"    # 이 시각 이후에 봇을 켜면 그날 '시가 매수'는 건너뜀
close_exit_time = "15:15"        # 종가 청산 주문 시각 (동시호가 15:20 전)
poll_interval_sec = 10           # 장중 시세 확인 주기(초)
extra_holidays = []              # 내장 달력에 없는 휴장일 추가. 예: ["2027-03-03"]

[backtest]
start = "2021-01-01"
end = ""                         # 비우면 오늘까지
# 데이터 출처: auto(KIS 키가 있으면 KIS, 없으면 네이버→야후) | kis | naver | yahoo | csv | synthetic(연습용 가짜 데이터)
data_source = "auto"

[kis]
order_style = "market"       # "market": 시장가 / "limit": 현재가에서 불리한 쪽으로 몇 틱 띄운 지정가
limit_ticks = 5              # order_style = "limit" 일 때 띄울 틱 수
fill_timeout_sec = 20        # 이 시간 안에 체결되지 않은 수량은 취소
max_calls_per_sec = 0        # API 초당 호출 수. 0 = 기본값 (실전 10, 모의 1.8)

[live]
# 실전 매매 허용 스위치. 백테스트 → 페이퍼 → 모의투자로 충분히 확인한 뒤에만 true 로 바꾸세요.
enabled = false
'''

DOTENV = '''\
# ============================================================
#  비밀 값 (.env) — 이 파일은 절대 남에게 보여 주거나 인터넷에 올리지 마세요.
#  한국투자증권 KIS Developers(https://apiportal.koreainvestment.com)에서 발급받은 값을 넣습니다.
#  쓰지 않는 항목은 비워 두면 됩니다.
# ============================================================

# --- 모의투자 (먼저 이것부터) ---
KIS_MOCK_APP_KEY=
KIS_MOCK_APP_SECRET=
KIS_MOCK_ACCOUNT=            # 모의투자 계좌번호 10자리. 예: 50012345-01

# --- 실전투자 ---
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT=                 # 실전 계좌번호 10자리. 예: 12345678-01

# --- 알림 (선택) ---
TELEGRAM_BOT_TOKEN=          # 텔레그램 봇 토큰 (BotFather 에서 발급)
TELEGRAM_CHAT_ID=            # 알림을 받을 채팅 ID
NOTIFY_WEBHOOK_URL=          # 디스코드/슬랙 웹훅 주소
'''
