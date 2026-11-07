import { useEffect, useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeItem, LEAVE_TYPES, LEAVE_STATUS, today, thisYear, calcLeaveDays, leaveBalance } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, Stat, useManage, statusTone } from './ui';

function LeaveForm({ initial, onClose }) {
  const { employees, leaves, settings } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState({ employeeId: '', type: '연차', start: today(), end: today(), days: 1, reason: '', status: '대기', ...initial });
  const [manualDays, setManualDays] = useState(!!initial?.id);
  const set = (k) => (e) => {
    const n = { ...f, [k]: e.target.value };
    if (k === 'start' && (!n.end || n.end < n.start)) n.end = n.start;
    if (k === 'type' && n.type === '반차') n.end = n.start;
    if (!manualDays || k === 'type' || k === 'start' || k === 'end') n.days = calcLeaveDays(n.type, n.start, n.end);
    setF(n);
  };
  const emp = employees.find((e) => e.id === f.employeeId);
  const bal = emp ? leaveBalance(emp, leaves.filter((l) => l.id !== initial?.id), (f.start || today()).slice(0, 4), settings) : null;
  const save = () => {
    if (!f.employeeId) return notify('직원을 선택하세요.');
    if (!f.start) return notify('시작일을 입력하세요.');
    const data = { ...f, end: f.end || f.start, days: Number(f.days) || 0 };
    if (initial?.id) { updateItem('leaves', initial.id, data); notify('휴가를 수정했습니다.'); }
    else { addItem('leaves', data); notify('휴가를 등록했습니다.'); }
    onClose();
  };
  const del = () => { if (!window.confirm('이 휴가 기록을 삭제할까요?')) return; removeItem('leaves', initial.id); onClose(); };
  return (
    <Modal title={initial?.id ? '휴가 수정' : '휴가 등록'} onClose={onClose}
      footer={<>{initial?.id && <Btn variant="danger" className="left" onClick={del}>삭제</Btn>}<Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="직원" required full>
          <select className="mg-select" value={f.employeeId} onChange={set('employeeId')} autoFocus>
            <option value="">직원 선택…</option>
            {employees.filter((e) => e.status !== '퇴직' || e.id === f.employeeId).map((e) => <option key={e.id} value={e.id}>{e.name} ({e.position})</option>)}
          </select>
          {bal && ['연차', '반차'].includes(f.type) && <div className="mg-help">연차 잔여 <b>{bal.left}일</b> (부여 {bal.total} · 사용 {bal.used}) {bal.left - (Number(f.days) || 0) < 0 && <span style={{ color: 'var(--red)' }}>· 잔여 연차를 초과합니다</span>}</div>}
        </Field>
        <Field label="휴가 종류"><select className="mg-select" value={f.type} onChange={set('type')}>{LEAVE_TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="상태"><select className="mg-select" value={f.status} onChange={set('status')}>{LEAVE_STATUS.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="시작일" required><input type="date" className="mg-input" value={f.start} onChange={set('start')} /></Field>
        <Field label="종료일"><input type="date" className="mg-input" value={f.end} onChange={set('end')} disabled={f.type === '반차'} /></Field>
        <Field label="일수" help="일요일 제외 자동 계산. 직접 수정 가능"><input className="mg-input" inputMode="decimal" value={f.days} onChange={(e) => { setManualDays(true); setF({ ...f, days: e.target.value }); }} /></Field>
        <Field label="사유" full><input className="mg-input" value={f.reason} onChange={set('reason')} placeholder="개인 사정, 병원, 경조사 등" /></Field>
      </div>
    </Modal>
  );
}

export default function Leaves({ params }) {
  const { leaves, employees, settings } = useAcademy();
  const { notify } = useManage();
  const [year, setYear] = useState(thisYear());
  const [status, setStatus] = useState('전체');
  const [empId, setEmpId] = useState('');
  const [tab, setTab] = useState('list');
  const [form, setForm] = useState(null);
  useEffect(() => { if (params?.employeeId) setForm({ employeeId: params.employeeId }); }, [params]);

  const rows = useMemo(() => leaves
    .filter((l) => (l.start || '').startsWith(year))
    .filter((l) => status === '전체' || l.status === status)
    .filter((l) => !empId || l.employeeId === empId)
    .map((l) => ({ ...l, emp: employees.find((e) => e.id === l.employeeId) }))
    .sort((a, b) => (a.status === '대기' ? -1 : 0) - (b.status === '대기' ? -1 : 0) || (b.start || '').localeCompare(a.start || '')), [leaves, employees, year, status, empId]);
  const pending = leaves.filter((l) => l.status === '대기').length;
  const t = today();
  const upcoming = leaves.filter((l) => l.status === '승인' && l.start >= t && l.start <= t.slice(0, 8) + '31').length;

  const columns = [
    { key: 'emp', label: '직원', render: (l) => <><b>{l.emp?.name || '(삭제됨)'}</b> <span className="mg-muted">{l.emp?.position}</span></> },
    { key: 'type', label: '종류', render: (l) => <Badge tone="gold">{l.type}</Badge> },
    { key: 'period', label: '기간', render: (l) => l.end && l.end !== l.start ? `${l.start} ~ ${l.end}` : l.start },
    { key: 'days', label: '일수', align: 'c', render: (l) => `${l.days}일` },
    { key: 'reason', label: '사유', render: (l) => <span className="mg-muted">{l.reason}</span> },
    { key: 'status', label: '상태', align: 'c', render: (l) => <Badge tone={statusTone(l.status)}>{l.status}</Badge> },
    { key: 'act', label: '', align: 'actions', stop: true, render: (l) => l.status === '대기' ? <><Btn size="sm" onClick={() => { updateItem('leaves', l.id, { status: '승인' }); notify('승인했습니다.'); }}>승인</Btn><Btn size="sm" variant="danger" onClick={() => { updateItem('leaves', l.id, { status: '반려' }); notify('반려했습니다.'); }}>반려</Btn></> : <Btn size="sm" variant="soft" onClick={() => setForm(l)}>수정</Btn> },
  ];
  const balRows = employees.filter((e) => e.status !== '퇴직').map((e) => ({ ...e, bal: leaveBalance(e, leaves, year, settings) })).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const balColumns = [
    { key: 'name', label: '직원', render: (e) => <><b>{e.name}</b> <span className="mg-muted">{e.position}</span></> },
    { key: 'empType', label: '고용 형태', render: (e) => <Badge tone={statusTone(e.empType)}>{e.empType}</Badge> },
    { key: 'total', label: '부여', align: 'c', render: (e) => `${e.bal.total}일` },
    { key: 'used', label: '사용', align: 'c', render: (e) => `${e.bal.used}일` },
    { key: 'left', label: '잔여', align: 'c', render: (e) => <b style={{ color: e.bal.left < 0 ? 'var(--red)' : e.bal.left <= 2 ? 'var(--amber)' : 'var(--green)' }}>{e.bal.left}일</b> },
    { key: 'bar', label: '사용률', render: (e) => <div style={{ background: 'var(--graylt)', height: 8, width: 160 }}><div style={{ height: '100%', width: `${e.bal.total ? Math.min(100, (e.bal.used / e.bal.total) * 100) : 0}%`, background: 'var(--navy)' }} /></div> },
  ];

  return (
    <>
      <PageHead title="휴가 관리" desc="연차·반차·병가 등 휴가 신청을 등록하고 승인하며, 직원별 연차 잔여를 확인합니다." right={<Btn onClick={() => setForm({})}>+ 휴가 등록</Btn>} />
      <div className="mg-stats">
        <Stat label="승인 대기" value={`${pending}건`} tone={pending ? 'red' : ''} />
        <Stat label="이번 달 예정 휴가 (승인)" value={`${upcoming}건`} tone="gold" />
        <Stat label={`${year}년 연차 사용`} value={`${balRows.reduce((s, e) => s + e.bal.used, 0)}일`} sub={`부여 합계 ${balRows.reduce((s, e) => s + e.bal.total, 0)}일`} tone="green" />
      </div>
      <div className="mg-tabs">
        <button className={`mg-tab ${tab === 'list' ? 'active' : ''}`} onClick={() => setTab('list')}>휴가 내역</button>
        <button className={`mg-tab ${tab === 'balance' ? 'active' : ''}`} onClick={() => setTab('balance')}>연차 잔여 현황</button>
      </div>
      <div className="mg-card">
        <div className="mg-toolbar">
          <select className="mg-select" style={{ width: 110 }} value={year} onChange={(e) => setYear(e.target.value)}>{[-1, 0, 1].map((d) => String(Number(thisYear()) + d)).map((y) => <option key={y}>{y}</option>)}</select>
          {tab === 'list' && <>
            <select className="mg-select" style={{ width: 110 }} value={status} onChange={(e) => setStatus(e.target.value)}>{['전체', ...LEAVE_STATUS].map((s) => <option key={s}>{s}</option>)}</select>
            <select className="mg-select" style={{ width: 160 }} value={empId} onChange={(e) => setEmpId(e.target.value)}><option value="">모든 직원</option>{employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select>
          </>}
        </div>
        {tab === 'list'
          ? <Table columns={columns} rows={rows} empty={<Empty icon="🏖️" title={`${year}년 휴가 내역이 없습니다.`} action={<Btn onClick={() => setForm({})}>+ 휴가 등록</Btn>} />} />
          : <Table columns={balColumns} rows={balRows} empty={<Empty icon="👥" title="직원이 없습니다." />} />}
      </div>
      {form && <LeaveForm initial={form} onClose={() => setForm(null)} />}
    </>
  );
}
