import { useMemo, useState } from 'react';
import { useAcademy, upsertWork, removeWork, WORK_STATUS, today, thisMonth, weekdayOf, monthDates, workHours, toMin } from '../../lib/academyStore';
import { Btn, Badge, PageHead, Empty, useManage, statusTone } from './ui';

function Daily() {
  const { employees, attendance, leaves, settings } = useAcademy();
  const { notify } = useManage();
  const [date, setDate] = useState(today());
  const staff = employees.filter((e) => e.status === '재직').sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const rec = (id) => attendance.find((a) => a.date === date && a.employeeId === id);
  const onLeave = (id) => leaves.find((l) => l.employeeId === id && l.status === '승인' && l.start <= date && (l.end || l.start) >= date);
  const now = () => { const d = new Date(); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
  const autoStatus = (r, patch) => {
    const n = { ...r, ...patch };
    if (['결근', '휴가', '외근'].includes(n.status) && !patch.status) return {};
    let status = n.status === '결근' || n.status === '휴가' || n.status === '외근' ? n.status : '정상';
    if (n.checkIn && toMin(n.checkIn) > toMin(settings.workStart)) status = '지각';
    if (n.checkOut && toMin(n.checkOut) < toMin(settings.workEnd)) status = status === '지각' ? '지각' : '조퇴';
    return { status };
  };
  const change = (id, patch) => {
    const r = rec(id) || { checkIn: '', checkOut: '', status: '정상', note: '' };
    const n = { ...r, ...patch };
    const hours = Math.round(workHours(n.checkIn, n.checkOut) * 10) / 10;
    upsertWork(date, id, { ...patch, hours, ...(patch.status ? {} : autoStatus(r, patch)) });
  };
  const counts = WORK_STATUS.map((st) => [st, staff.filter((e) => rec(e.id)?.status === st).length]);
  const unchecked = staff.filter((e) => !rec(e.id)).length;
  const applyLeaves = () => { let n = 0; staff.forEach((e) => { if (!rec(e.id) && onLeave(e.id)) { upsertWork(date, e.id, { status: '휴가', hours: 0 }); n++; } }); notify(n ? `휴가 승인자 ${n}명을 휴가로 표시했습니다.` : '이 날짜에 승인된 휴가자가 없습니다.'); };

  return (
    <div className="mg-card">
      <div className="mg-toolbar">
        <input type="date" className="mg-input" style={{ width: 170 }} value={date} onChange={(e) => setDate(e.target.value)} />
        <span className="mg-muted">{weekdayOf(date)}요일 · 기준 근무 {settings.workStart}~{settings.workEnd}</span>
        <span className="grow" />
        <Btn variant="ghost" onClick={applyLeaves}>승인된 휴가 반영</Btn>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
        {counts.map(([st, n]) => <Badge key={st} tone={statusTone(st)}>{st} {n}</Badge>)}
        <Badge tone="gray">미체크 {unchecked}</Badge>
      </div>
      {!staff.length ? <Empty icon="👥" title="재직 중인 직원이 없습니다." desc="직원 관리에서 직원을 먼저 등록해주세요." /> : staff.map((e) => {
        const r = rec(e.id);
        const lv = onLeave(e.id);
        return (
          <div className="mg-att-row" key={e.id}>
            <div className="mg-att-name">{e.name} {lv && !r && <Badge tone="gold">{lv.type} 승인</Badge>}</div>
            <div className="mg-att-meta">{e.position}{e.subject ? ` · ${e.subject}` : ''}</div>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <input type="time" className="mg-input" style={{ width: 118, padding: '4px 6px' }} value={r?.checkIn || ''} onChange={(ev) => change(e.id, { checkIn: ev.target.value })} />
              <Btn size="sm" variant="soft" onClick={() => change(e.id, { checkIn: now() })}>출근</Btn>
              <input type="time" className="mg-input" style={{ width: 118, padding: '4px 6px' }} value={r?.checkOut || ''} onChange={(ev) => change(e.id, { checkOut: ev.target.value })} />
              <Btn size="sm" variant="soft" onClick={() => change(e.id, { checkOut: now() })}>퇴근</Btn>
            </div>
            <div className="mg-att-btns">
              {WORK_STATUS.map((st) => (
                <button key={st} className={`mg-att-btn ${r?.status === st ? 'on-' + st : ''}`} onClick={() => change(e.id, { status: st })}>{st}</button>
              ))}
            </div>
            <div className="mg-att-note">
              <input className="mg-input" placeholder="비고" value={r?.note || ''} onChange={(ev) => change(e.id, { note: ev.target.value })} />
            </div>
            <div className="mg-muted" style={{ minWidth: 48, textAlign: 'right' }}>{r?.hours ? `${r.hours}h` : ''}</div>
            {r && <button className="mg-modal-x" title="기록 삭제" onClick={() => removeWork(date, e.id)}>×</button>}
          </div>
        );
      })}
    </div>
  );
}

function Monthly() {
  const { employees, attendance } = useAcademy();
  const [month, setMonth] = useState(thisMonth());
  const [view, setView] = useState('summary');
  const staff = employees.filter((e) => e.status !== '퇴직' || attendance.some((a) => a.employeeId === e.id && a.date.startsWith(month))).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const dates = useMemo(() => monthDates(month), [month]);
  const map = useMemo(() => { const m = {}; attendance.filter((a) => a.date.startsWith(month)).forEach((a) => { m[a.date + '|' + a.employeeId] = a; }); return m; }, [attendance, month]);
  const mark = { 정상: 'O', 지각: '지', 조퇴: '조', 결근: 'X', 휴가: '휴', 외근: '외' };
  const sum = (id) => {
    const rs = dates.map((d) => map[d + '|' + id]).filter(Boolean);
    const c = (st) => rs.filter((r) => r.status === st).length;
    return { days: rs.filter((r) => r.status !== '결근' && r.status !== '휴가').length, late: c('지각'), early: c('조퇴'), absent: c('결근'), leave: c('휴가'), hours: rs.reduce((s, r) => s + (Number(r.hours) || 0), 0) };
  };
  return (
    <div className="mg-card">
      <div className="mg-toolbar">
        <input type="month" className="mg-input" style={{ width: 160 }} value={month} onChange={(e) => setMonth(e.target.value)} />
        <select className="mg-select" style={{ width: 150 }} value={view} onChange={(e) => setView(e.target.value)}><option value="summary">월간 집계</option><option value="grid">일자별 표</option></select>
        <span className="grow" />
        <Btn variant="soft" onClick={() => window.print()}>인쇄</Btn>
      </div>
      {!staff.length ? <Empty icon="👥" title="직원이 없습니다." /> : view === 'summary' ? (
        <div className="mg-table-wrap">
          <table className="mg-table">
            <thead><tr><th>직원</th><th>직책</th><th className="c">근무일</th><th className="c">지각</th><th className="c">조퇴</th><th className="c">결근</th><th className="c">휴가</th><th className="r">근무시간</th></tr></thead>
            <tbody>{staff.map((e) => { const s = sum(e.id); return (
              <tr key={e.id}><td><b>{e.name}</b></td><td>{e.position}</td><td className="c">{s.days}</td><td className="c" style={{ color: s.late ? 'var(--amber)' : undefined }}>{s.late}</td><td className="c">{s.early}</td><td className="c" style={{ color: s.absent ? 'var(--red)' : undefined, fontWeight: s.absent ? 700 : 400 }}>{s.absent}</td><td className="c">{s.leave}</td><td className="r">{s.hours.toFixed(1)}h</td></tr>
            ); })}</tbody>
          </table>
        </div>
      ) : (
        <>
          <div className="mg-muted" style={{ marginBottom: 8 }}>O 정상 · 지 지각 · 조 조퇴 · X 결근 · 휴 휴가 · 외 외근</div>
          <div className="mg-table-wrap">
            <table className="mg-table mg-grid-table">
              <thead><tr><th>직원</th>{dates.map((d) => <th key={d} className="c" style={{ padding: '6px 3px', color: weekdayOf(d) === '일' ? 'var(--red)' : undefined }}>{Number(d.slice(8))}<br /><span style={{ fontWeight: 400 }}>{weekdayOf(d)}</span></th>)}</tr></thead>
              <tbody>{staff.map((e) => (
                <tr key={e.id}><td style={{ whiteSpace: 'nowrap' }}><b>{e.name}</b></td>
                  {dates.map((d) => { const r = map[d + '|' + e.id]; return <td key={d} className={`mark ${r ? 'mk-' + r.status : ''}`} title={r ? `${r.checkIn || ''}~${r.checkOut || ''} ${r.note || ''}` : ''}>{r ? mark[r.status] : <span style={{ color: '#ccc' }}>·</span>}</td>; })}
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function Work() {
  const [tab, setTab] = useState('daily');
  return (
    <>
      <PageHead title="근태 관리" desc="출근·퇴근 시간을 기록하면 지각·조퇴가 자동 판정되고 근무시간이 계산됩니다. 입력 즉시 저장됩니다." />
      <div className="mg-tabs">
        <button className={`mg-tab ${tab === 'daily' ? 'active' : ''}`} onClick={() => setTab('daily')}>일일 근태</button>
        <button className={`mg-tab ${tab === 'monthly' ? 'active' : ''}`} onClick={() => setTab('monthly')}>월간 근태 현황</button>
      </div>
      {tab === 'daily' ? <Daily /> : <Monthly />}
    </>
  );
}
