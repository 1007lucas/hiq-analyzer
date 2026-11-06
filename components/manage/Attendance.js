import { useMemo, useState } from 'react';
import { useAcademy, setAttendance, ATT_STATUS, today, thisMonth, weekdayOf, DAYS } from '../../lib/academyStore';
import { Btn, Badge, PageHead, Empty, useManage, statusTone } from './ui';

function Daily() {
  const { classes, students, attendance } = useAcademy();
  const { notify } = useManage();
  const [date, setDate] = useState(today());
  const wd = weekdayOf(date);
  const todayClasses = classes.filter((c) => (c.days || []).includes(wd));
  const [classId, setClassId] = useState('');
  const effective = classId || todayClasses[0]?.id || classes[0]?.id || '';
  const cls = classes.find((c) => c.id === effective);
  const roster = students.filter((s) => s.status === '재원' && (s.classIds || []).includes(effective)).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const rec = (sid) => attendance.find((a) => a.date === date && a.classId === effective && a.studentId === sid);
  const counts = ATT_STATUS.map((st) => [st, roster.filter((s) => rec(s.id)?.status === st).length]);
  const unchecked = roster.filter((s) => !rec(s.id)).length;

  const markAll = () => { roster.forEach((s) => { if (!rec(s.id)) setAttendance(date, effective, s.id, '출석'); }); notify('미체크 학생을 모두 출석 처리했습니다.'); };

  return (
    <div className="mg-card">
      <div className="mg-toolbar">
        <input type="date" className="mg-input" style={{ width: 170 }} value={date} onChange={(e) => setDate(e.target.value)} />
        <span className="mg-muted">{wd}요일</span>
        <select className="mg-select grow" value={effective} onChange={(e) => setClassId(e.target.value)}>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}{(c.days || []).includes(wd) ? ' ✓' : ''} ({(c.days || []).join('·')} {c.time})</option>)}
        </select>
        <Btn variant="ghost" onClick={markAll} disabled={!unchecked}>미체크 전원 출석</Btn>
      </div>
      {!cls ? <Empty icon="🏫" title="반이 없습니다." desc="반 관리에서 반을 먼저 만들어주세요." /> : (
        <>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
            {counts.map(([st, n]) => <Badge key={st} tone={statusTone(st)}>{st} {n}</Badge>)}
            <Badge tone="gray">미체크 {unchecked}</Badge>
            {!(cls.days || []).includes(wd) && <Badge tone="amber">이 반은 {wd}요일 수업이 없습니다</Badge>}
          </div>
          {roster.length ? roster.map((s) => {
            const r = rec(s.id);
            return (
              <div className="mg-att-row" key={s.id}>
                <div className="mg-att-name">{s.name}</div>
                <div className="mg-att-meta">{s.school} {s.grade}</div>
                <div className="mg-att-btns">
                  {ATT_STATUS.map((st) => (
                    <button key={st} className={`mg-att-btn ${r?.status === st ? 'on-' + st : ''}`}
                      onClick={() => setAttendance(date, effective, s.id, r?.status === st ? '' : st, r?.note)}>{st}</button>
                  ))}
                </div>
                <div className="mg-att-note">
                  <input className="mg-input" placeholder="비고" value={r?.note || ''} disabled={!r}
                    onChange={(e) => setAttendance(date, effective, s.id, r.status, e.target.value)} />
                </div>
              </div>
            );
          }) : <Empty icon="🎓" title="이 반에 재원 학생이 없습니다." desc="반 관리에서 학생을 배정해주세요." />}
        </>
      )}
    </div>
  );
}

function Monthly() {
  const { classes, students, attendance } = useAcademy();
  const [month, setMonth] = useState(thisMonth());
  const [classId, setClassId] = useState('');
  const effective = classId || classes[0]?.id || '';
  const cls = classes.find((c) => c.id === effective);
  const roster = students.filter((s) => (s.classIds || []).includes(effective)).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const dates = useMemo(() => {
    if (!cls) return [];
    const [y, m] = month.split('-').map(Number);
    const n = new Date(y, m, 0).getDate();
    const out = [];
    for (let d = 1; d <= n; d++) {
      const ds = `${month}-${String(d).padStart(2, '0')}`;
      if ((cls.days || []).includes(weekdayOf(ds))) out.push(ds);
    }
    return out;
  }, [cls, month]);
  const map = useMemo(() => {
    const m = {};
    attendance.filter((a) => a.classId === effective && a.date.startsWith(month)).forEach((a) => { m[a.date + '|' + a.studentId] = a.status; });
    return m;
  }, [attendance, effective, month]);
  const mark = { 출석: 'O', 지각: '지', 결석: 'X', 조퇴: '조' };
  return (
    <div className="mg-card">
      <div className="mg-toolbar">
        <input type="month" className="mg-input" style={{ width: 160 }} value={month} onChange={(e) => setMonth(e.target.value)} />
        <select className="mg-select grow" value={effective} onChange={(e) => setClassId(e.target.value)}>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name} ({(c.days || []).join('·')})</option>)}
        </select>
        <Btn variant="soft" onClick={() => window.print()}>인쇄</Btn>
      </div>
      <div className="mg-muted" style={{ marginBottom: 8 }}>O 출석 · 지 지각 · X 결석 · 조 조퇴 · 수업 요일만 표시됩니다.</div>
      {!cls ? <Empty icon="🏫" title="반이 없습니다." /> : !roster.length ? <Empty icon="🎓" title="수강생이 없습니다." /> : (
        <div className="mg-table-wrap">
          <table className="mg-table mg-grid-table">
            <thead><tr><th>학생</th>{dates.map((d) => <th key={d} className="c">{Number(d.slice(8))}<br /><span style={{ fontWeight: 400 }}>{weekdayOf(d)}</span></th>)}<th className="c">출석</th><th className="c">지각</th><th className="c">결석</th></tr></thead>
            <tbody>
              {roster.map((s) => {
                const cnt = (st) => dates.filter((d) => map[d + '|' + s.id] === st).length;
                return (
                  <tr key={s.id}>
                    <td style={{ whiteSpace: 'nowrap' }}><b>{s.name}</b></td>
                    {dates.map((d) => { const st = map[d + '|' + s.id]; return <td key={d} className={`mark ${st ? 'mk-' + st : ''}`}>{st ? mark[st] : <span style={{ color: '#ccc' }}>·</span>}</td>; })}
                    <td className="c">{cnt('출석')}</td><td className="c">{cnt('지각')}</td><td className="c" style={{ color: 'var(--red)', fontWeight: 700 }}>{cnt('결석')}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Attendance() {
  const [tab, setTab] = useState('daily');
  return (
    <>
      <PageHead title="출결 관리" desc="날짜와 반을 선택해 출석을 체크하세요. 클릭 즉시 저장됩니다." />
      <div className="mg-tabs">
        <button className={`mg-tab ${tab === 'daily' ? 'active' : ''}`} onClick={() => setTab('daily')}>일일 출석 체크</button>
        <button className={`mg-tab ${tab === 'monthly' ? 'active' : ''}`} onClick={() => setTab('monthly')}>월간 출결표</button>
      </div>
      {tab === 'daily' ? <Daily /> : <Monthly />}
    </>
  );
}
