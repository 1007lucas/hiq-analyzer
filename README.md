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

## 학원 관리 시스템 (`/manage`)

지문 분석기와 같은 사이트에서 **학원 운영 업무**를 한 곳에서 처리합니다. 배포 후 `https://[내도메인]/manage` 로 접속하세요.
(지문 분석기 상단의 **학원 관리 시스템 →** 버튼으로도 이동할 수 있습니다.)

| 메뉴 | 기능 |
|---|---|
| 대시보드 | 재원생·운영 반·강사 수, 오늘 수업과 출결 체크 현황, 이번 달 미수금, 후속 상담 예정 |
| 학생 관리 | 학생 등록·검색·상태(재원/휴원/퇴원), 수강반 배정, 학생별 출결·수납·상담 요약 |
| 출결 관리 | 날짜·반별 출석/지각/결석/조퇴 체크(클릭 즉시 저장), 월간 출결표 + 인쇄 |
| 상담 기록 | 학부모·학생 상담 내용 기록, 후속 상담 예정일 관리 |
| 반 · 수업 관리 | 반 생성(과목·강사·요일·시간·수강료·정원), 수강생 추가/제외 |
| 강사 관리 | 강사 정보와 담당 반 |
| 학원비 수납 | 월별 청구 자동 생성(수강반 수강료 합계), 수납 처리, 완납/부분납/미납 현황 |
| 설정 · 백업 | 학원 이름, JSON 백업/복원, 샘플 데이터, 초기화 |

### 데이터 저장 방식 (⚠️ 꼭 읽어주세요)
- 모든 데이터는 **접속한 브라우저의 저장소(localStorage)** 에만 저장됩니다. 별도 서버·DB 설정이 필요 없어 Vercel 배포만으로 바로 쓸 수 있습니다.
- 따라서 **다른 PC나 휴대폰에서는 데이터가 공유되지 않으며**, 브라우저 데이터를 지우면 사라집니다.
- **설정 · 백업** 메뉴에서 정기적으로 백업 파일을 내려받고, 다른 기기에서는 복원 기능으로 불러오세요.
- 여러 기기에서 함께 쓰려면 다음 단계로 DB(예: Supabase) 연동이 필요합니다.

### 처음 사용 순서
1. **강사 관리**에서 강사 등록
2. **반 · 수업 관리**에서 반 생성 (요일·시간·수강료 입력)
3. **학생 관리**에서 학생 등록 + 수강반 선택
4. 매월 **학원비 수납 → 이번 달 청구 생성** 후 납부 시 **수납 처리**
5. 수업일마다 **출결 관리**에서 출석 체크
