# 주식 자동매매 프로그램 (autotrader)

한국 주식을 **정해 둔 규칙대로 자동으로 사고파는** 프로그램입니다.

- **백테스트** — 과거 시세로 전략을 먼저 검증
- **가상 매매(paper)** — 실제 주문 없이 실시간 시세로 연습
- **모의투자 / 실전** — 한국투자증권(KIS) Open API 로 실제 주문
- 손절·일일 손실 한도·긴급 정지 등 **안전장치 내장**, 텔레그램 알림, 웹 대시보드

파이썬만 설치하면 됩니다. 추가로 설치할 라이브러리가 없습니다 (Python 3.11 이상).

---

## ⚠️ 먼저 꼭 읽어 주세요

1. **수익을 보장하지 않습니다.** 자동매매는 "규칙을 지치지 않고 지켜 주는 도구"일 뿐, 돈을 벌어 주는 기계가 아닙니다. 원금 손실이 날 수 있고 그 책임은 사용자 본인에게 있습니다.
2. **반드시 이 순서로 진행하세요:** 백테스트 → 가상 매매(paper) 며칠 → 모의투자(kis-mock) 1~2주 → 소액 실전.
3. **이 프로그램은 실제 한국투자증권 서버에서 아직 검증되지 않았습니다.** 공식 예제 저장소의 규격대로 만들고 "가짜 서버"로 자동 테스트했지만, 개발 환경에서는 증권사 서버에 접속할 수 없었습니다. 그래서 **모의투자에서 주문·체결·취소가 실제로 잘 되는지 직접 확인하는 단계가 필수**입니다. ([알려진 한계](#알려진-한계) 참고)
4. 봇이 꺼져 있으면 **손절도 동작하지 않습니다.** PC 가 절전 모드로 들어가지 않게 하세요.

---

## 5분 만에 체험하기

### 1) 파이썬 설치
[python.org](https://www.python.org/downloads/) 에서 3.11 이상을 설치합니다. Windows 는 설치 첫 화면에서 **"Add python.exe to PATH"** 를 꼭 체크하세요.

### 2) 이 폴더에서 명령 실행
Windows: 이 폴더(`auto-trader`)를 탐색기로 연 뒤 주소창에 `cmd` 를 입력하고 Enter.
macOS/Linux: 터미널에서 `cd auto-trader`. (명령이 `python` 으로 안 되면 `python3` 로 바꿔 입력)

```bash
python -m autotrader init                          # 설정 파일(config.toml, .env) 만들기
python -m autotrader backtest --source synthetic   # 연습용 가짜 데이터로 기능 체험
python -m autotrader backtest                      # 실제 과거 시세로 전략 검증
python -m autotrader backtest --compare            # 내장 전략 6개 비교
```

백테스트가 끝나면 `reports/` 폴더에 HTML 리포트가 생깁니다. 브라우저로 열어 보세요.

### 3) 가상 매매 (실제 주문 없음)

```bash
python -m autotrader run          # 봇 시작 (Ctrl+C 로 종료)
python -m autotrader status       # 다른 창에서: 현재 상태 보기
python -m autotrader dashboard    # 다른 창에서: 웹 대시보드 (http://localhost:8787)
```

Windows 에서는 `run_bot.bat`, `run_backtest.bat`, `run_dashboard.bat`, `emergency_stop.bat` 을 더블클릭해도 됩니다.

---

## 단계별 안내

### 1단계 — 백테스트

```bash
python -m autotrader backtest --start 2021-01-01
python -m autotrader backtest --strategy volatility_breakout --param k=0.5
python -m autotrader backtest --symbols 005930,069500 --capital 5000000
```

- 리포트에서 **총수익률보다 최대낙폭(MDD)** 을 먼저 보세요. "-30%" 는 1,000만 원이 700만 원이 되는 구간을 견뎌야 한다는 뜻입니다.
- "단순보유(벤치마크)"보다 못하면 그 전략을 쓸 이유가 없습니다.
- 데이터 출처(`--source`): `auto`(KIS 키가 있으면 KIS, 없으면 네이버→야후), `kis`, `naver`, `yahoo`, `csv`, `synthetic`.
  네이버·야후는 비공식 경로라 막힐 수 있습니다. 그럴 땐 KIS 키를 넣거나 `data/csv/종목코드.csv` 파일(`date,open,high,low,close,volume`)을 준비해 `--source csv` 를 쓰세요.

### 2단계 — 가상 매매 (paper)

`config.toml` 의 `mode = "paper"` (기본값) 그대로 `python -m autotrader run`.
실제 주문은 나가지 않고, 봇 안의 가상 계좌로만 사고팝니다. 며칠 돌려 보며 알림·대시보드·손절 동작에 익숙해지세요.

### 3단계 — 한국투자증권 모의투자

1. 한국투자증권 계좌 개설 → [KIS Developers](https://apiportal.koreainvestment.com) 에서 **모의투자 신청** 후 **모의투자용 앱키/시크릿** 발급
2. `.env` 파일에 입력
   ```
   KIS_MOCK_APP_KEY=발급받은_앱키
   KIS_MOCK_APP_SECRET=발급받은_시크릿
   KIS_MOCK_ACCOUNT=50012345-01
   ```
3. 점검 후 실행
   ```bash
   python -m autotrader doctor --mode kis-mock     # 토큰·시세·계좌 조회가 되는지 확인
   python -m autotrader run --mode kis-mock
   ```
4. **1~2주 동안** 매수·매도·손절이 실제로 체결되는지, 증권사 앱의 잔고와 `status` 가 일치하는지 확인하세요.

### 4단계 — 실전 (충분히 확인한 뒤에만)

1. `.env` 에 실전용 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT` 입력
2. `config.toml` 에서 `[risk] capital` 을 **잃어도 괜찮은 소액**으로, `[live] enabled = true` 로 변경
3. `python -m autotrader doctor --mode kis-live`
4. `python -m autotrader run --mode kis-live` → 확인 문구 `실전매매` 를 직접 입력해야 시작됩니다.

---

## 봇은 하루를 이렇게 보냅니다

| 시각 | 하는 일 |
|---|---|
| 08:40 | 전일까지의 일봉으로 **오늘의 계획** 수립 (무엇을 사고팔지) → 알림 |
| 09:00 + 30초 | 실제로 장이 열렸는지 확인 후 시가 매도 → 시가 매수 |
| 장중 (10초마다) | 보유 종목 손절·익절 감시, 돌파 매수 감시 |
| 15:15 | 종가 청산 대상 매도 |
| 15:35 | 평가금 기록, **마감 요약** 알림 |

전략은 "전일까지 완성된 일봉"만 보고 판단합니다. 백테스트와 실전이 **같은 판단 코드**를 쓰므로 백테스트에서 본 규칙이 그대로 실행됩니다.

## 내장 전략

| 이름 | 설명 | 매매 빈도 |
|---|---|---|
| `sma_cross` (기본) | 5일선이 20일선 위에 있으면 보유, 아래로 내려가면 매도 | 낮음 |
| `donchian_breakout` | 20일 신고가 돌파 시 매수, 10일 신저가 이탈 시 매도 | 낮음 |
| `momentum` | 최근 60일 수익률이 플러스면 보유 | 낮음 |
| `rsi_reversion` | RSI 30 미만 과매도에서 매수, 반등하면 매도 | 중간 |
| `bollinger_reversion` | 볼린저밴드 하단 이탈 시 매수, 중심선 회복 시 매도 | 중간 |
| `volatility_breakout` | 변동성 돌파: 시가 + 전일 변동폭×k 돌파 시 매수, 다음 날 시가 매도 | **높음** |

매매가 잦을수록 수수료·거래세(매도 시 약 0.2%)·슬리피지가 수익을 갉아먹습니다. `python -m autotrader strategies` 로 파라미터를 볼 수 있습니다.

## 안전장치

| 장치 | 설명 |
|---|---|
| 운용자금 한도 | 계좌에 돈이 더 있어도 `[risk] capital` 금액 안에서만 매매. 직접 산 종목은 건드리지 않음 |
| 손절 / 익절 / 추적손절 | 평균단가 대비 -7%(기본)면 매도. `[risk]` 에서 조정 |
| 일일 손실 한도 | 하루 -3%(기본)면 그날 신규 매수 중단 |
| 최대 낙폭 한도 | 최고점 대비 -20%(기본)면 `resume` 할 때까지 신규 매수 중단 |
| 긴급 정지 | `python -m autotrader stop` → 모든 주문 중단. `resume` 으로 해제 |
| 전량 청산 | `python -m autotrader liquidate` → 봇 보유 종목 전부 매도 후 정지 (봇 실행 중·장중에만) |
| 중복 실행 방지 | 같은 모드의 봇은 하나만 실행됨 (이중 주문 방지) |
| 주문 재전송 금지 | 주문 결과가 불확실하면 다시 보내지 않고 "직접 확인" 알림 |
| 실제 개장 확인 | 달력만 믿지 않고 거래가 실제로 일어나는지 확인한 뒤 주문 (임시 휴장·개장 지연 대비) |
| 비정상 시세 무시 | 전일 대비 ±30% 를 벗어난 시세는 오류로 보고 무시 |
| 권리 변동 감지 | 액면분할 등으로 주가 기준이 바뀌면 그 종목 자동매매 중단 + 알림 |
| 실전 이중 잠금 | `[live] enabled = true` + 시작 시 `실전매매` 직접 입력 |

## 명령어

```
python -m autotrader init          설정 파일 만들기
python -m autotrader doctor        설정·API 연결 점검  (--mode, --offline, --notify-test)
python -m autotrader strategies    전략 목록
python -m autotrader backtest      백테스트  (--strategy, --param, --symbols, --start, --end, --source, --compare)
python -m autotrader run           자동매매 시작  (--mode paper|kis-mock|kis-live)
python -m autotrader status        현재 상태
python -m autotrader dashboard     웹 대시보드 (조회 전용)
python -m autotrader stop          긴급 정지
python -m autotrader resume        정지 해제
python -m autotrader liquidate     전량 매도 후 정지
python -m autotrader forget 005930 봇 장부에서 종목 정리 (증권사 앱에서 직접 팔았을 때)
```

## 텔레그램 알림 (강력 권장)

1. 텔레그램에서 `@BotFather` 에게 `/newbot` → **봇 토큰** 받기
2. 만든 봇에게 아무 메시지나 보낸 뒤, 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 를 열어 `"chat":{"id":숫자}` 의 숫자(**채팅 ID**) 확인
3. `.env` 에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 입력
4. `python -m autotrader doctor --notify-test` 로 테스트

매수·매도 체결, 손절, 오류, 하루 요약이 휴대폰으로 옵니다. 디스코드/슬랙 웹훅(`NOTIFY_WEBHOOK_URL`)도 됩니다.

## 봇을 계속 켜 두려면

- PC 의 **절전 모드/자동 종료를 끄세요.** 노트북은 덮개를 닫아도 꺼지지 않게 설정.
- 봇은 장이 끝나도 종료하지 않고 다음 거래일까지 기다립니다. 한 번 켜 두면 됩니다.
- PC 를 재시작했다면 다시 `run` 하세요. 봇은 진행 상황을 `data/` 폴더에 저장하므로 **같은 주문을 두 번 내지 않고** 이어서 동작합니다.
- Windows 작업 스케줄러로 매일 아침 `run_bot.bat` 을 실행하게 할 수도 있습니다 (실전은 `--i-understand` 옵션 필요).

## 백테스트의 가정

- 일봉(시가·고가·저가·종가)만 사용합니다. 장중 순서를 알 수 없는 경우 **불리한 쪽**으로 가정합니다 (예: 손절과 익절이 같은 날 모두 가능하면 손절 먼저).
- 수수료 0.015%, 매도 거래세 0.20%, 슬리피지 0.05% 를 반영합니다 (`[costs]` 에서 조정).
- 주문은 전량 체결된다고 가정합니다. 거래량이 적은 종목은 실제보다 좋게 나옵니다.
- 과거에 잘 맞도록 파라미터를 계속 고치면 "과최적화"되어 실전에서는 통하지 않습니다.

## 알려진 한계

- **실서버 미검증:** 한국투자증권 연동은 공식 예제 저장소(2026-11 기준)의 엔드포인트·TR ID·필드명을 따랐고 가짜 서버로 테스트했지만, 실제 모의/실전 서버 호출은 해 보지 못했습니다. 특히 ① 주문 직후 체결 조회 지연, ② 취소 주문의 표시 방식, ③ 장 시작 전 시세 필드 값은 공식 문서로 확정하지 못해 방어적으로 구현했습니다. 모의투자에서 꼭 확인하세요.
- **네이버·야후 시세는 비공식**이며 응답 형식을 실제로 검증하지 못했습니다. 키 없이 하는 백테스트/가상 매매용 "최선 노력" 기능입니다. 안정적인 운용에는 KIS 키를 쓰세요.
- **휴장일 달력:** 2026년은 확정, 2027년은 정부 월력요항 기준 예상입니다 (거래소 공식 발표 전). 임시공휴일 등은 `[schedule] extra_holidays` 로 추가할 수 있고, 실전 키가 있으면 증권사 휴장일 조회를 우선합니다. 2028년 이후는 프로그램 업데이트가 필요합니다.
- 국내 주식 **현금 매수(롱) 전용**입니다. 신용·미수·공매도·해외주식·시간외 거래는 지원하지 않습니다.
- 수수료·세금은 설정값으로 **추정**합니다. 봇의 손익은 증권사 실제 잔고와 조금 다를 수 있습니다.
- 배당·액면분할 같은 권리 변동은 자동 처리하지 않습니다 (감지하면 그 종목 매매를 멈추고 알립니다).
- 시세는 10초 간격으로 확인합니다(실시간 체결 통보 아님). 급변 시 손절가보다 불리하게 팔릴 수 있습니다.

## 자주 묻는 질문

**Q. `python` 을 찾을 수 없다고 나옵니다.**
파이썬 설치 시 PATH 체크를 놓친 경우입니다. 다시 설치하거나 `py -m autotrader ...` 로 실행해 보세요.

**Q. 백테스트에서 "일봉 데이터를 받지 못했습니다"가 나옵니다.**
인터넷 연결과 종목코드를 확인하세요. 네이버·야후가 막힌 경우 `.env` 에 KIS 키를 넣거나 CSV 를 준비하세요. 기능만 보려면 `--source synthetic`.

**Q. 봇이 아무것도 사지 않습니다.**
`status` 의 "오늘의 계획"을 보세요. 전략 조건이 안 맞으면 사지 않는 것이 정상입니다. 09:30 이후에 켜면 그날 "시가 매수"는 건너뜁니다. "일봉 부족"이면 상장한 지 얼마 안 된 종목입니다.

**Q. 증권사 앱에서 직접 팔았습니다.**
`python -m autotrader forget 종목코드 --price 판가격` 으로 봇 장부를 맞춰 주세요.

**Q. 알림에 "직접 확인해 주세요"가 왔습니다.**
주문 결과를 확신할 수 없는 상황입니다. 증권사 앱에서 주문·잔고를 확인하세요. 봇은 안전을 위해 그날 그 종목을 더 건드리지 않습니다.

**Q. 모드를 바꾸면 기록이 사라지나요?**
아니요. 모드별로 장부가 따로 저장됩니다 (`data/state-paper.db`, `state-kis-mock.db`, `state-kis-live.db`).

---

## 개발자용

```bash
python -m pytest            # 테스트 (pytest 필요: pip install pytest)
```

```
autotrader/
  core.py            매매 판단 코어 (백테스트·실전 공용): 계획 실행, 리스크, 장부
  strategies/        전략 (DayPlan 을 반환하는 순수 함수)
  backtest/          일봉 재생 드라이버, 성과 지표, HTML 리포트
  live/trader.py     실시간 드라이버 (시계·시세 → 코어)
  brokers/kis.py     한국투자증권 Open API 클라이언트
  brokers/paper.py   가상 체결
  data/              일봉 로더, CSV, 합성 데이터, 네이버·야후
  dashboard/         조회 전용 웹 대시보드
  config.py, cli.py, app.py, state.py, control.py, notify.py, market_calendar.py, market_rules.py
```

새 전략은 `strategies/` 에 `Strategy` 를 상속한 클래스를 만들고 `strategies/__init__.py` 의 목록에 추가하면 됩니다.
