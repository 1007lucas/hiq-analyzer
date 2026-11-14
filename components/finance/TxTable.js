import { useMemo, useState } from 'react';
import { won } from '../../lib/finance/format';

const HOW = { memory: ['기억', 'gray'], rule: ['규칙', 'gray'], ai: ['AI', ''], default: ['기본', 'amber'], manual: ['수동', 'green'] };

export default function TxTable({ txs, categories, onChangeCategory, onDelete, pageSize = 50, emptyText }) {
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('');
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return txs
      .filter((t) => (!qq || t.desc.toLowerCase().includes(qq)) && (!cat || t.category === cat))
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [txs, q, cat]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const cur = Math.min(page, pages - 1);
  const slice = filtered.slice(cur * pageSize, (cur + 1) * pageSize);
  const sum = filtered.reduce((a, t) => a + t.amount, 0);

  return (
    <div>
      <div className="btn-row" style={{ marginBottom: 10 }}>
        <input type="text" placeholder="내용 검색" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} style={{ minWidth: 180 }} />
        <select value={cat} onChange={(e) => { setCat(e.target.value); setPage(0); }}>
          <option value="">전체 카테고리</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="note">{filtered.length}건 · 합계 {won(sum, { plus: true })}</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="tbl">
          <thead><tr><th>날짜</th><th>내용</th><th className="num">금액</th><th>카테고리</th><th>근거</th><th></th></tr></thead>
          <tbody>
            {slice.map((t) => {
              const [hl, hc] = HOW[t.how] || ['', 'gray'];
              return (
                <tr key={t.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>{t.date}</td>
                  <td>{t.desc}</td>
                  <td className={`num ${t.amount < 0 ? 'neg' : 'pos'}`}>{won(t.amount, { plus: true })}</td>
                  <td>
                    <select value={t.category || ''} onChange={(e) => onChangeCategory(t, e.target.value)}>
                      {!t.category && <option value="">미분류</option>}
                      {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </td>
                  <td>{hl && <span className={`chip ${hc}`}>{hl}</span>}</td>
                  <td>{onDelete && <button className="btn btn-sm btn-ghost" onClick={() => onDelete(t)} title="삭제">✕</button>}</td>
                </tr>
              );
            })}
            {!slice.length && <tr><td colSpan={6} className="note" style={{ textAlign: 'center', padding: 20 }}>{emptyText || '거래가 없습니다.'}</td></tr>}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="btn-row" style={{ marginTop: 10, justifyContent: 'center' }}>
          <button className="btn btn-sm btn-ghost" disabled={cur === 0} onClick={() => setPage(cur - 1)}>이전</button>
          <span className="note">{cur + 1} / {pages}</span>
          <button className="btn btn-sm btn-ghost" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}>다음</button>
        </div>
      )}
    </div>
  );
}
