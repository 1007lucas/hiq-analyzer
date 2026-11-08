import { createContext, useContext, useEffect } from 'react';

export const ManageCtx = createContext({ notify: () => {}, go: () => {} });
export const useManage = () => useContext(ManageCtx);

export function Btn({ variant = 'primary', size, className = '', ...rest }) {
  return <button type="button" className={`mg-btn ${variant} ${size === 'sm' ? 'sm' : ''} ${className}`} {...rest} />;
}

export function Badge({ tone = 'navy', children }) {
  return <span className={`mg-badge ${tone}`}>{children}</span>;
}

export function Field({ label, required, full, children, help }) {
  return (
    <div className={`mg-field ${full ? 'full' : ''}`}>
      {label && <label>{label}{required && <span className="req">*</span>}</label>}
      {children}
      {help && <div className="mg-help">{help}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="mg-modal-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className={`mg-modal ${wide ? 'wide' : ''}`}>
        <div className="mg-modal-head">
          <div className="mg-modal-title">{title}</div>
          <button className="mg-modal-x" onClick={onClose} aria-label="닫기">×</button>
        </div>
        <div className="mg-modal-body">{children}</div>
        {footer && <div className="mg-modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Empty({ icon = '📂', title, desc, action }) {
  return (
    <div className="mg-empty">
      <div className="ico">{icon}</div>
      <div className="t">{title}</div>
      {desc && <div className="d">{desc}</div>}
      {action}
    </div>
  );
}

export function Table({ columns, rows, onRowClick, empty }) {
  if (!rows.length) return empty || <Empty title="데이터가 없습니다." />;
  return (
    <div className="mg-table-wrap">
      <table className="mg-table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.align || ''} style={c.width ? { width: c.width } : undefined}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={onRowClick ? 'clickable' : ''} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={c.align || ''} onClick={c.stop ? (e) => e.stopPropagation() : undefined}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChipSelect({ options, value = [], onChange, labelOf = (o) => o, keyOf = (o) => o }) {
  const toggle = (k) => onChange(value.includes(k) ? value.filter((v) => v !== k) : [...value, k]);
  return (
    <div className="mg-checks">
      {options.map((o) => {
        const k = keyOf(o);
        return (
          <label key={k} className={`mg-chip ${value.includes(k) ? 'on' : ''}`}>
            <input type="checkbox" checked={value.includes(k)} onChange={() => toggle(k)} />
            {labelOf(o)}
          </label>
        );
      })}
    </div>
  );
}

export function PageHead({ title, desc, right }) {
  return (
    <div className="mg-page-head">
      <div>
        <div className="mg-page-title">{title}</div>
        {desc && <div className="mg-page-desc">{desc}</div>}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{right}</div>
    </div>
  );
}

export function Stat({ label, value, sub, tone = '' }) {
  return (
    <div className={`mg-stat ${tone}`}>
      <div className="mg-stat-label">{label}</div>
      <div className="mg-stat-value">{value}</div>
      {sub && <div className="mg-stat-sub">{sub}</div>}
    </div>
  );
}

export const statusTone = (s) => ({
  재직: 'green', 휴직: 'amber', 퇴직: 'gray',
  정상: 'green', 지각: 'amber', 조퇴: 'blue', 결근: 'red', 휴가: 'gold', 외근: 'navy',
  대기: 'amber', 승인: 'green', 반려: 'red',
  지급완료: 'green', 미지급: 'red',
  진행중: 'green', 만료임박: 'amber', 만료: 'gray', 해지: 'red',
  정규직: 'navy', 계약직: 'blue', 시간강사: 'gold', 프리랜서: 'amber',
}[s] || 'navy');
