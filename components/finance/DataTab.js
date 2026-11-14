import { useRef, useState } from 'react';
import ImportPanel from './ImportPanel';
import TxTable from './TxTable';
import { applyMemory, runAI, fillDefaults } from '../../lib/finance/categorize';
import { normalizeDesc } from '../../lib/finance/rules';
import { downloadJSON, readJSONFile } from '../../lib/finance/store';

// 거래내역 가져오기 · AI 분류 · 수정 · 백업 (학원/개인 공용)
export default function DataTab({ domain, state, setState, categories, setToast, hint }) {
  const [busy, setBusy] = useState('');
  const [importOpen, setImportOpen] = useState(!(state.txs?.length));
  const restoreRef = useRef();
  const txs = state.txs || [];
  const unclassified = txs.filter((t) => !t.category).length;
  const existingKeys = new Set(txs.map((t) => t.key));

  const classify = async (list, baseState) => {
    const cats = categories;
    const prepared = applyMemory(domain, list, baseState.memory || {});
    const pending = prepared.filter((t) => !t.category).length;
    if (!pending) return { txs: prepared, memory: {} };
    setBusy(`AI 분류 중 (0/${pending})`);
    try {
      const r = await runAI(domain, prepared, cats, (done, total) => setBusy(`AI 분류 중 (${done}/${total})`));
      return { txs: r.txs, memory: r.memory };
    } catch (e) {
      setToast('AI 분류 실패: ' + e.message + ' — 기본 카테고리로 저장했습니다.');
      return { txs: fillDefaults(domain, prepared), memory: {} };
    } finally { setBusy(''); }
  };

  const onImport = async (fresh, meta) => {
    if (!fresh.length) { setToast('새로 추가할 거래가 없습니다.'); return; }
    const r = await classify(fresh, state);
    setState((s) => ({ ...s, txs: [...(s.txs || []), ...r.txs], memory: { ...(s.memory || {}), ...r.memory } }));
    setToast(`${fresh.length}건 가져왔습니다.${meta.skipped ? ` (중복 ${meta.skipped}건 제외)` : ''}`);
    setImportOpen(false);
  };

  const reclassify = async () => {
    const r = await classify(txs.map((t) => (t.locked ? t : { ...t, category: null, how: null })), state);
    setState((s) => ({ ...s, txs: r.txs, memory: { ...(s.memory || {}), ...r.memory } }));
    setToast('재분류했습니다.');
  };

  const onChangeCategory = (tx, cat) => {
    const k = normalizeDesc(tx.desc);
    setState((s) => ({
      ...s,
      memory: { ...(s.memory || {}), [k]: cat },
      txs: s.txs.map((t) => {
        if (t.id === tx.id) return { ...t, category: cat, how: 'manual', locked: true };
        if (!t.locked && normalizeDesc(t.desc) === k && Math.sign(t.amount) === Math.sign(tx.amount)) return { ...t, category: cat, how: 'memory' };
        return t;
      }),
    }));
  };

  const onDelete = (tx) => setState((s) => ({ ...s, txs: s.txs.filter((t) => t.id !== tx.id) }));
  const clearAll = () => {
    if (!window.confirm('모든 거래내역을 삭제할까요? (학생·강사·예산 등 다른 데이터는 유지됩니다)')) return;
    setState((s) => ({ ...s, txs: [] }));
  };
  const backup = () => downloadJSON(state, `hiq-finance-${domain}-${new Date().toISOString().slice(0, 10)}.json`);
  const restore = async (file) => {
    if (!file) return;
    try {
      const data = await readJSONFile(file);
      if (!data || typeof data !== 'object' || !Array.isArray(data.txs)) throw new Error('백업 파일 형식이 아닙니다.');
      if (!window.confirm('현재 데이터를 백업 파일 내용으로 교체할까요?')) return;
      setState(data);
      setToast('복원했습니다.');
    } catch (e) { setToast(e.message); }
  };

  return (
    <>
      <div className="card">
        <div className="card-title">
          <span>거래내역 가져오기 <small>{txs.length ? `${txs.length}건 저장됨` : '아직 없음'}</small></span>
          <div className="btn-row">
            {txs.length > 0 && <button className="btn btn-sm btn-ghost" onClick={() => setImportOpen((v) => !v)}>{importOpen ? '닫기' : '+ 파일 추가'}</button>}
          </div>
        </div>
        {importOpen && <ImportPanel onImport={onImport} existingKeys={existingKeys} hint={hint} />}
        {busy && <div className="banner" style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}><span className="spinner dark" />{busy}</div>}
      </div>

      {txs.length > 0 && (
        <div className="card">
          <div className="card-title">
            <span>거래내역 {unclassified > 0 && <span className="chip amber">미분류 {unclassified}건</span>}</span>
            <div className="btn-row">
              <button className="btn btn-sm btn-ghost" disabled={!!busy} onClick={reclassify}>AI 재분류</button>
              <button className="btn btn-sm btn-ghost" onClick={backup}>백업(JSON)</button>
              <button className="btn btn-sm btn-ghost" onClick={() => restoreRef.current.click()}>복원</button>
              <input ref={restoreRef} type="file" accept=".json" style={{ display: 'none' }} onChange={(e) => { restore(e.target.files[0]); e.target.value = ''; }} />
              <button className="btn btn-sm btn-danger" onClick={clearAll}>전체 삭제</button>
            </div>
          </div>
          <p className="note" style={{ marginBottom: 10 }}>카테고리를 바꾸면 같은 가맹점(내용)의 다른 거래에도 적용되고, 다음 가져오기부터 기억됩니다. 데이터는 이 브라우저에만 저장되므로 주기적으로 백업하세요.</p>
          <TxTable txs={txs} categories={categories} onChangeCategory={onChangeCategory} onDelete={onDelete} />
        </div>
      )}
    </>
  );
}
