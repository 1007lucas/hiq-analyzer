import { useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeItem, thisMonth, today, fmtMoney, monthHours, calcDeductions } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, Stat, useManage, statusTone } from './ui';

const num = (v) => Number(String(v ?? '').replace(/[^\d.-]/g, '')) || 0;

export function computePay(p, emp, rates) {
  const base = p.payType === '시급제' ? num(p.hours) * num(p.hourlyRate) : num(p.baseAmount);
  const gross = base + num(p.allowance) + num(p.bonus);
  const d = calcDeductions(emp || { empType: '정규직', insured: false }, gross, rates, p.incomeTax, p.otherDeduction);
  return { base, gross, deductions: d, net: gross - d.total };
}

function PayForm({ initial, month, onClose }) {
  const { employees, attendance, settings } = useAcademy();
  const { notify } = useManage();
  const isNew = !initial?.id;
  const [f, setF] = useState({ employeeId: '', month, payType: '월급제', baseAmount: '', hours: '', hourlyRate: '', allowance: 0, bonus: 0, incomeTax: 0, otherDeduction: 0, status: '미지급', paidDate: '', memo: '', ...initial });
  const emp = employees.find((e) => e.id === f.employeeId);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const pickEmp = (e) => {
    const id = e.target.value; const em = employees.find((x) => x.id === id);
    if (!em) return setF({ ...f, employeeId: id });
    setF({ ...f, employeeId: id, payType: em.payType, baseAmount: em.baseSalary, hourlyRate: em.hourlyRate, hours: em.payType === '시급제' ? Math.round(monthHours(attendance, id, f.month) * 10) / 10 : 0 });
  };
  const calc = computePay(f, emp, settings.rates);
  const d = calc.deductions;
  const save = () => {
    if (!f.employeeId) return notify('직원을 선택하세요.');
    const data = { ...f, baseAmount: num(f.baseAmount), hours: num(f.hours), hourlyRate: num(f.hourlyRate), allowance: num(f.allowance), bonus: num(f.bonus), incomeTax: num(f.incomeTax), otherDeduction: num(f.otherDeduction), gross: calc.gross, net: calc.net, deductions: d };
    if (data.status === '지급완료' && !data.paidDate) data.paidDate = today();
    if (isNew) { addItem('payrolls', data); notify('급여 내역을 추가했습니다.'); }
    else { updateItem('payrolls', initial.id, data); notify('급여 내역을 저장했습니다.'); }
    onClose();
  };
  const del = () => { if (!window.confirm('이 급여 내역을 삭제할까요?')) return; removeItem('payrolls', initial.id); onClose(); };
  const Row = ({ k, v, strong, red }) => <li><span>{k}</span><span style={{ fontWeight: strong ? 800 : 600, color: red ? 'var(--red)' : undefined }}>{v}</span></li>;
  return (
    <Modal title={isNew ? '급여 내역 추가' : `급여 상세 · ${emp?.name || ''} (${f.month})`} onClose={onClose} wide
      footer={<>{!isNew && <Btn variant="danger" className="left" onClick={del}>삭제</Btn>}<Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-two">
        <div>
          <div className="mg-form" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <Field label="직원" required full>
              <select className="mg-select" value={f.employeeId} onChange={pickEmp} disabled={!isNew}>
                <option value="">직원 선택…</option>
                {employees.filter((e) => e.status !== '퇴직' || e.id === f.employeeId).map((e) => <option key={e.id} value={e.id}>{e.name} ({e.position} · {e.empType})</option>)}
              </select>
            </Field>
            <Field label="귀속 월"><input type="month" className="mg-input" value={f.month} onChange={set('month')} /></Field>
            <Field label="급여 형태"><select className="mg-select" value={f.payType} onChange={set('payType')}><option>월급제</option><option>시급제</option></select></Field>
            {f.payType === '시급제' ? <>
              <Field label="근무시간 (h)" help={emp ? <button className="mg-link-btn" onClick={() => setF({ ...f, hours: Math.round(monthHours(attendance, f.employeeId, f.month) * 10) / 10 })}>근태에서 불러오기</button> : ''}><input className="mg-input" inputMode="decimal" value={f.hours} onChange={set('hours')} /></Field>
              <Field label="시급 (원)"><input className="mg-input" inputMode="numeric" value={f.hourlyRate} onChange={set('hourlyRate')} /></Field>
            </> : <Field label="기본급 (원)" full><input className="mg-input" inputMode="numeric" value={f.baseAmount} onChange={set('baseAmount')} /></Field>}
            <Field label="수당 (원)" help="특강·초과근무·식대 등"><input className="mg-input" inputMode="numeric" value={f.allowance} onChange={set('allowance')} /></Field>
            <Field label="상여 (원)"><input className="mg-input" inputMode="numeric" value={f.bonus} onChange={set('bonus')} /></Field>
            {emp?.empType !== '프리랜서' && <Field label="소득세 (원)" help="간이세액표 금액 직접 입력. 지방소득세 10%는 자동"><input className="mg-input" inputMode="numeric" value={f.incomeTax} onChange={set('incomeTax')} /></Field>}
            <Field label="기타 공제 (원)" help="가불, 선지급 등"><input className="mg-input" inputMode="numeric" value={f.otherDeduction} onChange={set('otherDeduction')} /></Field>
            <Field label="지급 상태"><select className="mg-select" value={f.status} onChange={set('status')}><option>미지급</option><option>지급완료</option></select></Field>
            <Field label="지급일"><input type="date" className="mg-input" value={f.paidDate} onChange={set('paidDate')} /></Field>
            <Field label="메모" full><input className="mg-input" value={f.memo} onChange={set('memo')} /></Field>
          </div>
        </div>
        <div>
          <div className="mg-sec" style={{ marginTop: 0 }}>급여 계산 {emp && <Badge tone={statusTone(emp.empType)}>{emp.empType}{emp.empType !== '프리랜서' ? (emp.insured ? ' · 4대보험' : ' · 보험 미가입') : ' · 3.3%'}</Badge>}</div>
          <ul className="mg-list">
            {f.payType === '시급제' ? <Row k={`기본급 (${num(f.hours)}h × ${fmtMoney(f.hourlyRate)})`} v={fmtMoney(calc.base)} /> : <Row k="기본급" v={fmtMoney(calc.base)} />}
            <Row k="수당 + 상여" v={fmtMoney(num(f.allowance) + num(f.bonus))} />
            <Row k="지급 총액" v={fmtMoney(calc.gross)} strong />
            {d.pension > 0 && <Row k={`국민연금 (${settings.rates.pension}%)`} v={'-' + fmtMoney(d.pension)} red />}
            {d.health > 0 && <Row k={`건강보험 (${settings.rates.health}%)`} v={'-' + fmtMoney(d.health)} red />}
            {d.care > 0 && <Row k={`장기요양 (건강보험의 ${settings.rates.care}%)`} v={'-' + fmtMoney(d.care)} red />}
            {d.employment > 0 && <Row k={`고용보험 (${settings.rates.employment}%)`} v={'-' + fmtMoney(d.employment)} red />}
            <Row k={emp?.empType === '프리랜서' ? '사업소득세 (3%)' : '소득세'} v={'-' + fmtMoney(d.incomeTax)} red />
            <Row k="지방소득세 (10%)" v={'-' + fmtMoney(d.localTax)} red />
            {d.other > 0 && <Row k="기타 공제" v={'-' + fmtMoney(d.other)} red />}
            <Row k="공제 합계" v={'-' + fmtMoney(d.total)} strong red />
            <Row k="실지급액" v={<span style={{ fontSize: 18, color: 'var(--navy)' }}>{fmtMoney(calc.net)}</span>} strong />
          </ul>
          <div className="mg-help" style={{ marginTop: 8 }}>보험 요율은 설정 메뉴에서 변경할 수 있습니다. 실제 신고 금액은 세무 담당자 확인을 권장합니다.</div>
        </div>
      </div>
    </Modal>
  );
}

function Payslip({ p, onClose }) {
  const { employees, settings } = useAcademy();
  const emp = employees.find((e) => e.id === p.employeeId);
  const c = computePay(p, emp, settings.rates);
  const d = c.deductions;
  const R = ({ k, v }) => <tr><td>{k}</td><td className="r">{fmtMoney(v)}</td></tr>;
  return (
    <Modal title={`급여명세서 · ${p.month}`} onClose={onClose}
      footer={<><Btn variant="soft" onClick={onClose}>닫기</Btn><Btn onClick={() => window.print()}>인쇄</Btn></>}>
      <div className="mg-payslip">
        <div style={{ textAlign: 'center', marginBottom: 14 }}><div style={{ fontSize: 18, fontWeight: 800, color: 'var(--navy)' }}>{p.month.replace('-', '년 ')}월 급여명세서</div><div className="mg-muted">{settings.academyName}</div></div>
        <div className="mg-detail-grid" style={{ marginBottom: 14 }}>
          <div><div className="k">성명</div><div className="v">{emp?.name}</div></div>
          <div><div className="k">직책</div><div className="v">{emp?.position} · {emp?.empType}</div></div>
          <div><div className="k">입사일</div><div className="v">{emp?.hireDate || '-'}</div></div>
          <div><div className="k">지급일</div><div className="v">{p.paidDate || '-'}</div></div>
        </div>
        <div className="mg-two">
          <table className="mg-table"><thead><tr><th>지급 항목</th><th className="r">금액</th></tr></thead><tbody>
            <R k={p.payType === '시급제' ? `기본급 (${p.hours}h × ${fmtMoney(p.hourlyRate)})` : '기본급'} v={c.base} />
            <R k="수당" v={p.allowance} /><R k="상여" v={p.bonus} />
            <tr><td><b>지급 합계</b></td><td className="r"><b>{fmtMoney(c.gross)}</b></td></tr>
          </tbody></table>
          <table className="mg-table"><thead><tr><th>공제 항목</th><th className="r">금액</th></tr></thead><tbody>
            {emp?.empType !== '프리랜서' && <><R k="국민연금" v={d.pension} /><R k="건강보험" v={d.health} /><R k="장기요양보험" v={d.care} /><R k="고용보험" v={d.employment} /></>}
            <R k={emp?.empType === '프리랜서' ? '사업소득세' : '소득세'} v={d.incomeTax} /><R k="지방소득세" v={d.localTax} />{d.other > 0 && <R k="기타 공제" v={d.other} />}
            <tr><td><b>공제 합계</b></td><td className="r"><b>{fmtMoney(d.total)}</b></td></tr>
          </tbody></table>
        </div>
        <div style={{ marginTop: 14, padding: '12px 16px', background: 'var(--goldfaint)', borderLeft: '4px solid var(--gold)', display: 'flex', justifyContent: 'space-between', fontSize: 16 }}><b>실지급액</b><b style={{ color: 'var(--navy)' }}>{fmtMoney(c.net)}</b></div>
        {p.memo && <div className="mg-muted" style={{ marginTop: 8 }}>비고: {p.memo}</div>}
      </div>
    </Modal>
  );
}

export default function Payroll() {
  const { employees, payrolls, attendance, settings } = useAcademy();
  const { notify } = useManage();
  const [month, setMonth] = useState(thisMonth());
  const [filter, setFilter] = useState('전체');
  const [form, setForm] = useState(null);
  const [slip, setSlip] = useState(null);

  const rows = useMemo(() => payrolls.filter((p) => p.month === month)
    .map((p) => { const emp = employees.find((e) => e.id === p.employeeId); return { ...p, emp, calc: computePay(p, emp, settings.rates) }; })
    .filter((p) => filter === '전체' || p.status === filter)
    .sort((a, b) => (a.emp?.name || '').localeCompare(b.emp?.name || '', 'ko')), [payrolls, employees, month, filter, settings]);
  const all = payrolls.filter((p) => p.month === month).map((p) => computePay(p, employees.find((e) => e.id === p.employeeId), settings.rates));
  const grossSum = all.reduce((s, c) => s + c.gross, 0);
  const netSum = all.reduce((s, c) => s + c.net, 0);
  const unpaid = payrolls.filter((p) => p.month === month && p.status !== '지급완료');

  const generate = () => {
    const targets = employees.filter((e) => e.status === '재직' && !payrolls.some((p) => p.month === month && p.employeeId === e.id));
    if (!targets.length) return notify('이번 달 급여가 모두 생성되어 있습니다.');
    if (!window.confirm(`${month} 급여 내역을 재직자 ${targets.length}명에게 생성할까요?\n(월급제: 기본급 / 시급제: 이달 근태 시간 × 시급)`)) return;
    targets.forEach((e) => {
      const base = { employeeId: e.id, month, payType: e.payType, baseAmount: e.baseSalary || 0, hourlyRate: e.hourlyRate || 0, hours: e.payType === '시급제' ? Math.round(monthHours(attendance, e.id, month) * 10) / 10 : 0, allowance: 0, bonus: 0, incomeTax: 0, otherDeduction: 0, status: '미지급', paidDate: '', memo: '' };
      const c = computePay(base, e, settings.rates);
      addItem('payrolls', { ...base, gross: c.gross, net: c.net, deductions: c.deductions });
    });
    notify(`${targets.length}건의 급여 내역을 생성했습니다.`);
  };
  const markPaid = (p) => { updateItem('payrolls', p.id, { status: '지급완료', paidDate: p.paidDate || today() }); notify('지급 완료로 표시했습니다.'); };

  const columns = [
    { key: 'emp', label: '직원', render: (p) => <><b>{p.emp?.name || '(삭제됨)'}</b> <span className="mg-muted">{p.emp?.position}</span></> },
    { key: 'type', label: '형태', render: (p) => p.emp ? <Badge tone={statusTone(p.emp.empType)}>{p.emp.empType}</Badge> : '-' },
    { key: 'base', label: '기본급', align: 'r', render: (p) => p.payType === '시급제' ? <>{fmtMoney(p.calc.base)}<div className="mg-muted" style={{ fontSize: 11 }}>{p.hours}h × {fmtMoney(p.hourlyRate)}</div></> : fmtMoney(p.calc.base) },
    { key: 'extra', label: '수당·상여', align: 'r', render: (p) => fmtMoney(num(p.allowance) + num(p.bonus)) },
    { key: 'gross', label: '지급 총액', align: 'r', render: (p) => fmtMoney(p.calc.gross) },
    { key: 'ded', label: '공제', align: 'r', render: (p) => <span style={{ color: 'var(--red)' }}>-{fmtMoney(p.calc.deductions.total)}</span> },
    { key: 'net', label: '실지급액', align: 'r', render: (p) => <b>{fmtMoney(p.calc.net)}</b> },
    { key: 'status', label: '상태', align: 'c', render: (p) => <><Badge tone={statusTone(p.status)}>{p.status}</Badge>{p.paidDate && <div className="mg-muted" style={{ fontSize: 11 }}>{p.paidDate}</div>}</> },
    { key: 'act', label: '', align: 'actions', stop: true, render: (p) => <>{p.status !== '지급완료' && <Btn size="sm" variant="gold" onClick={() => markPaid(p)}>지급 완료</Btn>}<Btn size="sm" variant="soft" onClick={() => setForm(p)}>상세</Btn><Btn size="sm" variant="soft" onClick={() => setSlip(p)}>명세서</Btn></> },
  ];
  return (
    <>
      <PageHead title="급여 관리" desc="월별 급여를 생성하고 4대보험·세금을 자동 계산해 급여명세서를 만듭니다."
        right={<><Btn variant="ghost" onClick={generate}>이번 달 급여 생성</Btn><Btn onClick={() => setForm({ month })}>+ 급여 추가</Btn></>} />
      <div className="mg-stats">
        <Stat label={`${month} 지급 총액`} value={fmtMoney(grossSum)} sub={`${all.length}명`} />
        <Stat label="실지급 합계" value={fmtMoney(netSum)} sub={`공제 ${fmtMoney(grossSum - netSum)}`} tone="green" />
        <Stat label="미지급" value={`${unpaid.length}명`} sub={fmtMoney(unpaid.reduce((s, p) => s + computePay(p, employees.find((e) => e.id === p.employeeId), settings.rates).net, 0))} tone={unpaid.length ? 'red' : ''} />
      </div>
      <div className="mg-card">
        <div className="mg-toolbar">
          <input type="month" className="mg-input" style={{ width: 160 }} value={month} onChange={(e) => setMonth(e.target.value)} />
          <select className="mg-select" style={{ width: 120 }} value={filter} onChange={(e) => setFilter(e.target.value)}>{['전체', '미지급', '지급완료'].map((s) => <option key={s}>{s}</option>)}</select>
          <span className="grow" />
          <Btn variant="soft" onClick={() => window.print()}>급여대장 인쇄</Btn>
        </div>
        <Table columns={columns} rows={rows}
          empty={<Empty icon="💰" title={`${month} 급여 내역이 없습니다.`} desc="'이번 달 급여 생성'을 누르면 재직자 전원의 급여가 기본급(또는 근태 시간 × 시급) 기준으로 만들어집니다." action={<Btn onClick={generate}>이번 달 급여 생성</Btn>} />} />
      </div>
      {form && <PayForm initial={form.id ? form : form} month={month} onClose={() => setForm(null)} />}
      {slip && <Payslip p={slip} onClose={() => setSlip(null)} />}
    </>
  );
}
