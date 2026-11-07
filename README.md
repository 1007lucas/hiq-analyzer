# HIQ 지문 분석기

영어 지문을 붙여넣거나 PDF를 올리면 구문 분석 + 내신 문제를 자동 생성합니다.

## 표지 디자이너 (`/cover`)

학원교재·개인출판 책의 **인쇄용 표지**를 브라우저에서 바로 만듭니다.

- **내용 입력**: 제목·부제·캐치프레이즈·학년·시리즈·저자·뒤표지 소개글·특징·ISBN·정가
- **AI 문구 제안**: 제목과 대상만 넣고 버튼을 누르면 부제/캐치프레이즈/뱃지/소개글/특징을 자동 작성 (`ANTHROPIC_API_KEY` 필요)
- **판형**: 4×6배판(188×257, 학원교재 표준)·B5·A4·크라운판·신국판·A5·직접 입력
- **책등 자동 계산**: 본문 쪽수 × 용지 두께로 세네카 폭 산출 (인쇄소 수치로 직접 지정 가능)
- **도련(재단 여백) 3mm + 재단선·접지선** 자동 표시
- **템플릿 6종**: 아카데믹 클래식 · 모던 그리드 · 볼드 타이포 · 미니멀 라인 · 그라디언트 · 다크 프리미엄
- **팔레트 8종 + 색상 직접 지정**, 한글 서체 6종(명조/고딕/제목용), 제목 크기 조절
- **ISBN 바코드**: EAN-13 + 부가기호(EAN-5) 실제 규격으로 생성, 체크디지트 자동 보정
- **미리보기**: 앞표지 / 뒤표지 / 펼침면(뒤·책등·앞)
- **내보내기**: PNG 300dpi, 인쇄용 PDF(브라우저 인쇄 → "PDF로 저장", 용지 크기 자동 설정)
- 작업 내용은 브라우저에 자동 저장되며 `.json`으로 저장/불러오기 가능

> 인쇄소 입고 시: 펼침면 PDF(도련 포함, 재단선 ON)를 전달하고, 책등 두께는 인쇄소 견적서 값을 "직접 지정"에 입력하세요.

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
