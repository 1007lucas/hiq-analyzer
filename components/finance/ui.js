import { won, pct, monthLabel, shiftMonth, wonShort } from '../../lib/finance/format';

export function StatTile({ label, value, tone, delta, deltaLabel, raw }) {
  let cls = 'val';
  if (tone === 'neg') cls += ' neg'; if (tone === 'pos') cls += ' pos';
  let d = null;
  if (delta !== undefined && delta !== null && Number.isFinite(delta)) {
    const up = delta > 0;
    d = <div className={`delta ${up ? 'up' : delta < 0 ? 'down' : ''}`}>{up ? '▲' : delta < 0 ? '▼' : '—'} {won(Math.abs(delta))} {deltaLabel || '전월 대비'}</div>;
  }
  return (
    <div className="stat">
      <div className="lbl">{label}</div>
      <div className={cls}>{raw !== undefined ? raw : won(value)}</div>
      {d}
    </div>
  );
}

// 이름·막대·수치가 한 줄인 미터 리스트 (한도가 있으면 한도 표시선)
export function MeterList({ rows, max, income }) {
  const m = max || Math.max(1, ...rows.map((r) => Math.max(r.value, r.limit || 0)));
  return (
    <div className="meter-list">
      {rows.map((r) => {
        const w = Math.min(100, (r.value / m) * 100);
        const ratio = r.limit ? r.value / r.limit : 0;
        const cls = `bar${income ? ' income' : ''}${r.limit && ratio > 1 ? ' over' : r.limit && ratio >= 0.8 ? ' warn' : ''}`;
        return (
          <div className="mrow" key={r.name} title={`${r.name} ${won(r.value)}`}>
            <div className="nm">{r.name}</div>
            <div className="trk">
              <div className={cls} style={{ width: `${w}%` }} />
              {r.limit ? <div className="lim" style={{ left: `${Math.min(100, (r.limit / m) * 100)}%` }} /> : null}
            </div>
            <div className="v">
              {won(r.value)}
              {r.limit ? <small>예산 {wonShort(r.limit)} · {pct(r.value, r.limit)}%</small> : r.sub ? <small>{r.sub}</small> : null}
            </div>
          </div>
        );
      })}
      {!rows.length && <div className="note">표시할 데이터가 없습니다.</div>}
    </div>
  );
}

export function MonthNav({ month, onChange }) {
  return (
    <div className="month-nav">
      <button onClick={() => onChange(shiftMonth(month, -1))} aria-label="이전 달">‹</button>
      <span className="cur">{monthLabel(month)}</span>
      <button onClick={() => onChange(shiftMonth(month, 1))} aria-label="다음 달">›</button>
    </div>
  );
}

export function Empty({ children }) {
  return <div className="note" style={{ padding: '18px 0', textAlign: 'center' }}>{children}</div>;
}

export function copy(text, setToast) {
  navigator.clipboard.writeText(text).then(() => setToast?.('복사되었습니다.')).catch(() => setToast?.('복사 실패'));
}
