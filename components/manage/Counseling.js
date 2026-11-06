import { useEffect, useMemo, useState } from 'react';
import { useAcademy, addItem, updateItem, removeItem, COUNSEL_TYPES, today } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, useManage } from './ui';

function CounselForm({ initial, onClose }) {
  const { students } = useAcademy();
  const { notify } = useManage();
  const [f, setF] = useState({ studentId: '', date: today(), type: COUNSEL_TYPES[0], content: '', followUp: '', ...initial });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = () => {
    if (!f.studentId) return notify('학생을 선택하세요.');
    if (!f.content.trim()) return notify('상담 내용을 입력하세요.');
    if (initial?.id) { updateItem('counseling', initial.id, f); notify('상담 기록을 수정했습니다.'); }
    else { addItem('counseling', f); notify('상담 기록을 추가했습니다.'); }
    onClose();
  };
  const del = () => { if (!window.confirm('이 상담 기록을 삭제할까요?')) return; removeItem('counseling', initial.id); onClose(); };
  return (
    <Modal title={initial?.id ? '상담 기록 수정' : '상담 기록 추가'} onClose={onClose}
      footer={<>{initial?.id && <Btn variant="danger" className="left" onClick={del}>삭제</Btn>}<Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="학생" required full>
          <select className="mg-select" value={f.studentId} onChange={set('studentId')} autoFocus>
            <option value="">학생 선택…</option>
            {students.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.school} {s.grade}{s.status !== '재원' ? ' · ' + s.status : ''})</option>)}
          </select>
        </Field>
        <Field label="상담일"><input type="date" className="mg-input" value={f.date} onChange={set('date')} /></Field>
        <Field label="상담 유형"><select className="mg-select" value={f.type} onChange={set('type')}>{COUNSEL_TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="상담 내용" required full><textarea className="mg-textarea" style={{ minHeight: 140 }} value={f.content} onChange={set('content')} placeholder="상담 내용, 학부모 요청사항, 조치 계획 등" /></Field>
        <Field label="후속 상담 예정일" help="비워두면 예정 없음"><input type="date" className="mg-input" value={f.followUp} onChange={set('followUp')} /></Field>
      </div>
    </Modal>
  );
}

export default function Counseling({ params }) {
  const { counseling, students } = useAcademy();
  const [q, setQ] = useState('');
  const [type, setType] = useState('전체');
  const [form, setForm] = useState(null);
  useEffect(() => { if (params?.studentId) setForm({ studentId: params.studentId }); }, [params]);

  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return counseling
      .map((c) => ({ ...c, student: students.find((s) => s.id === c.studentId) }))
      .filter((c) => type === '전체' || c.type === type)
      .filter((c) => !k || [c.student?.name, c.content].some((v) => String(v || '').toLowerCase().includes(k)))
      .sort((a, b) => b.date.localeCompare(a.date) || (b.createdAt || '').localeCompare(a.createdAt || ''));
  }, [counseling, students, q, type]);

  const t = today();
  const columns = [
    { key: 'date', label: '상담일', width: 110 },
    { key: 'name', label: '학생', render: (c) => <><b>{c.student?.name || '(삭제된 학생)'}</b> <span className="mg-muted">{c.student?.grade}</span></> },
    { key: 'type', label: '유형', render: (c) => <Badge tone="gold">{c.type}</Badge> },
    { key: 'content', label: '내용', render: (c) => <span style={{ whiteSpace: 'pre-wrap' }}>{c.content}</span> },
    { key: 'followUp', label: '후속 예정', render: (c) => c.followUp ? <Badge tone={c.followUp < t ? 'red' : c.followUp === t ? 'amber' : 'blue'}>{c.followUp}</Badge> : <span className="mg-muted">-</span> },
  ];
  return (
    <>
      <PageHead title="상담 기록" desc={`총 ${counseling.length}건`} right={<Btn onClick={() => setForm({})}>+ 상담 기록</Btn>} />
      <div className="mg-card">
        <div className="mg-toolbar">
          <input className="mg-input grow" placeholder="학생 이름·내용 검색" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="mg-select" style={{ width: 150 }} value={type} onChange={(e) => setType(e.target.value)}>{['전체', ...COUNSEL_TYPES].map((x) => <option key={x}>{x}</option>)}</select>
        </div>
        <Table columns={columns} rows={rows} onRowClick={(c) => setForm(c)}
          empty={<Empty icon="💬" title="상담 기록이 없습니다." desc="학부모·학생 상담 내용을 기록하고 후속 상담 일정을 관리하세요." action={<Btn onClick={() => setForm({})}>+ 상담 기록</Btn>} />} />
      </div>
      {form && <CounselForm initial={form} onClose={() => setForm(null)} />}
    </>
  );
}
