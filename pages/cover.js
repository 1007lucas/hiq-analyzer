import Head from 'next/head';
import Link from 'next/link';
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import CoverRender, { coverDims } from '../components/cover/CoverRender';
import {
  MM, TRIMS, PAPERS, PALETTES, FONTS, TEMPLATES, DEFAULT_DESIGN, GOOGLE_FONTS_HREF,
  getPalette, getTrim, getSpine,
} from '../lib/cover/constants';

const STORAGE_KEY = 'hiq-cover-design-v1';

export default function CoverDesigner() {
  const [d, setD] = useState(DEFAULT_DESIGN);
  const [mode, setMode] = useState('front');
  const [panel, setPanel] = useState('content');
  const [scale, setScale] = useState(0.5);
  const [busy, setBusy] = useState('');
  const [toast, setToast] = useState('');
  const [aiNote, setAiNote] = useState('');
  const previewRef = useRef(null);
  const exportRef = useRef(null);
  const fileRef = useRef(null);
  const loaded = useRef(false);

  const set = (k) => (e) => setD((p) => ({ ...p, [k]: e && e.target ? e.target.value : e }));
  const showToast = (m) => { setToast(m); setTimeout(() => setToast(''), 2800); };

  // ── 저장/복원 (localStorage) ──
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setD({ ...DEFAULT_DESIGN, ...JSON.parse(raw) });
    } catch {}
    loaded.current = true;
  }, []);
  useEffect(() => {
    if (!loaded.current) return;
    const t = setTimeout(() => { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(d)); } catch {} }, 400);
    return () => clearTimeout(t);
  }, [d]);

  // ── 미리보기 배율 ──
  const dims = useMemo(() => coverDims(d, mode), [d, mode]);
  useEffect(() => {
    const fit = () => {
      const el = previewRef.current;
      if (!el) return;
      const availW = el.clientWidth - 32;
      const availH = Math.max(420, window.innerHeight - 190);
      const sc = Math.min(availW / (dims.totalW * MM), availH / (dims.totalH * MM), 1);
      setScale(Math.max(0.08, sc));
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [dims]);

  // ── 내보내기: PNG (300dpi) ──
  const exportPng = async () => {
    const node = exportRef.current && exportRef.current.firstElementChild;
    if (!node) return;
    setBusy('png');
    try {
      await document.fonts.ready;
      const { toPng } = await import('html-to-image');
      const pixelRatio = 300 / 96;
      const dataUrl = await toPng(node, { pixelRatio, cacheBust: true, backgroundColor: '#ffffff', style: { position: 'static', left: '0', top: '0' } });
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = `${(d.title || '표지').replace(/\s+/g, '_').replace(/\n/g, '_')}_${{ front: '앞표지', back: '뒤표지', wrap: '펼침면' }[mode]}_300dpi.png`;
      a.click();
      showToast('PNG(300dpi) 저장 완료');
    } catch (e) {
      showToast('PNG 저장 실패: ' + e.message);
    }
    setBusy('');
  };

  // ── 내보내기: PDF (브라우저 인쇄 → PDF 저장) ──
  const exportPdf = async () => {
    await document.fonts.ready;
    showToast('인쇄 대화상자에서 "PDF로 저장"을 선택하세요. 용지 크기는 자동 설정됩니다.');
    setTimeout(() => window.print(), 300);
  };

  // ── 디자인 JSON 저장/불러오기 ──
  const saveJson = () => {
    const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(d.title || '표지').replace(/\s+/g, '_').replace(/\n/g, '_')}_표지디자인.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
  const loadJson = (file) => {
    if (!file) return;
    const r = new FileReader();
    r.onload = () => {
      try { setD({ ...DEFAULT_DESIGN, ...JSON.parse(r.result) }); showToast('디자인을 불러왔습니다.'); }
      catch { showToast('올바른 디자인 파일이 아닙니다.'); }
    };
    r.readAsText(file);
  };
  const reset = () => {
    if (!confirm('모든 내용을 기본값으로 되돌릴까요?')) return;
    setD(DEFAULT_DESIGN);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  };

  // ── AI 카피 제안 ──
  const aiCopy = async () => {
    setBusy('ai');
    setAiNote('');
    const prompt = `당신은 교육 출판 전문 카피라이터이자 북 디자이너입니다. 아래 교재 정보를 바탕으로 표지에 들어갈 문구를 제안하세요.

[교재 정보]
- 제목: ${d.title.replace(/\n/g, ' ')}
- 시리즈: ${d.series}
- 대상: ${d.level} ${d.subject}
- 저자/기관: ${d.author}
- 현재 부제: ${d.subtitle}
- 현재 설명: ${d.blurb}

[요구 사항]
1. subtitle: 부제 (25자 이내, 교재의 핵심 가치를 한 줄로)
2. tagline: 앞표지 캐치프레이즈 (20자 이내, 임팩트 있게)
3. badge: 원형 뱃지 문구 (8자 이내, 예: "내신 1등급")
4. blurb: 뒤표지 소개글 (180~260자, 학생·학부모가 읽는 구매 설득 문단, 과장 없이)
5. features: 이 책의 특징 4개 (각 22자 이내)

[출력 — 반드시 유효한 JSON만, 다른 텍스트 없음]
{"subtitle":"","tagline":"","badge":"","blurb":"","features":["","","",""]}`;
    try {
      const res = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `오류 (${res.status})`);
      const raw = data.result || '';
      const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
      const jsonText = fenced ? fenced[1] : raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1);
      const j = JSON.parse(jsonText);
      setD((p) => ({
        ...p,
        subtitle: j.subtitle || p.subtitle,
        tagline: j.tagline || p.tagline,
        badge: j.badge || p.badge,
        blurb: j.blurb || p.blurb,
        features: Array.isArray(j.features) && j.features.length ? j.features.join('\n') : p.features,
      }));
      setAiNote('AI 제안이 부제·캐치프레이즈·뱃지·소개글·특징에 반영되었습니다. 마음에 들지 않으면 직접 수정하세요.');
    } catch (e) {
      showToast('AI 제안 실패: ' + e.message);
    }
    setBusy('');
  };

  const pal = getPalette(d);
  const trim = getTrim(d);
  const spine = getSpine(d);
  const modeLabel = { front: '앞표지', back: '뒤표지', wrap: '펼침면 (뒤·책등·앞)' };

  return (
    <>
      <Head>
        <title>HIQ 표지 디자이너</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <link href={GOOGLE_FONTS_HREF} rel="stylesheet" />
      </Head>

      <style dangerouslySetInnerHTML={{ __html: `
        :root{--navy:#1F3864;--navy2:#15264A;--navylt:#2a4a80;--gold:#B08A2E;--goldl:#D8C28A;--paper:#F8F7F3;--ink:#1a1a1a;--gray:#6b7280;--graylt:#e5e7eb;--border:#d1d5db;--green:#1a6b3a;--greenfaint:#f0faf4;--red:#B23A2E;}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
        body{font-family:'Noto Sans KR','Malgun Gothic',sans-serif;background:var(--paper);color:var(--ink);line-height:1.6;}
        header{background:var(--navy);padding:0 28px;display:flex;align-items:center;justify-content:space-between;height:58px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25);}
        .logo{display:flex;align-items:center;gap:12px;}
        .logo-mark{width:34px;height:34px;background:var(--gold);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:14px;color:var(--navy2);}
        .logo-text{color:#fff;font-weight:700;font-size:15px;}
        .logo-sub{color:var(--goldl);font-size:11px;font-weight:400;display:block;margin-top:-2px;}
        .nav{display:flex;gap:6px;align-items:center;}
        .nav a{color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:6px 12px;border:1px solid rgba(255,255,255,.25);}
        .nav a:hover{background:rgba(255,255,255,.1);}
        .layout{display:grid;grid-template-columns:400px 1fr;min-height:calc(100vh - 58px);}
        .side{background:#fff;border-right:1px solid var(--border);display:flex;flex-direction:column;height:calc(100vh - 58px);position:sticky;top:58px;}
        .ptabs{display:flex;border-bottom:1px solid var(--border);}
        .ptab{flex:1;text-align:center;padding:11px 0;font-size:13px;font-weight:700;color:var(--gray);cursor:pointer;border-bottom:3px solid transparent;}
        .ptab.active{color:var(--navy);border-bottom-color:var(--navy);}
        .pbody{flex:1;overflow-y:auto;padding:18px 18px 40px;}
        .sec{font-size:11px;font-weight:800;color:var(--gray);letter-spacing:.1em;text-transform:uppercase;margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--graylt);}
        .sec:first-child{margin-top:0;}
        .f{margin-bottom:11px;}
        .f label{display:block;font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;}
        .f .hint{font-weight:400;color:var(--gray);font-size:11px;margin-left:5px;}
        input[type=text],input[type=number],select,textarea{width:100%;padding:7px 9px;border:1px solid var(--border);background:var(--paper);font-size:13px;color:var(--ink);font-family:inherit;}
        input:focus,select:focus,textarea:focus{outline:2px solid var(--navy);outline-offset:1px;}
        textarea{resize:vertical;min-height:64px;line-height:1.6;}
        select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236b7280' stroke-width='1.5' fill='none'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;}
        .row2{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
        .row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;}
        .tpl-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
        .tpl{border:1.5px solid var(--border);padding:9px 10px;cursor:pointer;background:#fff;transition:all .15s;}
        .tpl:hover{border-color:var(--navylt);}
        .tpl.active{border-color:var(--navy);background:#eef2f8;box-shadow:inset 0 0 0 1px var(--navy);}
        .tpl b{display:block;font-size:13px;color:var(--navy);}
        .tpl span{font-size:11px;color:var(--gray);line-height:1.4;display:block;}
        .pal-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;}
        .pal{cursor:pointer;border:2px solid transparent;padding:3px;text-align:center;}
        .pal.active{border-color:var(--navy);}
        .pal .sw{height:28px;display:flex;overflow:hidden;}
        .pal .sw i{flex:1;display:block;}
        .pal small{font-size:10px;color:var(--gray);display:block;margin-top:3px;line-height:1.2;}
        .color-row{display:flex;align-items:center;gap:8px;}
        .color-row input[type=color]{width:38px;height:32px;border:1px solid var(--border);padding:2px;background:#fff;cursor:pointer;}
        input[type=range]{width:100%;accent-color:var(--navy);}
        .chk{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;cursor:pointer;}
        .chk input{accent-color:var(--navy);width:15px;height:15px;}
        .btn{padding:9px 16px;font-size:13px;font-weight:700;cursor:pointer;border:none;display:inline-flex;align-items:center;gap:6px;font-family:inherit;transition:all .15s;}
        .btn-primary{background:var(--navy);color:#fff;}
        .btn-primary:hover{background:var(--navylt);}
        .btn-primary:disabled{background:#9aafcc;cursor:not-allowed;}
        .btn-ghost{background:#fff;color:var(--navy);border:1.5px solid var(--navy);}
        .btn-ghost:hover{background:#eef2f8;}
        .btn-gold{background:var(--gold);color:#fff;}
        .btn-gold:hover{background:#9a7626;}
        .btn-sm{padding:6px 11px;font-size:12px;}
        .btn-row{display:flex;gap:8px;flex-wrap:wrap;}
        .ai-box{background:#fbf7ea;border:1px solid #e7d9a8;padding:12px;margin-bottom:14px;}
        .ai-box p{font-size:12px;color:#6b5a2a;margin-bottom:8px;line-height:1.5;}
        .ai-note{font-size:12px;color:var(--green);background:var(--greenfaint);border:1px solid #a7d4b8;padding:8px 10px;margin-top:8px;}
        .stage{display:flex;flex-direction:column;}
        .stage-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 22px;background:#fff;border-bottom:1px solid var(--border);flex-wrap:wrap;position:sticky;top:58px;z-index:50;}
        .seg{display:inline-flex;border:1.5px solid var(--navy);}
        .seg button{background:#fff;color:var(--navy);border:none;padding:7px 14px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;}
        .seg button.active{background:var(--navy);color:#fff;}
        .meta{font-size:12px;color:var(--gray);}
        .meta b{color:var(--navy);}
        .canvas{flex:1;padding:24px 16px 40px;display:flex;justify-content:center;align-items:flex-start;overflow:auto;background:repeating-conic-gradient(#ececea 0 25%,#f5f5f3 0 50%) 0 0/20px 20px;}
        .cover-wrap{box-shadow:0 12px 40px rgba(0,0,0,.25);transform-origin:top left;}
        .export-root{position:absolute;left:-20000px;top:0;}
        .spinner{width:13px;height:13px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:inline-block;}
        @keyframes spin{to{transform:rotate(360deg)}}
        .toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:var(--navy);color:#fff;padding:10px 22px;font-size:13.5px;font-weight:600;box-shadow:0 8px 32px rgba(31,56,100,.16);z-index:999;pointer-events:none;max-width:90vw;text-align:center;}
        @media(max-width:980px){.layout{grid-template-columns:1fr;}.side{height:auto;position:static;}.pbody{max-height:60vh;}.stage-bar{position:static;}}
        @media print{
          @page{size:${dims.totalW}mm ${dims.totalH}mm;margin:0;}
          html,body{background:#fff !important;margin:0;}
          header,.layout,.toast{display:none !important;}
          .export-root{position:static !important;}
        }
      ` }} />

      <header>
        <div className="logo">
          <div className="logo-mark">HIQ</div>
          <div className="logo-text">
            표지 디자이너
            <span className="logo-sub">학원교재 · 개인출판 · 인쇄용 표지 제작</span>
          </div>
        </div>
        <nav className="nav">
          <Link href="/">지문 분석기 →</Link>
        </nav>
      </header>

      <div className="layout">
        {/* ─────── 좌측 편집 패널 ─────── */}
        <aside className="side">
          <div className="ptabs">
            {[['content', '① 내용'], ['format', '② 판형'], ['style', '③ 디자인']].map(([k, l]) => (
              <div key={k} className={`ptab${panel === k ? ' active' : ''}`} onClick={() => setPanel(k)}>{l}</div>
            ))}
          </div>

          <div className="pbody">
            {panel === 'content' && (
              <>
                <div className="ai-box">
                  <p>제목·대상만 입력하고 누르면 부제, 캐치프레이즈, 뱃지, 뒤표지 소개글, 특징 4가지를 AI가 제안합니다.</p>
                  <button className="btn btn-gold btn-sm" onClick={aiCopy} disabled={busy === 'ai'}>
                    {busy === 'ai' ? <><span className="spinner" /> 작성 중...</> : '✨ AI 표지 문구 제안'}
                  </button>
                  {aiNote && <div className="ai-note">{aiNote}</div>}
                </div>

                <div className="sec">앞표지</div>
                <div className="f"><label>책 제목 <span className="hint">줄바꿈 = Enter</span></label><textarea value={d.title} onChange={set('title')} style={{ minHeight: 56, fontWeight: 700, fontSize: 15 }} /></div>
                <div className="f"><label>부제</label><input type="text" value={d.subtitle} onChange={set('subtitle')} /></div>
                <div className="f"><label>캐치프레이즈</label><input type="text" value={d.tagline} onChange={set('tagline')} /></div>
                <div className="row3">
                  <div className="f"><label>학년·대상</label><input type="text" value={d.level} onChange={set('level')} placeholder="고2" /></div>
                  <div className="f"><label>과목</label><input type="text" value={d.subject} onChange={set('subject')} placeholder="영어 I" /></div>
                  <div className="f"><label>권호</label><input type="text" value={d.volume} onChange={set('volume')} placeholder="Vol. 1" /></div>
                </div>
                <div className="f"><label>시리즈명</label><input type="text" value={d.series} onChange={set('series')} /></div>
                <div className="row2">
                  <div className="f"><label>뱃지 문구 <span className="hint">비우면 숨김</span></label><input type="text" value={d.badge} onChange={set('badge')} /></div>
                  <div className="f"><label>판 표기</label><input type="text" value={d.edition} onChange={set('edition')} /></div>
                </div>
                <div className="row2">
                  <div className="f"><label>저자 · 기관</label><input type="text" value={d.author} onChange={set('author')} /></div>
                  <div className="f"><label>출판사</label><input type="text" value={d.publisher} onChange={set('publisher')} /></div>
                </div>

                <div className="sec">뒤표지</div>
                <div className="f"><label>소개글</label><textarea value={d.blurb} onChange={set('blurb')} style={{ minHeight: 110 }} /></div>
                <div className="f"><label>이 책의 특징 <span className="hint">한 줄에 하나</span></label><textarea value={d.features} onChange={set('features')} style={{ minHeight: 90 }} /></div>
                <div className="f"><label>연락처 · 홈페이지</label><input type="text" value={d.contact} onChange={set('contact')} /></div>
                <div className="row3">
                  <div className="f" style={{ gridColumn: 'span 2' }}><label>ISBN <span className="hint">12~13자리, 체크디지트 자동</span></label><input type="text" value={d.isbn} onChange={set('isbn')} placeholder="979-11-XXXX-XXX-X" /></div>
                  <div className="f"><label>부가기호</label><input type="text" value={d.addon} onChange={set('addon')} placeholder="53740" /></div>
                </div>
                <div className="f"><label>정가</label><input type="text" value={d.price} onChange={set('price')} /></div>
              </>
            )}

            {panel === 'format' && (
              <>
                <div className="sec">판형 (재단 크기)</div>
                <div className="f">
                  <select value={d.trim} onChange={set('trim')}>
                    {Object.entries(TRIMS).map(([k, t]) => <option key={k} value={k}>{t.name}</option>)}
                  </select>
                </div>
                {d.trim === 'custom' && (
                  <div className="row2">
                    <div className="f"><label>가로 (mm)</label><input type="number" value={d.customW} onChange={set('customW')} /></div>
                    <div className="f"><label>세로 (mm)</label><input type="number" value={d.customH} onChange={set('customH')} /></div>
                  </div>
                )}
                <div className="row2">
                  <div className="f"><label>도련 (재단 여백, mm)</label><input type="number" min="0" max="10" step="1" value={d.bleed} onChange={set('bleed')} /></div>
                  <div className="f" style={{ display: 'flex', alignItems: 'flex-end' }}>
                    <label className="chk"><input type="checkbox" checked={!!d.marks} onChange={(e) => setD((p) => ({ ...p, marks: e.target.checked }))} /> 재단선·접지선 표시</label>
                  </div>
                </div>

                <div className="sec">책등 (세네카)</div>
                <div className="row2">
                  <div className="f"><label>본문 쪽수</label><input type="number" min="0" step="2" value={d.pages} onChange={set('pages')} /></div>
                  <div className="f"><label>본문 용지</label>
                    <select value={d.paper} onChange={set('paper')}>
                      {Object.keys(PAPERS).map((k) => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </div>
                </div>
                <div className="f"><label>책등 두께 직접 지정 (mm) <span className="hint">비우면 자동 계산</span></label><input type="number" min="0" step="0.5" value={d.spineOverride} onChange={set('spineOverride')} placeholder={`자동: ${spine}mm`} /></div>
                <div className="meta" style={{ background: '#eef2f8', padding: '10px 12px', lineHeight: 1.7 }}>
                  재단 <b>{trim.w} × {trim.h} mm</b> · 책등 <b>{spine} mm</b><br />
                  펼침면 완성 크기 (도련 포함): <b>{Math.round((trim.w * 2 + spine + d.bleed * 2) * 10) / 10} × {Math.round((trim.h + d.bleed * 2) * 10) / 10} mm</b><br />
                  <span style={{ fontSize: 11 }}>※ 책등 두께는 용지·제본 방식에 따라 달라집니다. 인쇄소 견적서의 수치를 "직접 지정"에 입력하세요.</span>
                </div>
              </>
            )}

            {panel === 'style' && (
              <>
                <div className="sec">템플릿</div>
                <div className="tpl-grid">
                  {TEMPLATES.map((t) => (
                    <div key={t.key} className={`tpl${d.template === t.key ? ' active' : ''}`} onClick={() => setD((p) => ({ ...p, template: t.key }))}>
                      <b>{t.name}</b><span>{t.desc}</span>
                    </div>
                  ))}
                </div>

                <div className="sec">색상 팔레트</div>
                <div className="pal-grid">
                  {PALETTES.map((p) => (
                    <div key={p.key} className={`pal${d.palette === p.key ? ' active' : ''}`} onClick={() => setD((x) => ({ ...x, palette: p.key, customPrimary: '', customAccent: '' }))} title={p.name}>
                      <div className="sw"><i style={{ background: p.primary }} /><i style={{ background: p.accent }} /><i style={{ background: p.bg, border: '1px solid #e5e7eb' }} /></div>
                      <small>{p.name}</small>
                    </div>
                  ))}
                </div>
                <div className="row2" style={{ marginTop: 12 }}>
                  <div className="f"><label>주 색상 직접 지정</label>
                    <div className="color-row"><input type="color" value={d.customPrimary || pal.primary} onChange={set('customPrimary')} /><input type="text" value={d.customPrimary} onChange={set('customPrimary')} placeholder={pal.primary} /></div>
                  </div>
                  <div className="f"><label>강조 색상 직접 지정</label>
                    <div className="color-row"><input type="color" value={d.customAccent || pal.accent} onChange={set('customAccent')} /><input type="text" value={d.customAccent} onChange={set('customAccent')} placeholder={pal.accent} /></div>
                  </div>
                </div>

                <div className="sec">서체</div>
                <div className="f"><label>제목 서체</label>
                  <select value={d.titleFont} onChange={set('titleFont')}>{Object.entries(FONTS).map(([k, f]) => <option key={k} value={k}>{f.name}</option>)}</select>
                </div>
                <div className="f"><label>본문 서체</label>
                  <select value={d.bodyFont} onChange={set('bodyFont')}>{Object.entries(FONTS).map(([k, f]) => <option key={k} value={k}>{f.name}</option>)}</select>
                </div>
                <div className="f"><label>제목 크기 <span className="hint">{Math.round(d.titleScale * 100)}%</span></label>
                  <input type="range" min="0.6" max="1.6" step="0.05" value={d.titleScale} onChange={set('titleScale')} />
                </div>

                <div className="sec">디자인 파일</div>
                <div className="btn-row">
                  <button className="btn btn-ghost btn-sm" onClick={saveJson}>디자인 저장 (.json)</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => fileRef.current.click()}>불러오기</button>
                  <button className="btn btn-ghost btn-sm" style={{ color: 'var(--red)', borderColor: 'var(--red)' }} onClick={reset}>초기화</button>
                  <input ref={fileRef} type="file" accept=".json,application/json" style={{ display: 'none' }} onChange={(e) => { loadJson(e.target.files[0]); e.target.value = ''; }} />
                </div>
                <p className="meta" style={{ marginTop: 8, fontSize: 11 }}>작업 내용은 이 브라우저에 자동 저장됩니다. 다른 기기에서 이어 하려면 .json으로 저장하세요.</p>
              </>
            )}
          </div>
        </aside>

        {/* ─────── 우측 미리보기 ─────── */}
        <section className="stage">
          <div className="stage-bar">
            <div className="seg">
              {['front', 'back', 'wrap'].map((m) => (
                <button key={m} className={mode === m ? 'active' : ''} onClick={() => setMode(m)}>{modeLabel[m]}</button>
              ))}
            </div>
            <div className="meta">
              <b>{modeLabel[mode]}</b> · {trim.w}×{trim.h}mm{mode === 'wrap' ? ` · 책등 ${spine}mm` : ''} · 도련 {d.bleed}mm · 미리보기 {Math.round(scale * 100)}%
            </div>
            <div className="btn-row">
              <button className="btn btn-primary" onClick={exportPng} disabled={!!busy}>
                {busy === 'png' ? <><span className="spinner" /> 생성 중...</> : '⬇ PNG (300dpi)'}
              </button>
              <button className="btn btn-primary" onClick={exportPdf} disabled={!!busy}>🖨 PDF (인쇄용)</button>
            </div>
          </div>

          <div className="canvas" ref={previewRef}>
            <div style={{ width: dims.totalW * MM * scale, height: dims.totalH * MM * scale }}>
              <div className="cover-wrap" style={{ transform: `scale(${scale})` }}>
                <CoverRender design={d} mode={mode} />
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* 내보내기·인쇄용 1:1 렌더 (화면 밖) */}
      <div className="export-root" id="print-root" ref={exportRef}>
        <CoverRender design={d} mode={mode} />
      </div>

      {toast && <div className="toast">{toast}</div>}
    </>
  );
}
