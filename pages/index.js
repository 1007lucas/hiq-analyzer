import Head from 'next/head';
import { useState, useRef } from 'react';

export default function Home() {
  const [level, setLevel] = useState('고2');
  const [book, setBook] = useState('NE능률(오선영)');
  const [outputType, setOutputType] = useState('both');
  const [qtype, setQtype] = useState('mixed');
  const [qcount, setQcount] = useState('5');
  const [activeTab, setActiveTab] = useState('text');
  const [textInput, setTextInput] = useState('');
  const [pdfText, setPdfText] = useState('');
  const [pdfStatus, setPdfStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [progressPct, setProgressPct] = useState(0);
  const [analysisData, setAnalysisData] = useState(null);
  const [questionsData, setQuestionsData] = useState(null);
  const [reviewDone, setReviewDone] = useState(false);
  const [toast, setToast] = useState('');
  const fileRef = useRef();

  // ── Toast ──
  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2800);
  };

  // ── PDF 처리 ──
  const handlePDF = async (file) => {
    if (!file || file.type !== 'application/pdf') { showToast('PDF 파일만 업로드할 수 있습니다.'); return; }
    setPdfStatus('📖 PDF 읽는 중...');
    try {
      const pdfjsLib = (await import('pdfjs-dist')).default;
      pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js`;
      const buf = await file.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
      let text = '';
      for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const content = await page.getTextContent();
        text += content.items.map(s => s.str).join(' ') + '\n';
      }
      setPdfText(text.trim());
      setPdfStatus(`✅ 추출 완료 — ${pdf.numPages}페이지, ${text.trim().length}자`);
    } catch {
      setPdfStatus('❌ PDF 읽기 실패. 텍스트 포함 PDF인지 확인해주세요.');
    }
  };

  // ── API 호출 ──
  const callAPI = async (prompt, onProgress) => {
    onProgress();
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `오류 (${res.status})`);
    return data.result;
  };

  // ── JSON 추출 ──
  const extractJSON = (raw) => {
    const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (fenced) return fenced[1].trim();
    const start = raw.indexOf('{');
    const end = raw.lastIndexOf('}');
    if (start !== -1 && end !== -1) return raw.slice(start, end + 1);
    return raw;
  };

  // ── 분석 프롬프트 ──
  const buildAnalysisPrompt = (passage) => `당신은 한국 고등학교 영어 교재 분석 전문가입니다.
아래 조건에 맞게 지문을 문장 단위로 분석하세요.

[조건]
- 학교급/학년: ${level}
- 교재: ${book}
- 출력 형식: 아래 JSON 형식을 반드시 준수할 것

[지문]
${passage}

[출력 형식 — 반드시 유효한 JSON만 출력, 다른 텍스트 없음]
{
  "sentences": [
    {
      "no": 1,
      "en": "원문 문장",
      "ko": "정확한 우리말 해석",
      "points": [
        {
          "label": "구문 포인트 이름",
          "struct": "《형태 표기》",
          "desc": "설명 — 어법 함정은 (×)잘못된형태 포함"
        }
      ]
    }
  ]
}

[분석 기준]
1. 모든 문장 빠짐없이 분석
2. 구문 포인트 문장당 1~5개 (중요도 순)
3. 내신 빈출 구문 우선: 가정법·관계사·수동태·5형식·분사구문·수일치·병렬
4. struct 필드에 《》기호로 구조 표기
5. 오답 형태는 (×)로 표기
6. 해석은 교과서 수준으로 정확하게`;

  // ── 문제 프롬프트 ──
  const buildQPrompt = (passage) => {
    const typeDesc = {
      mixed: '어법 선택형, 빈칸 추론, 서술형, 어순 배열을 균형 있게',
      grammar: '어법상 옳은/틀린 것 고르기 5지선다만',
      blank: '빈칸에 알맞은 말 쓰거나 고르기만',
      writing: '조건에 맞게 영작하거나 문장 변형하는 서술형만',
    };
    return `당신은 ${level} 영어 내신 문제 전문 출제위원입니다.
아래 지문으로 내신 시험 문제를 출제하세요.

[조건]
- 학교급/학년: ${level}
- 교재: ${book}
- 문제 수: ${qcount}문제
- 유형: ${typeDesc[qtype]}
- 답이 명확하고 근거가 지문에 있어야 함

[지문]
${passage}

[출력 형식 — 반드시 유효한 JSON만 출력]
{
  "questions": [
    {
      "no": 1,
      "type": "grammar|blank|writing|arrange",
      "type_label": "유형명",
      "question": "문제 전문",
      "choices": ["① 선택지1", "② 선택지2", "③ 선택지3", "④ 선택지4", "⑤ 선택지5"],
      "answer": "정답",
      "explanation": "정답 근거 및 오답 분석"
    }
  ]
}

[출제 기준]
1. 선택형은 5지선다 (choices 필수)
2. 서술형/배열은 choices를 빈 배열 []로
3. 정답 2개 이상인 문제 만들지 말 것
4. 문법 용어는 ${level} 수준에 맞게
5. 지문 외 내용 묻지 말 것`;
  };

  // ── 검수 프롬프트 ──
  const buildReviewPrompt = (rawJSON) => `당신은 ${level} 영어 내신 문제 검토 전문가입니다.
아래 문제 JSON을 검토하고 오류를 수정해서 완성된 JSON을 반환하세요.

[검토 기준]
1. 정답이 틀렸거나 근거 불명확한 문제 → 수정
2. 선택형인데 정답 2개 이상 → 수정
3. ${level} 수준에 맞지 않는 문제 → 수정
4. 발문이 모호하거나 조건 불충분 → 수정
5. 서술형 모범답안 범위 너무 넓음 → 수정

[입력 JSON]
${rawJSON}

[출력 — 수정된 완성 JSON만, 다른 텍스트 없음]`;

  // ── 실행 ──
  const run = async () => {
    const passage = activeTab === 'text' ? textInput.trim() : pdfText.trim();
    if (!passage) { showToast('지문을 입력해주세요.'); return; }

    setBusy(true);
    setAnalysisData(null);
    setQuestionsData(null);
    setReviewDone(false);
    setProgressPct(0);

    try {
      if (outputType === 'analysis' || outputType === 'both') {
        setProgressMsg('문장 구조 분석 중...');
        setProgressPct(20);
        const raw = await callAPI(buildAnalysisPrompt(passage), () => setProgressPct(40));
        try { setAnalysisData(JSON.parse(extractJSON(raw))); } catch { setAnalysisData({ _raw: raw }); }
        setProgressPct(55);
      }

      if (outputType === 'questions' || outputType === 'both') {
        setProgressMsg('문제 생성 중...');
        setProgressPct(60);
        const rawQ = await callAPI(buildQPrompt(passage), () => setProgressPct(72));
        setProgressMsg('자동 검수 중...');
        setProgressPct(80);
        const reviewed = await callAPI(buildReviewPrompt(rawQ), () => setProgressPct(92));
        try { setQuestionsData(JSON.parse(extractJSON(reviewed))); } catch { setQuestionsData({ _raw: reviewed }); }
        setReviewDone(true);
      }

      setProgressPct(100);
      setProgressMsg('완료!');
    } catch (e) {
      showToast('오류: ' + e.message);
    }

    setBusy(false);
  };

  // ── 복사 ──
  const copyText = (text, btnId) => {
    navigator.clipboard.writeText(text).then(() => {
      const el = document.getElementById(btnId);
      if (el) { const orig = el.textContent; el.textContent = '✓ 복사됨'; el.style.background='var(--green)'; el.style.color='#fff'; setTimeout(() => { el.textContent = orig; el.style.background=''; el.style.color=''; }, 2000); }
    });
  };

  const analysisPlain = (data) => {
    if (!data?.sentences) return '';
    return data.sentences.map(s =>
      `【${String(s.no).padStart(2,'0')}】 ${s.en}\n해석  ${s.ko}\n` +
      (s.points || []).map(p => `[${p.label}]  ${p.struct||''}  ${p.desc}`).join('\n')
    ).join('\n\n');
  };

  const questionsPlain = (data) => {
    if (!data?.questions) return '';
    return data.questions.map(q =>
      `[${q.type_label}] ${q.no}번\n${q.question}\n` +
      (q.choices||[]).map((c,i) => `  ${i+1}. ${c}`).join('\n') +
      `\n정답: ${q.answer}\n해설: ${q.explanation||''}`
    ).join('\n\n');
  };

  return (
    <>
      <Head>
        <title>HIQ 지문 분석기</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700;900&display=swap" rel="stylesheet" />
      </Head>

      <style>{`
        :root{--navy:#1F3864;--navy2:#15264A;--navylt:#2a4a80;--gold:#B08A2E;--goldl:#D8C28A;--goldfaint:#f5efd6;--paper:#F8F7F3;--white:#ffffff;--ink:#1a1a1a;--gray:#6b7280;--graylt:#e5e7eb;--red:#B23A2E;--redfaint:#fdf2f0;--green:#1a6b3a;--greenfaint:#f0faf4;--border:#d1d5db;}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
        body{font-family:'Noto Sans KR','Malgun Gothic',sans-serif;background:var(--paper);color:var(--ink);min-height:100vh;line-height:1.65;}
        header{background:var(--navy);padding:0 28px;display:flex;align-items:center;justify-content:space-between;height:58px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25);}
        .logo{display:flex;align-items:center;gap:12px;}
        .logo-mark{width:34px;height:34px;background:var(--gold);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:14px;color:var(--navy2);letter-spacing:.04em;}
        .logo-text{color:#fff;font-weight:700;font-size:15px;}
        .logo-sub{color:var(--goldl);font-size:11px;font-weight:400;display:block;margin-top:-2px;}
        .badge{font-size:11px;color:var(--goldl);border:1px solid rgba(216,194,138,.4);padding:3px 10px;letter-spacing:.06em;}
        .main{max-width:900px;margin:0 auto;padding:32px 20px 80px;}
        .card{background:var(--white);border:1px solid var(--border);border-top:3px solid var(--navy);padding:24px;margin-bottom:22px;box-shadow:0 2px 12px rgba(31,56,100,.10);}
        .step-label{display:flex;align-items:center;gap:10px;margin-bottom:14px;}
        .step-num{width:26px;height:26px;background:var(--navy);color:#fff;font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
        .step-title{font-weight:700;font-size:15px;color:var(--navy);}
        .opts{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:18px;}
        .opts2{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
        .og label{display:block;font-size:11px;font-weight:700;color:var(--gray);letter-spacing:.06em;text-transform:uppercase;margin-bottom:5px;}
        select,textarea,input[type=text]{width:100%;padding:8px 10px;border:1px solid var(--border);background:var(--paper);font-size:13.5px;color:var(--ink);font-family:inherit;}
        select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236b7280' stroke-width='1.5' fill='none'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;background-color:var(--paper);}
        select:focus,textarea:focus{outline:2px solid var(--navy);outline-offset:1px;}
        textarea{min-height:180px;resize:vertical;line-height:1.7;font-size:14px;}
        textarea::placeholder{color:#b0b8c4;}
        .tabs{display:flex;border-bottom:2px solid var(--graylt);margin-bottom:16px;}
        .tab{padding:8px 20px;font-size:13.5px;font-weight:600;color:var(--gray);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:color .15s,border-color .15s;}
        .tab.active{color:var(--navy);border-bottom-color:var(--navy);}
        .drop-zone{border:2px dashed var(--border);padding:40px 20px;text-align:center;cursor:pointer;transition:border-color .2s,background .2s;background:var(--paper);}
        .drop-zone:hover{border-color:var(--navy);background:#eef2f8;}
        .btn-row{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap;}
        .btn{padding:10px 22px;font-size:14px;font-weight:700;cursor:pointer;border:none;transition:all .15s;display:inline-flex;align-items:center;gap:7px;}
        .btn-primary{background:var(--navy);color:#fff;}
        .btn-primary:hover{background:var(--navylt);}
        .btn-primary:disabled{background:#9aafcc;cursor:not-allowed;}
        .btn-ghost{background:transparent;color:var(--navy);border:1.5px solid var(--navy);}
        .btn-ghost:hover{background:#eef2f8;}
        .btn-sm{padding:6px 14px;font-size:12.5px;}
        .btn-copy{background:var(--greenfaint);color:var(--green);border:1px solid #a7d4b8;cursor:pointer;padding:6px 14px;font-size:12.5px;font-weight:700;}
        .btn-copy:hover{background:#d4f0e0;}
        .prog-wrap{margin-top:18px;}
        .prog-bar-out{height:5px;background:var(--graylt);overflow:hidden;margin-top:6px;}
        .prog-bar-in{height:100%;background:var(--gold);transition:width .4s ease;}
        .prog-msg{font-size:13px;color:var(--gray);}
        .spinner{width:14px;height:14px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:inline-block;}
        @keyframes spin{to{transform:rotate(360deg)}}
        .out-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px;}
        .out-title{font-size:15px;font-weight:700;color:var(--navy);}
        .sent-box{background:#f0f3f9;border:1px solid #d0d8e8;border-left:8px solid var(--navy);padding:13px 16px;font-weight:700;font-size:14.5px;line-height:1.7;margin-bottom:8px;}
        .sent-no{color:var(--gold);font-weight:800;margin-right:6px;}
        .ko-line{padding:6px 0 2px 4px;font-size:14px;color:#333;}
        .ko-label{color:var(--navy);font-weight:700;margin-right:6px;}
        .pt-line{padding:5px 4px 5px 18px;font-size:13.5px;color:#444;line-height:1.6;}
        .pt-label{color:var(--red);font-weight:700;}
        .pt-struct{color:var(--navy);font-weight:600;}
        .ab{margin-bottom:28px;}
        .qblock{margin-bottom:22px;}
        .q-head{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
        .q-badge{font-size:11px;font-weight:700;letter-spacing:.05em;padding:3px 9px;color:#fff;}
        .bg-grammar{background:var(--navy);}
        .bg-blank{background:var(--navylt);}
        .bg-writing{background:var(--red);}
        .bg-arrange{background:#5a7a3a;}
        .q-text{font-size:14px;line-height:1.75;margin-bottom:8px;white-space:pre-wrap;}
        .q-choices{list-style:none;padding:0;}
        .q-choices li{padding:5px 0 5px 20px;font-size:13.5px;position:relative;}
        .q-choices li::before{content:attr(data-num)'.';position:absolute;left:0;color:var(--gray);font-weight:600;}
        .answer-box{margin-top:8px;background:var(--goldfaint);border-left:4px solid var(--gold);padding:8px 12px;font-size:13px;}
        .answer-label{font-weight:700;color:var(--gold);margin-right:6px;}
        .explain-box{margin-top:4px;background:#f0f3f9;border-left:4px solid var(--navy);padding:8px 12px;font-size:13px;}
        .explain-label{font-weight:700;color:var(--navy);margin-right:6px;}
        .review-banner{background:var(--greenfaint);border:1px solid #a7d4b8;padding:10px 14px;font-size:13px;color:var(--green);margin-bottom:18px;display:flex;align-items:center;gap:8px;}
        .divider{height:1px;background:var(--graylt);margin:20px 0;}
        .toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:var(--navy);color:#fff;padding:10px 22px;font-size:13.5px;font-weight:600;box-shadow:0 8px 32px rgba(31,56,100,.16);z-index:999;pointer-events:none;}
        @media(max-width:600px){.opts{grid-template-columns:1fr 1fr;}.opts .og:last-child{grid-column:1/-1;}header{padding:0 14px;}.main{padding:20px 12px 60px;}}
      `}</style>

      <header>
        <div className="logo">
          <div className="logo-mark">HIQ</div>
          <div className="logo-text">
            지문 분석기
            <span className="logo-sub">HIQ입시학원 · 영어교육연구소</span>
          </div>
        </div>
        <div className="badge">BETA</div>
      </header>

      <div className="main">

        {/* STEP 1 옵션 */}
        <div className="card">
          <div className="step-label">
            <div className="step-num">1</div>
            <div className="step-title">분석 조건 설정</div>
          </div>
          <div className="opts">
            <div className="og"><label>학교급 · 학년</label>
              <select value={level} onChange={e=>setLevel(e.target.value)}>
                <option value="고1">고1 (영어)</option>
                <option value="고2">고2 (영어I)</option>
                <option value="고3">고3 (영어II)</option>
                <option value="중3">중3</option>
                <option value="중2">중2</option>
              </select>
            </div>
            <div className="og"><label>출판사 · 교재</label>
              <select value={book} onChange={e=>setBook(e.target.value)}>
                <option value="NE능률(오선영)">NE능률 (오선영)</option>
                <option value="천재(이재영)">천재 (이재영)</option>
                <option value="YBM(박준언)">YBM (박준언)</option>
                <option value="비상(홍민표)">비상 (홍민표)</option>
                <option value="능률(김성곤)">능률 (김성곤)</option>
                <option value="기타">기타</option>
              </select>
            </div>
            <div className="og"><label>출력 항목</label>
              <select value={outputType} onChange={e=>setOutputType(e.target.value)}>
                <option value="both">분석 + 문제 생성</option>
                <option value="analysis">분석만</option>
                <option value="questions">문제만</option>
              </select>
            </div>
          </div>
          <div className="opts2">
            <div className="og"><label>문제 유형</label>
              <select value={qtype} onChange={e=>setQtype(e.target.value)}>
                <option value="mixed">혼합 (어법+빈칸+서술형+배열)</option>
                <option value="grammar">어법 선택형만</option>
                <option value="blank">빈칸 추론만</option>
                <option value="writing">서술형만</option>
              </select>
            </div>
            <div className="og"><label>문제 수</label>
              <select value={qcount} onChange={e=>setQcount(e.target.value)}>
                <option value="3">3문제</option>
                <option value="5">5문제</option>
                <option value="8">8문제</option>
                <option value="10">10문제</option>
              </select>
            </div>
          </div>
        </div>

        {/* STEP 2 입력 */}
        <div className="card">
          <div className="step-label">
            <div className="step-num">2</div>
            <div className="step-title">지문 입력</div>
          </div>
          <div className="tabs">
            <div className={`tab${activeTab==='text'?' active':''}`} onClick={()=>setActiveTab('text')}>텍스트 직접 입력</div>
            <div className={`tab${activeTab==='pdf'?' active':''}`} onClick={()=>setActiveTab('pdf')}>PDF 업로드</div>
          </div>

          {activeTab==='text' && (
            <textarea
              value={textInput}
              onChange={e=>setTextInput(e.target.value)}
              placeholder="영어 지문을 여기에 붙여넣으세요.&#10;&#10;예) Host: Hello, everyone! Welcome to Science Report.&#10;Doctor: Well, I want to begin by asking the audience a question..."
            />
          )}

          {activeTab==='pdf' && (
            <div
              className="drop-zone"
              onClick={()=>fileRef.current.click()}
              onDragOver={e=>e.preventDefault()}
              onDrop={e=>{e.preventDefault();handlePDF(e.dataTransfer.files[0]);}}
            >
              <div style={{fontSize:36,marginBottom:10}}>📄</div>
              <div style={{fontSize:14,color:'var(--gray)'}}>
                <strong style={{color:'var(--navy)'}}>PDF 파일을 여기에 드래그</strong>하거나 클릭해서 선택
              </div>
              <div style={{fontSize:12,color:'var(--gray)',marginTop:6}}>텍스트가 포함된 PDF만 지원 (스캔 이미지 PDF 불가)</div>
              {pdfStatus && <div style={{fontSize:13,color:'var(--navy)',marginTop:10,fontWeight:600}}>{pdfStatus}</div>}
              <input ref={fileRef} type="file" accept=".pdf" style={{display:'none'}} onChange={e=>handlePDF(e.target.files[0])} />
            </div>
          )}

          <div className="btn-row">
            <button className="btn btn-primary" onClick={run} disabled={busy}>
              {busy && <span className="spinner" />}
              {busy ? '분석 중...' : '분석 시작'}
            </button>
            <button className="btn btn-ghost" onClick={()=>{setTextInput('');setPdfText('');setPdfStatus('');setAnalysisData(null);setQuestionsData(null);setReviewDone(false);setBusy(false);setProgressPct(0);}}>초기화</button>
          </div>

          {busy && (
            <div className="prog-wrap">
              <div className="prog-msg">{progressMsg}</div>
              <div className="prog-bar-out"><div className="prog-bar-in" style={{width:progressPct+'%'}} /></div>
            </div>
          )}
        </div>

        {/* STEP 3 결과 */}
        {(analysisData || questionsData) && (
          <div>
            {reviewDone && (
              <div className="review-banner">
                ✅ 자동 검수 완료 — 문제 오류·난이도 미달 항목을 수정했습니다.
              </div>
            )}

            {/* 분석 결과 */}
            {analysisData && (
              <div className="card">
                <div className="out-header">
                  <div className="out-title">📋 본문 문장 분석</div>
                  <button id="btn-copy-analysis" className="btn-copy" onClick={()=>copyText(analysisPlain(analysisData),'btn-copy-analysis')}>복사</button>
                </div>
                {analysisData._raw ? (
                  <pre style={{fontSize:13,whiteSpace:'pre-wrap',color:'var(--red)'}}>{analysisData._raw}</pre>
                ) : (
                  (analysisData.sentences||[]).map(s => (
                    <div className="ab" key={s.no}>
                      <div className="sent-box"><span className="sent-no">{String(s.no).padStart(2,'0')}</span>{s.en}</div>
                      <div className="ko-line"><span className="ko-label">해석</span>{s.ko}</div>
                      {(s.points||[]).map((p,i) => (
                        <div className="pt-line" key={i}>
                          <span className="pt-label">[{p.label}]</span>{'  '}
                          <span className="pt-struct">{p.struct||''}</span>{'  '}
                          {p.desc}
                        </div>
                      ))}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* 문제 결과 */}
            {questionsData && (
              <div className="card">
                <div className="out-header">
                  <div className="out-title">📝 내신 대비 문제</div>
                  <button id="btn-copy-q" className="btn-copy" onClick={()=>copyText(questionsPlain(questionsData),'btn-copy-q')}>복사</button>
                </div>
                {questionsData._raw ? (
                  <pre style={{fontSize:13,whiteSpace:'pre-wrap',color:'var(--red)'}}>{questionsData._raw}</pre>
                ) : (
                  (questionsData.questions||[]).map((q,idx) => {
                    const bc = {grammar:'bg-grammar',blank:'bg-blank',writing:'bg-writing',arrange:'bg-arrange'}[q.type]||'bg-grammar';
                    return (
                      <div key={q.no}>
                        <div className="qblock">
                          <div className="q-head">
                            <span className={`q-badge ${bc}`}>{q.type_label||q.type}</span>
                            <span style={{fontSize:13,fontWeight:700,color:'var(--gray)'}}>{q.no}번</span>
                          </div>
                          <div className="q-text">{q.question}</div>
                          {(q.choices||[]).length>0 && (
                            <ul className="q-choices">
                              {q.choices.map((c,i)=><li key={i} data-num={i+1}>{c}</li>)}
                            </ul>
                          )}
                          <div className="answer-box"><span className="answer-label">정답</span>{q.answer}</div>
                          <div className="explain-box"><span className="explain-label">해설</span>{q.explanation||''}</div>
                        </div>
                        {idx < (questionsData.questions||[]).length-1 && <div className="divider" />}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {toast && <div className="toast">{toast}</div>}
    </>
  );
}
