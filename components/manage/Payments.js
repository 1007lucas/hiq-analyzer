import { useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeItem, thisMonth, today, fmtMoney, studentFee, paymentStatus, PAY_METHODS } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, Stat, useManage, statusTone } from './ui';

function PayForm({ initial, month, onClose }) {
  const { students, classes } = useAcademy();
  const { notify } = useManage();
  const isNew = !initial?.id;
  const [f, setF] = useState({
    studentId: initial?.studentId || '',
    month: initial?.month || month,
    amount: initial?.amount ?? '',
    paidAmount: initial?.paidAmount ?? '',
    paidDate: initial?.paidDate || today(),
    method: initial?.method || PAY_METHODS[0],
    memo: initial?.memo || '',
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const num = (v) => Number(String(v).replace(/[^\d]/g, '')) || 0;
  const pickStudent = (e) => {
    const sid = e.target.value;
    const s = students.find((x) => x.id === sid);
    setF({ ...f, studentId: sid, amount: s ? studentFee(s, classes) : f.amount });
  };
  const save = () => {
    if (!f.studentId) return notify('학생을 선택하세요.');
    const data = { ...f, amount: num(f.amount), paidAmount: num(f.paidAmount) };
    if (data.paidAmount === 0) { data.paidDate = ''; data.method = ''; }
    if (isNew) { addItem('payments', data); notify('수납 내역을 추가했습니다.'); }
    else { updateItem('payments', initial.id, data); notify('수납 내역을 저장했습니다.'); }
    onClose();
  };
  const del = () => { if (!window.confirm('이 수납 내역을 삭제할까요?')) return; removeItem('payments', initial.id); onClose(); };
  const fullPay = () => setF({ ...f, paidAmount: num(f.amount), paidDate: f.paidDate || today() });
  return (
    <Modal title={isNew ? '수납 내역 추가' : '수납 처리'} onClose={onClose}
      footer={<>{!isNew && <Btn variant="danger" className="left" onClick={del}>삭제</Btn>}<Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="학생" required full>
          <select className="mg-select" value={f.studentId} onChange={pickStudent} disabled={!isNew}>
            <option value="">학생 선택…</option>
            {students.filter((s) => s.status !== '퇴원' || s.id === f.studentId).map((s) => <option key={s.id} value={s.id}>{s.name} ({s.school} {s.grade})</option>)}
          </select>
        </Field>
        <Field label="청구 월"><input type="month" className="mg-input" value={f.month} onChange={set('month')} /></Field>
        <Field label="청구 금액 (원)"><input className="mg-input" inputMode="numeric" value={f.amount} onChange={set('amount')} /></Field>
        <Field label="납부 금액 (원)" help={<button className="mg-link-btn" onClick={fullPay}>전액 납부로 채우기</button>}><input className="mg-input" inputMode="numeric" value={f.paidAmount} onChange={set('paidAmount')} /></Field>
        <Field label="납부일"><input type="date" className="mg-input" value={f.paidDate} onChange={set('paidDate')} /></Field>
        <Field label="납부 방법"><select className="mg-select" value={f.method} onChange={set('method')}>{PAY_METHODS.map((m) => <option key={m}>{m}</option>)}</select></Field>
        <Field label="메모" full><input className="mg-input" value={f.memo} onChange={set('memo')} placeholder="할인, 분납 사유 등" /></Field>
      </div>
    </Modal>
  );
}

export default function Payments() {
  const { students, classes, payments } = useAcademy();
  const { notify } = useManage();
  const [month, setMonth] = useState(thisMonth());
  const [filter, setFilter] = useState('전체');
  const [q, setQ] = useState('');
  const [form, setForm] = useState(null);

  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return payments.filter((p) => p.month === month)
      .map((p) => ({ ...p, student: students.find((s) => s.id === p.studentId), status: paymentStatus(p) }))
      .filter((p) => filter === '전체' || p.status === filter)
      .filter((p) => !k || (p.student?.name || '').toLowerCase().includes(k))
      .sort((a, b) => (a.student?.name || '').localeCompare(b.student?.name || '', 'ko'));
  }, [payments, students, month, filter, q]);

  const all = payments.filter((p) => p.month === month);
  const billed = all.reduce((s, p) => s + (Number(p.amount) || 0), 0);
  const paid = all.reduce((s, p) => s + (Number(p.paidAmount) || 0), 0);
  const unpaidCount = all.filter((p) => paymentStatus(p) !== '완납').length;

  const generate = () => {
    const targets = students.filter((s) => s.status === '재원' && !all.some((p) => p.studentId === s.id));
    if (!targets.length) return notify('이번 달 청구가 모두 생성되어 있습니다.');
    if (!window.confirm(`${month} 청구서를 ${targets.length}명에게 생성할까요?\n(수강반 수강료 합계 기준, 이미 생성된 학생은 제외)`)) return;
    targets.forEach((s) => addItem('payments', { studentId: s.id, month, amount: studentFee(s, classes), paidAmount: 0, paidDate: '', method: '', memo: '' }));
    notify(`${targets.length}건의 청구를 생성했습니다.`);
  };

  const columns = [
    { key: 'name', label: '학생', render: (p) => <><b>{p.student?.name || '(삭제된 학생)'}</b> <span className="mg-muted">{p.student?.school} {p.student?.grade}</span></> },
    { key: 'cls', label: '수강반', render: (p) => (p.student?.classIds || []).map((cid) => classes.find((c) => c.id === cid)?.name).filter(Boolean).join(', ') || '-' },
    { key: 'amount', label: '청구액', align: 'r', render: (p) => fmtMoney(p.amount) },
    { key: 'paidAmount', label: '납부액', align: 'r', render: (p) => fmtMoney(p.paidAmount) },
    { key: 'rest', label: '미납액', align: 'r', render: (p) => { const r = (Number(p.amount) || 0) - (Number(p.paidAmount) || 0); return r > 0 ? <span style={{ color: 'var(--red)', fontWeight: 700 }}>{fmtMoney(r)}</span> : '-'; } },
    { key: 'paidDate', label: '납부일 · 방법', render: (p) => p.paidDate ? `${p.paidDate} · ${p.method}` : '-' },
    { key: 'status', label: '상태', align: 'c', render: (p) => <Badge tone={statusTone(p.status)}>{p.status}</Badge> },
    { key: 'memo', label: '메모', render: (p) => <span className="mg-muted">{p.memo}</span> },
    { key: 'act', label: '', align: 'actions', stop: true, render: (p) => <Btn size="sm" variant={p.status === '완납' ? 'soft' : 'gold'} onClick={() => setForm(p)}>{p.status === '완납' ? '수정' : '수납 처리'}</Btn> },
  ];

  return (
    <>
      <PageHead title="학원비 수납" desc="월별 청구를 생성하고 납부 내역을 기록합니다."
        right={<><Btn variant="ghost" onClick={generate}>이번 달 청구 생성</Btn><Btn onClick={() => setForm({})}>+ 수납 추가</Btn></>} />
      <div className="mg-stats">
        <Stat label={`${month} 청구 총액`} value={fmtMoney(billed)} sub={`${all.length}건`} />
        <Stat label="수납 완료" value={fmtMoney(paid)} sub={billed ? `${Math.round((paid / billed) * 100)}% 수납` : ''} tone="green" />
        <Stat label="미수금" value={fmtMoney(Math.max(billed - paid, 0))} sub={`미납·부분납 ${unpaidCount}명`} tone="red" />
      </div>
      <div className="mg-card">
        <div className="mg-toolbar">
          <input type="month" className="mg-input" style={{ width: 160 }} value={month} onChange={(e) => setMonth(e.target.value)} />
          <select className="mg-select" style={{ width: 120 }} value={filter} onChange={(e) => setFilter(e.target.value)}>{['전체', '미납', '부분납', '완납'].map((s) => <option key={s}>{s}</option>)}</select>
          <input className="mg-input grow" placeholder="학생 이름 검색" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Table columns={columns} rows={rows}
          empty={<Empty icon="💳" title={`${month} 수납 내역이 없습니다.`} desc="'이번 달 청구 생성'을 누르면 재원생 전원의 청구서가 수강료 기준으로 만들어집니다." action={<Btn onClick={generate}>이번 달 청구 생성</Btn>} />} />
      </div>
      {form && <PayForm initial={form.id ? form : null} month={month} onClose={() => setForm(null)} />}
    </>
  );
}
