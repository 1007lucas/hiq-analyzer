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
