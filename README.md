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

## 학원 인사 관리 시스템 (`/manage`)

직원 정보부터 급여 관리까지, 학원 **인사 업무를 한 번에 처리**합니다. 배포 후 `https://[내도메인]/manage` 로 접속하세요.
(지문 분석기 상단의 **인사 관리 시스템 →** 버튼으로도 이동할 수 있습니다.)

| 메뉴 | 기능 |
|---|---|
| 대시보드 | 재직 인원, 오늘 출근 현황, 휴가 승인 대기, 30일 내 계약 만료, 이번 달 급여 합계, 연차 잔여 |
| 직원 정보 | 직책·고용 형태(정규직/계약직/시간강사/프리랜서)·급여 형태·4대보험·계좌 등록, 직원별 연차·근태·계약·급여 요약 |
| 근태 관리 | 출근/퇴근 시간 입력(버튼 한 번으로 현재 시각), 기준 시각 대비 지각·조퇴 자동 판정, 근무시간 계산, 월간 집계·일자별 표·인쇄 |
| 휴가 관리 | 연차·반차·병가 등 신청 등록, 승인/반려, 연차 잔여 자동 계산(일요일 제외), 직원별 잔여 현황 |
| 급여 관리 | 월별 급여 일괄 생성(월급제: 기본급 / 시급제: 근태 시간 × 시급), 수당·상여·소득세 입력, 4대보험·지방소득세·프리랜서 3.3% 자동 공제, 급여명세서 인쇄, 지급 완료 처리 |
| 계약 관리 | 근로·위촉 계약 기간과 조건 관리, 만료 30일 전 알림(D-day), 1년 갱신 계약 생성, 계약 없는 재직자 표시 |
| 설정 · 백업 | 학원 이름, 기준 출퇴근 시각, 기본 연차 일수, 4대보험 요율, JSON 백업/복원, 샘플 데이터, 초기화 |

### 💻 PC 설치 프로그램으로 쓰기 (Windows / macOS)

웹 배포 없이 **설치해서 쓰는 프로그램**으로도 만들 수 있습니다. (Electron 기반, 인터넷 연결 불필요)

**방법 A — GitHub에서 자동으로 설치 파일 받기 (추천)**
1. GitHub 저장소 → **Actions** 탭 → **Desktop Build** → **Run workflow** 클릭
2. 몇 분 뒤 완료되면 하단 **Artifacts** 에서 `windows-installer` (`.exe`) 또는 `macos-dmg` (`.dmg`) 다운로드
3. 압축을 풀고 설치 파일 실행 → 바탕화면의 **HIQ 인사 관리** 아이콘으로 실행
- `v1.0.0` 처럼 `v`로 시작하는 태그를 푸시하면 **Releases** 페이지에 설치 파일이 자동 첨부됩니다.
- 서명되지 않은 앱이므로 Windows SmartScreen 경고가 뜨면 "추가 정보 → 실행", macOS는 "시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기"를 선택하세요.

**방법 B — 내 PC에서 직접 빌드**
```bash
npm install
npm run desktop:build:win   # Windows 설치 파일 → dist/HIQ-인사관리-Setup-1.0.0.exe
npm run desktop:build:mac   # macOS 디스크 이미지 → dist/HIQ-인사관리-1.0.0-arm64.dmg (Mac에서만)
npm run desktop:dev         # 설치 없이 바로 실행해 보기
```

- 데스크톱 프로그램의 데이터는 그 PC 안에 저장됩니다. (도움말 → 사용 안내에서 저장 위치 확인)
- 데스크톱 버전에는 인사 관리 시스템만 포함되며, 지문 분석기는 웹(Vercel)에서 사용합니다.
- Vercel 빌드 시간을 줄이려면 Vercel 환경변수에 `ELECTRON_SKIP_BINARY_DOWNLOAD=1` 을 추가하세요.

### 데이터 저장 방식 (⚠️ 꼭 읽어주세요)
- 모든 데이터는 **접속한 브라우저의 저장소(localStorage)** 에만 저장됩니다. 별도 서버·DB 설정이 필요 없어 Vercel 배포만으로 바로 쓸 수 있습니다.
- 따라서 **다른 PC나 휴대폰에서는 데이터가 공유되지 않으며**, 브라우저 데이터를 지우면 사라집니다.
- **설정 · 백업** 메뉴에서 정기적으로 백업 파일을 내려받고, 다른 기기에서는 복원 기능으로 불러오세요.
- 여러 기기에서 함께 쓰려면 다음 단계로 DB(예: Supabase) 연동이 필요합니다.

### 급여 계산 기준
- 4대보험(근로자 부담분)은 설정 메뉴의 요율로 자동 계산하며, 요율은 매년 공단 고시에 맞춰 갱신하세요.
- 소득세는 간이세액표 금액을 급여별로 직접 입력하고, 지방소득세 10%는 자동 계산됩니다.
- 프리랜서(위촉)는 사업소득세 3% + 지방소득세 0.3%를 자동 원천징수합니다.
- 실제 신고·납부 금액은 세무 담당자 확인을 권장합니다.

### 처음 사용 순서
1. **설정 · 백업**에서 학원 이름과 기준 출퇴근 시각 확인
2. **직원 정보**에서 직원 등록 (고용 형태·급여·4대보험 여부)
3. **계약 관리**에서 근로계약 기간 등록
4. 매일 **근태 관리**에서 출퇴근 기록, 휴가는 **휴가 관리**에서 승인
5. 매월 **급여 관리 → 이번 달 급여 생성** 후 수당·소득세 보정, 명세서 출력, 지급 완료 처리
