# HIQ 지문 분석기

영어 지문을 붙여넣거나 PDF를 올리면 구문 분석 + 내신 문제를 자동 생성합니다.

---

## 배포 방법 (5분 완료)

### 1단계 — GitHub에 올리기
1. [github.com](https://github.com) 로그인
2. 우측 상단 **+** → **New repository**
3. Repository name: `hiq-analyzer`
4. **Create repository** 클릭
5. 아래 명령어 순서대로 실행 (터미널/CMD)

```bash
cd hiq-analyzer
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/[내계정]/hiq-analyzer.git
git push -u origin main
```

---

### 2단계 — Vercel 연결
1. [vercel.com](https://vercel.com) 로그인 (GitHub 계정으로)
2. **Add New Project** 클릭
3. `hiq-analyzer` 저장소 선택 → **Import**
4. Framework: **Next.js** (자동 감지됨)
5. **Deploy** 클릭

---

### 3단계 — API 키 등록 (⚠️ 필수)
1. Vercel 대시보드 → 프로젝트 선택
2. **Settings** → **Environment Variables**
3. 아래 항목 추가:
   - **Name**: `ANTHROPIC_API_KEY`
   - **Value**: `sk-ant-api03-...` (실제 키)
   - **Environment**: Production, Preview, Development 모두 체크
4. **Save** 클릭
5. **Deployments** → 최신 배포 우클릭 → **Redeploy**

---

### 로컬 테스트 방법
```bash
# .env.local 파일 생성
cp .env.local.example .env.local
# 파일 열어서 실제 API 키 입력

# 실행
npm install
npm run dev
# http://localhost:3000 접속
```

---

## API 키 발급
[console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key

---

## 재무 비서 (`/finance`)

영어 지문 분석기와 같은 배포에 포함된 두 개의 재무 비서입니다. 메인 화면 우측 상단 **재무 비서 →** 링크 또는 `https://[배포주소]/finance` 로 접속합니다.

| 경로 | 비서 | 기능 |
|---|---|---|
| `/finance/academy` | 🏫 학원 전담 | 월 손익(+AI 코멘트) · 수강료 수납/미납 관리(입금 자동 대조, 안내 문자) · 강사 급여 계산(3.3%/4대보험) · 세무 일정(원천세·간이지급명세서·사업장현황신고·종소세) |
| `/finance/personal` | 👤 개인 전담 | 지출 분류·월 리포트(+AI 절약 제안) · 카테고리별 예산·초과 경고 · 저축 목표 추적 · 구독/고정지출 자동 탐지 |

### 사용 순서
1. **거래내역** 탭에서 은행·카드사에서 내려받은 엑셀(xlsx/xls)·CSV 파일을 올립니다. (국민·신한·우리·하나·농협·카카오뱅크·토스 등 대부분의 양식을 자동 인식, EUC-KR CSV 지원)
2. 헤더 행과 열 역할(날짜/내용/입금/출금)을 확인하고 **가져오기**를 누릅니다. 중복 거래는 자동으로 제외됩니다.
3. 키워드 규칙으로 1차 분류 후, 남은 거래만 AI(Claude)가 분류합니다. 카테고리를 직접 바꾸면 같은 가맹점에 적용되고 다음부터 기억됩니다.
4. 학원: 학생을 등록하고 **입금 내역 자동 대조**를 누르면 입금자명과 금액으로 납부가 체크됩니다. 강사를 등록하고 월별 시수를 입력하면 급여·원천세가 계산됩니다.
5. 개인: **예산** 탭에서 "최근 3개월 평균으로 채우기"로 시작하고, **구독·고정지출** 탭에서 해지 검토 항목을 표시하세요.

### 데이터 저장과 개인정보
- 모든 데이터(거래내역·학생·강사·예산·목표)는 **사용 중인 브라우저의 localStorage에만** 저장됩니다. 서버나 DB에 저장되지 않습니다.
- 다른 기기에서 쓰거나 브라우저 데이터를 지우기 전에는 **거래내역 탭 → 백업(JSON)** 으로 내려받고, **복원**으로 불러오세요.
- AI 분류·분석 시 Anthropic API로 전송되는 것은 거래 내용(적요)·금액과 카테고리별 합계뿐입니다. 계좌번호·잔액·연락처는 전송하지 않습니다.
- 파일 자체는 브라우저 안에서 파싱되며 업로드되지 않습니다.

### 집계 기준
- 개인: `이체·송금`, `카드대금`, `저축·투자` 카테고리는 소비가 아니므로 지출 합계에서 제외합니다. 은행 내역과 카드 내역을 함께 올려도 카드대금이 중복 집계되지 않습니다.
- 학원: `이체·내부거래`(카드대금, 대표자 계좌 이동)는 손익에서 제외합니다. 카드 지출을 반영하려면 카드 이용내역도 함께 올리세요.
- 세무 일정은 학원(교육용역, 부가세 면세사업자) 기준의 일반 일정입니다. 토·일요일은 다음 영업일로 표시하며 공휴일은 반영하지 않습니다. 실제 신고 의무는 세무사와 확인하세요.
- 4대보험 요율과 국민연금 상한은 **강사 급여 → 4대보험 요율**에서 수정할 수 있습니다. 근로자 소득세(간이세액)는 직접 입력합니다.

### 기술 메모
- AI 호출은 `pages/api/finance.js` 한 곳에서 `@anthropic-ai/sdk`로 처리합니다 (모델 `claude-opus-5-5`, 분류는 structured output JSON, 안전 정책 거부 시 서버측 fallback 사용). 기존 `ANTHROPIC_API_KEY` 환경변수를 그대로 씁니다.
- 파일 파싱: `xlsx`(SheetJS), 반복결제 탐지·세무 일정·급여 계산은 `lib/finance/` 의 순수 함수입니다.
