import { useRef, useState } from 'react';
import { readFileToRows, detectHeader, autoMapColumns, buildTransactions, guessFlipSign, ROLE_LABELS } from '../../lib/finance/parse';
import { won } from '../../lib/finance/format';

// 파일 업로드 → 헤더/열 확인 → 거래 가져오기
export default function ImportPanel({ onImport, existingKeys, hint }) {
  const fileRef = useRef();
  const [over, setOver] = useState(false);
  const [stage, setStage] = useState(null); // {rows, headerIdx, mapping, flip, name}
  const [err, setErr] = useState('');

  const handleFile = async (file) => {
    if (!file) return;
    setErr('');
    try {
      const rows = await readFileToRows(file);
      if (rows.length < 2) throw new Error('데이터가 없는 파일입니다.');
      let headerIdx = detectHeader(rows);
      if (headerIdx < 0) headerIdx = 0;
      const mapping = autoMapColumns(rows[headerIdx]);
      const flip = guessFlipSign(rows, headerIdx, mapping);
      setStage({ rows, headerIdx, mapping, flip, name: file.name });
    } catch (e) {
      setErr(e.message || '파일을 읽을 수 없습니다.');
    }
  };

  const setRole = (col, role) => setStage((s) => ({ ...s, mapping: { ...s.mapping, [col]: role } }));
  const setHeader = (idx) => setStage((s) => ({ ...s, headerIdx: idx, mapping: autoMapColumns(s.rows[idx]) }));

  let preview = null, previewErr = '';
  if (stage) {
    try {
      preview = buildTransactions(stage.rows, stage.headerIdx, stage.mapping, { flipSign: stage.flip, source: stage.name });
    } catch (e) { previewErr = e.message; }
  }
  const dupCount = preview ? preview.filter((t) => existingKeys?.has(t.key)).length : 0;
  const newCount = preview ? preview.length - dupCount : 0;

  const doImport = () => {
    if (!preview) return;
    const fresh = preview.filter((t) => !existingKeys?.has(t.key));
    onImport(fresh, { skipped: dupCount, file: stage.name });
    setStage(null);
  };

  if (!stage) {
    return (
      <div>
        <div
          className={`drop-zone${over ? ' over' : ''}`}
          onClick={() => fileRef.current.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); handleFile(e.dataTransfer.files[0]); }}
        >
          <div style={{ fontSize: 30, marginBottom: 6 }}>📥</div>
          <div style={{ fontSize: 14 }}><strong style={{ color: 'var(--navy)' }}>거래내역 파일을 드래그</strong>하거나 클릭해서 선택</div>
          <div className="note" style={{ marginTop: 6 }}>
            은행·카드사 홈페이지/앱에서 내려받은 엑셀(xlsx·xls)·CSV 파일. {hint || ''}<br />
            파일은 브라우저에서만 처리되며 서버로 업로드되지 않습니다. (AI 분류 시 거래 내용·금액만 전송)
          </div>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv,.txt,.tsv" style={{ display: 'none' }} onChange={(e) => { handleFile(e.target.files[0]); e.target.value = ''; }} />
        </div>
        {err && <div className="banner err" style={{ marginTop: 10 }}>{err}</div>}
      </div>
    );
  }

  const header = stage.rows[stage.headerIdx] || [];
  const sample = stage.rows.slice(stage.headerIdx + 1, stage.headerIdx + 4);
  const hasAmountCol = Object.values(stage.mapping).includes('amount');

  return (
    <div>
      <div className="banner">
        <b>{stage.name}</b> · {stage.rows.length - stage.headerIdx - 1}행 인식. 열 역할을 확인하고 <b>가져오기</b>를 누르세요.
      </div>
      <div className="btn-row" style={{ marginBottom: 10 }}>
        <label className="fl" style={{ margin: 0 }}>헤더 행</label>
        <select value={stage.headerIdx} onChange={(e) => setHeader(Number(e.target.value))}>
          {stage.rows.slice(0, 30).map((r, i) => (
            <option key={i} value={i}>{i + 1}행: {r.slice(0, 5).map((c) => String(c ?? '').slice(0, 10)).join(' | ')}</option>
          ))}
        </select>
        {hasAmountCol && (
          <label style={{ fontSize: 13, display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={stage.flip} onChange={(e) => setStage((s) => ({ ...s, flip: e.target.checked }))} />
            금액이 모두 지출(카드 명세)
          </label>
        )}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="tbl">
          <thead>
            <tr>{header.map((h, i) => <th key={i}>{String(h ?? '') || `(열 ${i + 1})`}</th>)}</tr>
            <tr>
              {header.map((_, i) => (
                <th key={i}>
                  <select value={stage.mapping[i] || 'skip'} onChange={(e) => setRole(i, e.target.value)} style={{ fontSize: 12 }}>
                    {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sample.map((r, ri) => (
              <tr key={ri}>{header.map((_, i) => <td key={i} className="muted">{r[i] instanceof Date ? r[i].toLocaleDateString('ko-KR') : String(r[i] ?? '').slice(0, 18)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {previewErr && <div className="banner err" style={{ marginTop: 10 }}>{previewErr}</div>}
      {preview && (
        <div className="banner ok" style={{ marginTop: 10 }}>
          거래 {preview.length}건 인식 (신규 {newCount}건{dupCount ? `, 중복 ${dupCount}건 제외` : ''}) ·
          입금 {won(preview.filter((t) => t.amount > 0).reduce((a, t) => a + t.amount, 0))} ·
          출금 {won(preview.filter((t) => t.amount < 0).reduce((a, t) => a - t.amount, 0))}
          {preview[0] && <> · 기간 {preview.map((t) => t.date).sort()[0]} ~ {preview.map((t) => t.date).sort().slice(-1)[0]}</>}
        </div>
      )}
      <div className="btn-row" style={{ marginTop: 12 }}>
        <button className="btn btn-primary" disabled={!preview || !newCount} onClick={doImport}>가져오기 ({newCount}건)</button>
        <button className="btn btn-ghost" onClick={() => setStage(null)}>취소</button>
      </div>
    </div>
  );
}
