import { useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeEmployeeCascade, POSITIONS, EMP_TYPES, EMP_STATUS, PAY_TYPES, today, thisYear, thisMonth, fmtPhone, fmtMoney, yearsOfService, leaveBalance, monthHours, contractState } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, useManage, statusTone } from './ui';

const blank = (settings) => ({ name: '', position: '강사', empType: '정규직', subject: '', phone: '', email: '', birth: '', hireDate: today(), leaveDate: '', status: '재직', payType: '월급제', baseSalary: '', hourlyRate: '', insured: true, annualLeave: settings.defaultAnnualLeave, bank: '', account: '', address: '', memo: '' });

export function EmployeeForm({ initial, onClose }) {
  const { settings } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState({ ...blank(settings), ...(initial || {}) });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const num = (v) => Number(String(v).replace(/[^\d.]/g, '')) || 0;
  const save = () => {
    if (!f.name.trim()) return notify('이름을 입력하세요.');
    const data = { ...f, name: f.name.trim(), phone: f.phone.replace(/\D/g, ''), baseSalary: num(f.baseSalary), hourlyRate: num(f.hourlyRate), annualLeave: num(f.annualLeave), insured: f.empType === '프리랜서' ? false : !!f.insured };
    if (data.status === '퇴직' && !data.leaveDate) data.leaveDate = today();
    if (initial?.id) { updateItem('employees', initial.id, data); notify('직원 정보를 수정했습니다.'); }
    else { addItem('employees', data); notify('직원을 등록했습니다.'); }
    onClose();
  };
  return (
    <Modal title={initial?.id ? '직원 정보 수정' : '직원 등록'} onClose={onClose} wide
      footer={<><Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-sec" style={{ marginTop: 0 }}>기본 정보</div>
      <div className="mg-form">
        <Field label="이름" required><input className="mg-input" value={f.name} onChange={set('name')} autoFocus /></Field>
        <Field label="재직 상태"><select className="mg-select" value={f.status} onChange={set('status')}>{EMP_STATUS.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="직책"><select className="mg-select" value={f.position} onChange={set('position')}>{POSITIONS.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="고용 형태"><select className="mg-select" value={f.empType} onChange={set('empType')}>{EMP_TYPES.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="담당 과목 · 업무"><input className="mg-input" value={f.subject} onChange={set('subject')} placeholder="영어 / 상담 / 행정" /></Field>
        <Field label="생년월일"><input type="date" className="mg-input" value={f.birth} onChange={set('birth')} /></Field>
        <Field label="연락처"><input className="mg-input" value={f.phone} onChange={set('phone')} placeholder="010-0000-0000" /></Field>
        <Field label="이메일"><input className="mg-input" value={f.email} onChange={set('email')} /></Field>
        <Field label="입사일"><input type="date" className="mg-input" value={f.hireDate} onChange={set('hireDate')} /></Field>
        <Field label="퇴사일"><input type="date" className="mg-input" value={f.leaveDate} onChange={set('leaveDate')} /></Field>
        <Field label="주소" full><input className="mg-input" value={f.address} onChange={set('address')} /></Field>
      </div>
      <div className="mg-sec">급여 · 보험</div>
      <div className="mg-form">
        <Field label="급여 형태"><select className="mg-select" value={f.payType} onChange={set('payType')}>{PAY_TYPES.map((s) => <option key={s}>{s}</option>)}</select></Field>
        {f.payType === '월급제'
          ? <Field label="기본급 (월, 원)"><input className="mg-input" inputMode="numeric" value={f.baseSalary} onChange={set('baseSalary')} placeholder="3000000" /></Field>
          : <Field label="시급 (원)"><input className="mg-input" inputMode="numeric" value={f.hourlyRate} onChange={set('hourlyRate')} placeholder="40000" /></Field>}
        <Field label="4대보험" help={f.empType === '프리랜서' ? '프리랜서는 사업소득 3.3% 원천징수로 처리됩니다.' : '체크하면 급여 계산 시 국민연금·건강·장기요양·고용보험을 자동 공제합니다.'}>
          <label className={`mg-chip ${f.insured && f.empType !== '프리랜서' ? 'on' : ''}`} style={{ width: 'fit-content' }}>
            <input type="checkbox" checked={!!f.insured && f.empType !== '프리랜서'} disabled={f.empType === '프리랜서'} onChange={set('insured')} />4대보험 가입
          </label>
        </Field>
        <Field label="연차 부여 일수 (연)"><input className="mg-input" inputMode="numeric" value={f.annualLeave} onChange={set('annualLeave')} /></Field>
        <Field label="은행"><input className="mg-input" value={f.bank} onChange={set('bank')} placeholder="국민" /></Field>
        <Field label="계좌번호"><input className="mg-input" value={f.account} onChange={set('account')} /></Field>
        <Field label="메모" full><textarea className="mg-textarea" value={f.memo} onChange={set('memo')} placeholder="담당 반, 근무 요일, 특이사항 등" /></Field>
      </div>
    </Modal>
  );
}

export function EmployeeDetail({ id, onClose, onEdit }) {
  const { employees, attendance, leaves, payrolls, contracts, settings } = useAcademy();
  const { notify, go } = useManage();
  const e = employees.find((x) => x.id === id);
  if (!e) return null;
  const y = thisYear(), m = thisMonth();
  const bal = leaveBalance(e, leaves, y, settings);
  const att = attendance.filter((a) => a.employeeId === id && a.date.startsWith(m));
  const cnt = (st) => att.filter((a) => a.status === st).length;
  const myContracts = contracts.filter((c) => c.employeeId === id).sort((a, b) => (b.start || '').localeCompare(a.start || ''));
  const myPays = payrolls.filter((p) => p.employeeId === id).sort((a, b) => b.month.localeCompare(a.month)).slice(0, 6);
  const myLeaves = leaves.filter((l) => l.employeeId === id).sort((a, b) => (b.start || '').localeCompare(a.start || '')).slice(0, 5);
  const del = () => {
    if (!window.confirm(`${e.name} 님을 삭제할까요?\n근태·휴가·급여·계약 기록도 함께 삭제됩니다. (퇴직 처리는 '수정'에서 상태를 바꾸세요)`)) return;
    removeEmployeeCascade(id); notify('직원을 삭제했습니다.'); onClose();
  };
  return (
    <Modal title={<>{e.name} <span className="mg-muted" style={{ fontWeight: 400, fontSize: 13 }}>{e.position}</span> <Badge tone={statusTone(e.status)}>{e.status}</Badge> <Badge tone={statusTone(e.empType)}>{e.empType}</Badge></>} onClose={onClose} wide
      footer={<><Btn variant="danger" className="left" onClick={del}>삭제</Btn><Btn variant="soft" onClick={onClose}>닫기</Btn><Btn onClick={() => onEdit(e)}>수정</Btn></>}>
      <div className="mg-detail-grid">
        <div><div className="k">담당</div><div className="v">{e.subject || '-'}</div></div>
        <div><div className="k">연락처</div><div className="v">{fmtPhone(e.phone) || '-'}</div></div>
        <div><div className="k">이메일</div><div className="v">{e.email || '-'}</div></div>
        <div><div className="k">입사일 · 근속</div><div className="v">{e.hireDate || '-'} {e.hireDate && <span className="mg-muted">({yearsOfService(e.hireDate, e.leaveDate || undefined)})</span>}</div></div>
        {e.leaveDate && <div><div className="k">퇴사일</div><div className="v">{e.leaveDate}</div></div>}
        <div><div className="k">급여</div><div className="v">{e.payType === '시급제' ? `시급 ${fmtMoney(e.hourlyRate)}` : `월 ${fmtMoney(e.baseSalary)}`}</div></div>
        <div><div className="k">4대보험</div><div className="v">{e.empType === '프리랜서' ? '해당 없음 (3.3%)' : e.insured ? '가입' : '미가입'}</div></div>
        <div><div className="k">계좌</div><div className="v">{e.bank ? `${e.bank} ${e.account}` : '-'}</div></div>
        <div><div className="k">생년월일</div><div className="v">{e.birth || '-'}</div></div>
      </div>
      {e.memo && <div className="mg-note-box" style={{ marginTop: 14 }}>{e.memo}</div>}
      <div className="mg-two">
        <div>
          <div className="mg-sec">{y}년 연차 <button className="mg-link-btn" style={{ fontSize: 12, marginLeft: 8 }} onClick={() => { onClose(); go('leaves', { employeeId: id }); }}>휴가 등록 →</button></div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            <Badge tone="navy">부여 {bal.total}일</Badge><Badge tone="amber">사용 {bal.used}일</Badge><Badge tone={bal.left < 0 ? 'red' : 'green'}>잔여 {bal.left}일</Badge>
          </div>
          {myLeaves.length ? <ul className="mg-list">{myLeaves.map((l) => <li key={l.id}><span>{l.start}{l.end && l.end !== l.start ? `~${l.end}` : ''} <Badge tone="gold">{l.type}</Badge> {l.days}일</span><Badge tone={statusTone(l.status)}>{l.status}</Badge></li>)}</ul> : <div className="mg-muted">휴가 기록이 없습니다.</div>}
        </div>
        <div>
          <div className="mg-sec">{m} 근태</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['정상', '지각', '조퇴', '결근', '휴가', '외근'].map((st) => <Badge key={st} tone={statusTone(st)}>{st} {cnt(st)}</Badge>)}
          </div>
          <div className="mg-muted" style={{ marginTop: 8 }}>근무일 {att.length}일 · 근무시간 {monthHours(attendance, id, m).toFixed(1)}h</div>
        </div>
      </div>
      <div className="mg-two">
        <div>
          <div className="mg-sec">계약 <button className="mg-link-btn" style={{ fontSize: 12, marginLeft: 8 }} onClick={() => { onClose(); go('contracts', { employeeId: id }); }}>계약 추가 →</button></div>
          {myContracts.length ? <ul className="mg-list">{myContracts.map((c) => { const st = contractState(c); return <li key={c.id}><span><b>{c.type}</b> <span className="mg-muted">{c.start}{c.end ? ` ~ ${c.end}` : ' ~ (기간 없음)'}</span></span><Badge tone={statusTone(st)}>{st}</Badge></li>; })}</ul> : <div className="mg-muted">등록된 계약이 없습니다.</div>}
        </div>
        <div>
          <div className="mg-sec">최근 급여</div>
          {myPays.length ? <ul className="mg-list">{myPays.map((p) => <li key={p.id}><span>{p.month} <Badge tone={statusTone(p.status)}>{p.status}</Badge></span><span>{fmtMoney(p.net)}</span></li>)}</ul> : <div className="mg-muted">급여 기록이 없습니다.</div>}
        </div>
      </div>
    </Modal>
  );
}

export default function Employees() {
  const { employees } = useAcademy();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('재직');
  const [type, setType] = useState('');
  const [form, setForm] = useState(null);
  const [detail, setDetail] = useState(null);
  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return employees
      .filter((e) => (status === '전체' ? true : e.status === status))
      .filter((e) => (type ? e.empType === type : true))
      .filter((e) => !k || [e.name, e.position, e.subject, e.phone, e.email, e.memo].some((v) => String(v || '').toLowerCase().includes(k)))
      .sort((a, b) => POSITIONS.indexOf(a.position) - POSITIONS.indexOf(b.position) || a.name.localeCompare(b.name, 'ko'));
  }, [employees, q, status, type]);
  const columns = [
    { key: 'name', label: '이름', render: (e) => <b>{e.name}</b> },
    { key: 'position', label: '직책' },
    { key: 'empType', label: '고용 형태', render: (e) => <Badge tone={statusTone(e.empType)}>{e.empType}</Badge> },
    { key: 'subject', label: '담당', render: (e) => e.subject || '-' },
    { key: 'phone', label: '연락처', render: (e) => fmtPhone(e.phone) || '-' },
    { key: 'hireDate', label: '입사일 · 근속', render: (e) => <>{e.hireDate || '-'} <span className="mg-muted">{yearsOfService(e.hireDate, e.leaveDate || undefined)}</span></> },
    { key: 'pay', label: '급여', align: 'r', render: (e) => e.payType === '시급제' ? `시급 ${fmtMoney(e.hourlyRate)}` : fmtMoney(e.baseSalary) },
    { key: 'insured', label: '4대보험', align: 'c', render: (e) => e.empType === '프리랜서' ? <span className="mg-muted">3.3%</span> : e.insured ? '가입' : <span className="mg-muted">미가입</span> },
    { key: 'status', label: '상태', align: 'c', render: (e) => <Badge tone={statusTone(e.status)}>{e.status}</Badge> },
  ];
  return (
    <>
      <PageHead title="직원 관리" desc={`전체 ${employees.length}명 · 재직 ${employees.filter((e) => e.status === '재직').length}명`} right={<Btn onClick={() => setForm({})}>+ 직원 등록</Btn>} />
      <div className="mg-card">
        <div className="mg-toolbar">
          <input className="mg-input grow" placeholder="이름·직책·담당·연락처 검색" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="mg-select" style={{ width: 120 }} value={status} onChange={(e) => setStatus(e.target.value)}>{['전체', ...EMP_STATUS].map((s) => <option key={s}>{s}</option>)}</select>
          <select className="mg-select" style={{ width: 140 }} value={type} onChange={(e) => setType(e.target.value)}><option value="">모든 고용 형태</option>{EMP_TYPES.map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        <Table columns={columns} rows={rows} onRowClick={(e) => setDetail(e.id)}
          empty={<Empty icon="👥" title={employees.length ? '조건에 맞는 직원이 없습니다.' : '등록된 직원이 없습니다.'} desc="직원을 등록하면 근태·휴가·급여·계약을 함께 관리할 수 있습니다." action={<Btn onClick={() => setForm({})}>+ 직원 등록</Btn>} />} />
        <div className="mg-muted" style={{ marginTop: 8 }}>행을 클릭하면 상세 정보(연차·근태·계약·급여 요약)를 볼 수 있습니다.</div>
      </div>
      {form && <EmployeeForm initial={form.id ? form : null} onClose={() => setForm(null)} />}
      {detail && !form && <EmployeeDetail id={detail} onClose={() => setDetail(null)} onEdit={(e) => setForm(e)} />}
    </>
  );
}
