import { useState } from 'react';
import { useAcademy, addItem, updateItem, removeItem, TEACHER_STATUS, today, fmtPhone } from '../../lib/academyStore';
import { Btn, Badge, Field, Modal, Table, PageHead, Empty, useManage, statusTone } from './ui';

const blank = () => ({ name: '', phone: '', subjects: '', hireDate: today(), status: '재직', memo: '' });

function TeacherForm({ initial, onClose }) {
  const { notify } = useManage();
  const [f, setF] = useState(initial ? { ...blank(), ...initial } : blank());
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = () => {
    if (!f.name.trim()) return notify('강사 이름을 입력하세요.');
    const data = { ...f, name: f.name.trim(), phone: f.phone.replace(/\D/g, '') };
    if (initial?.id) { updateItem('teachers', initial.id, data); notify('강사 정보를 수정했습니다.'); }
    else { addItem('teachers', data); notify('강사를 등록했습니다.'); }
    onClose();
  };
  const del = () => {
    if (!window.confirm(`${initial.name} 강사를 삭제할까요?`)) return;
    removeItem('teachers', initial.id); notify('강사를 삭제했습니다.'); onClose();
  };
  return (
    <Modal title={initial?.id ? '강사 정보 수정' : '강사 등록'} onClose={onClose}
      footer={<>{initial?.id && <Btn variant="danger" className="left" onClick={del}>삭제</Btn>}<Btn variant="soft" onClick={onClose}>취소</Btn><Btn onClick={save}>저장</Btn></>}>
      <div className="mg-form">
        <Field label="이름" required><input className="mg-input" value={f.name} onChange={set('name')} autoFocus /></Field>
        <Field label="상태"><select className="mg-select" value={f.status} onChange={set('status')}>{TEACHER_STATUS.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="담당 과목"><input className="mg-input" value={f.subjects} onChange={set('subjects')} placeholder="영어, 수학" /></Field>
        <Field label="연락처"><input className="mg-input" value={f.phone} onChange={set('phone')} placeholder="010-0000-0000" /></Field>
        <Field label="입사일"><input type="date" className="mg-input" value={f.hireDate} onChange={set('hireDate')} /></Field>
        <Field label="메모" full><textarea className="mg-textarea" value={f.memo} onChange={set('memo')} placeholder="급여 조건, 근무 요일 등" /></Field>
      </div>
    </Modal>
  );
}

export default function Teachers() {
  const { teachers, classes } = useAcademy();
  const [form, setForm] = useState(null);
  const rows = [...teachers].sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const columns = [
    { key: 'name', label: '이름', render: (t) => <b>{t.name}</b> },
    { key: 'subjects', label: '담당 과목', render: (t) => t.subjects || '-' },
    { key: 'phone', label: '연락처', render: (t) => fmtPhone(t.phone) || '-' },
    { key: 'classes', label: '담당 반', render: (t) => classes.filter((c) => c.teacherId === t.id).map((c) => c.name).join(', ') || <span className="mg-muted">-</span> },
    { key: 'hireDate', label: '입사일', render: (t) => t.hireDate || '-' },
    { key: 'status', label: '상태', align: 'c', render: (t) => <Badge tone={statusTone(t.status)}>{t.status}</Badge> },
  ];
  return (
    <>
      <PageHead title="강사 관리" desc={`재직 ${teachers.filter((t) => t.status === '재직').length}명`} right={<Btn onClick={() => setForm({})}>+ 강사 등록</Btn>} />
      <div className="mg-card">
        <Table columns={columns} rows={rows} onRowClick={(t) => setForm(t)}
          empty={<Empty icon="👩‍🏫" title="등록된 강사가 없습니다." action={<Btn onClick={() => setForm({})}>+ 강사 등록</Btn>} />} />
      </div>
      {form && <TeacherForm initial={form.id ? form : null} onClose={() => setForm(null)} />}
    </>
  );
}
