import { useEffect, useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeItem, CONTRACT_TYPES, today, daysBetween, contractState } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, Stat, useManage, statusTone } from './ui';

const ORDER = { 만료임박: 0, 진행중: 1, 만료: 2, 해지: 3 };

function ContractForm({ initial, onClose }) {
  const { employees } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState({ employeeId: '', type: '근로계약', start: today(), end: '', payTerms: '', insured: true, memo: '', status: '진행중', ...initial });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const save = () => {
    if (!f.employeeId) return notify('직원을 선택하세요.');
    if (!f.start) return notify('계약 시작일을 입력하세요.');
    if (initial?.id) { updateItem('contracts', initial.id, f); notify('계약을 수정했습니다.'); }
    else { addItem('contracts', f); notify('계약을 등록했습니다.'); }
    onClose();
  };
  const del = () => { if (!window.confirm('이 계약을 삭제할까요?')) return; removeItem('contracts', initial.id); onClose(); };
  const renew = () => {
    const e = employees.find((x) => x.id === f.employeeId);
    const d = new Date((f.end || today()) + 'T00:00:00'); d.setDate(d.getDate() + 1); const ns = d.toISOString().slice(0, 10);
    const ne = new Date(ns + 'T00:00:00'); ne.setFullYear(ne.getFullYear() + 1); ne.setDate(ne.getDate() - 1);
    addItem('contracts', { ...f, id: undefined, start: ns, end: ne.toISOString().slice(0, 10), status: '진행중', memo: `${f.start}~${f.end} 계약 갱신` });
    updateItem('contracts', initial.id, { status: '만료' });
    notify(`${e?.name} 님 계약을 1년 갱신했습니다.`); onClose();
  };
  return (
    <Modal title={initial?.id ? '계약 수정' : '계약 등록'} onClose={onClose}
      footer={<>{initial?.id && <Btn variant="danger" className="left" onClick={del}>삭제</Btn>}{initial?.id && initial.end && <Btn variant="ghost" onClick={renew}>1년 갱신 계약 생성</Btn>}<Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="직원" required full>
          <select className="mg-select" value={f.employeeId} onChange={set('employeeId')} autoFocus>
            <option value="">직원 선택…</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.position} · {e.empType}{e.status !== '재직' ? ' · ' + e.status : ''})</option>)}
          </select>
        </Field>
        <Field label="계약 종류"><select className="mg-select" value={f.type} onChange={set('type')}>{CONTRACT_TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="상태"><select className="mg-select" value={f.status} onChange={set('status')}><option>진행중</option><option>만료</option><option>해지</option></select></Field>
        <Field label="시작일" required><input type="date" className="mg-input" value={f.start} onChange={set('start')} /></Field>
        <Field label="종료일" help="비워두면 기간의 정함이 없는 계약"><input type="date" className="mg-input" value={f.end} onChange={set('end')} /></Field>
        <Field label="급여 · 근무 조건" full><input className="mg-input" value={f.payTerms} onChange={set('payTerms')} placeholder="월 3,000,000원 / 주 5일 13:00~22:00 / 주휴 포함" /></Field>
        <Field label="4대보험" full><label className={`mg-chip ${f.insured ? 'on' : ''}`} style={{ width: 'fit-content' }}><input type="checkbox" checked={!!f.insured} onChange={set('insured')} />4대보험 가입 계약</label></Field>
        <Field label="메모" full><textarea className="mg-textarea" value={f.memo} onChange={set('memo')} placeholder="계약서 보관 위치, 특약 사항, 갱신 협의 내용 등" /></Field>
      </div>
    </Modal>
  );
}

export default function Contracts({ params }) {
  const { contracts, employees } = useAcademy();
  const [filter, setFilter] = useState('전체');
  const [q, setQ] = useState('');
  const [form, setForm] = useState(null);
  useEffect(() => { if (params?.employeeId) setForm({ employeeId: params.employeeId }); }, [params]);
  const t = today();
  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return contracts.map((c) => ({ ...c, emp: employees.find((e) => e.id === c.employeeId), state: contractState(c, t) }))
      .filter((c) => filter === '전체' || c.state === filter)
      .filter((c) => !k || [c.emp?.name, c.type, c.payTerms, c.memo].some((v) => String(v || '').toLowerCase().includes(k)))
      .sort((a, b) => (ORDER[a.state] - ORDER[b.state]) || (a.end || '9999').localeCompare(b.end || '9999'));
  }, [contracts, employees, filter, q, t]);
  const states = contracts.map((c) => contractState(c, t));
  const noContract = employees.filter((e) => e.status === '재직' && !contracts.some((c) => c.employeeId === e.id && contractState(c, t) !== '만료' && contractState(c, t) !== '해지'));
  const columns = [
    { key: 'emp', label: '직원', render: (c) => <><b>{c.emp?.name || '(삭제됨)'}</b> <span className="mg-muted">{c.emp?.position}</span></> },
    { key: 'type', label: '계약 종류' },
    { key: 'period', label: '계약 기간', render: (c) => <>{c.start} ~ {c.end || <span className="mg-muted">기간 없음</span>}</> },
    { key: 'left', label: '남은 기간', align: 'c', render: (c) => { if (!c.end || c.state === '만료' || c.state === '해지') return '-'; const n = daysBetween(t, c.end); return <span style={{ color: n <= 30 ? 'var(--red)' : undefined, fontWeight: n <= 30 ? 700 : 400 }}>D-{n}</span>; } },
    { key: 'payTerms', label: '급여 · 근무 조건', render: (c) => c.payTerms || '-' },
    { key: 'insured', label: '4대보험', align: 'c', render: (c) => c.insured ? '가입' : <span className="mg-muted">미가입</span> },
    { key: 'state', label: '상태', align: 'c', render: (c) => <Badge tone={statusTone(c.state)}>{c.state}</Badge> },
  ];
  return (
    <>
      <PageHead title="계약 관리" desc="근로·위촉 계약의 기간과 조건을 관리하고 만료 30일 전부터 알려드립니다." right={<Btn onClick={() => setForm({})}>+ 계약 등록</Btn>} />
      <div className="mg-stats">
        <Stat label="진행 중 계약" value={`${states.filter((s) => s === '진행중' || s === '만료임박').length}건`} />
        <Stat label="30일 내 만료" value={`${states.filter((s) => s === '만료임박').length}건`} tone={states.includes('만료임박') ? 'red' : ''} />
        <Stat label="계약 없는 재직자" value={`${noContract.length}명`} sub={noContract.map((e) => e.name).join(', ')} tone={noContract.length ? 'gold' : ''} />
      </div>
      <div className="mg-card">
        <div className="mg-toolbar">
          <input className="mg-input grow" placeholder="직원·종류·조건 검색" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="mg-select" style={{ width: 130 }} value={filter} onChange={(e) => setFilter(e.target.value)}>{['전체', '만료임박', '진행중', '만료', '해지'].map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        <Table columns={columns} rows={rows} onRowClick={(c) => setForm(c)}
          empty={<Empty icon="📝" title="등록된 계약이 없습니다." desc="근로계약서·위촉계약서의 기간과 조건을 등록하면 만료 시점을 놓치지 않습니다." action={<Btn onClick={() => setForm({})}>+ 계약 등록</Btn>} />} />
      </div>
      {form && <ContractForm initial={form} onClose={() => setForm(null)} />}
    </>
  );
}
