import { won, pct, monthLabel, shiftMonth, wonShort } from '../../lib/finance/format';

// goodWhenUp: 수입·순이익처럼 증가가 긍정인 지표는 true
export function StatTile({ label, value, tone, delta, deltaLabel, raw, goodWhenUp = false }) {
  let cls = 'val';
  if (tone === 'neg') cls += ' neg'; if (tone === 'pos') cls += ' pos';
  let d = null;
  if (delta !== undefined && delta !== null && Number.isFinite(delta)) {
    const up = delta > 0, down = delta < 0;
    const good = (up && goodWhenUp) || (down && !goodWhenUp);
    const mood = !up && !down ? '' : good ? ' good' : ' bad';
    d = <div className={`delta${mood}`}>{up ? '↑' : down ? '↓' : '—'} {won(Math.abs(delta))} <span style={{ fontWeight: 500, opacity: .8 }}>{deltaLabel || '전월 대비'}</span></div>;
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

const ICONS = {
  inbox: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16v12l-3 4H7l-3-4z" /><path d="M4 14h5l1 2h4l1-2h5" /></svg>,
  users: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><circle cx="17" cy="9" r="2.5" /><path d="M16 15.5a5 5 0 0 1 5.5 4.5" /></svg>,
  calendar: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>,
  target: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /></svg>,
  repeat: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 2l4 4-4 4" /><path d="M3 11V9a4 4 0 0 1 4-4h14" /><path d="M7 22l-4-4 4-4" /><path d="M21 13v2a4 4 0 0 1-4 4H3" /></svg>,
};

export function Empty({ children, icon = 'inbox', action, onAction }) {
  return (
    <div className="empty">
      <div className="ic">{ICONS[icon] || ICONS.inbox}</div>
      <p>{children}</p>
      {action && <button className="btn btn-primary btn-sm" onClick={onAction} style={{ marginTop: 4 }}>{action}</button>}
    </div>
  );
}

export function copy(text, setToast) {
  navigator.clipboard.writeText(text).then(() => setToast?.('복사되었습니다.')).catch(() => setToast?.('복사 실패'));
}
