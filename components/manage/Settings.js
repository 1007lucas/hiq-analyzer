import { useRef, useState } from 'react';
import { useAcademy, updateSettings, exportJSON, importJSON, loadSample, resetAll, STORAGE_KEY } from '../../lib/academyStore';
import { Btn, Field, PageHead, useManage } from './ui';

export default function Settings() {
  const { settings, students, classes, teachers, attendance, payments, counseling } = useAcademy();
  const { notify } = useManage();
  const [name, setName] = useState(settings.academyName || '');
  const fileRef = useRef();
  const onImport = async (file) => {
    if (!file) return;
    if (!window.confirm('현재 데이터를 백업 파일 내용으로 덮어씁니다. 계속할까요?')) { fileRef.current.value = ''; return; }
    try { await importJSON(file); notify('백업을 복원했습니다.'); } catch (e) { notify('복원 실패: ' + e.message); }
    fileRef.current.value = '';
  };
  return (
    <>
      <PageHead title="설정 · 백업" />
      <div className="mg-card">
        <div className="mg-card-title">학원 정보</div>
        <div className="mg-form">
          <Field label="학원 이름"><input className="mg-input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="mg-field"><label>&nbsp;</label><Btn onClick={() => { updateSettings({ academyName: name.trim() || 'HIQ입시학원' }); notify('저장했습니다.'); }}>저장</Btn></div>
        </div>
      </div>
      <div className="mg-card">
        <div className="mg-card-title">데이터 백업 · 복원</div>
        <p className="mg-muted" style={{ marginBottom: 12 }}>
          모든 데이터는 <b>이 브라우저</b>에만 저장됩니다. 다른 기기에서 보거나 브라우저 데이터를 지우기 전에는 반드시 백업 파일을 내려받으세요.
          <br />현재 저장량: 학생 {students.length} · 반 {classes.length} · 강사 {teachers.length} · 출결 {attendance.length} · 수납 {payments.length} · 상담 {counseling.length}
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn onClick={() => { exportJSON(); notify('백업 파일을 내려받습니다.'); }}>백업 파일 다운로드 (JSON)</Btn>
          <Btn variant="ghost" onClick={() => fileRef.current.click()}>백업 파일 복원</Btn>
          <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }} onChange={(e) => onImport(e.target.files[0])} />
        </div>
      </div>
      <div className="mg-card">
        <div className="mg-card-title">샘플 · 초기화</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn variant="soft" onClick={() => { if (window.confirm('현재 데이터를 지우고 샘플 데이터로 바꿀까요?')) { loadSample(); notify('샘플 데이터를 불러왔습니다.'); } }}>샘플 데이터 불러오기</Btn>
          <Btn variant="danger" onClick={() => { if (window.confirm('정말 모든 데이터를 삭제할까요? 되돌릴 수 없습니다.') && window.confirm('마지막 확인: 백업은 받아두셨나요?')) { resetAll(); notify('모든 데이터를 삭제했습니다.'); } }}>모든 데이터 삭제</Btn>
        </div>
        <div className="mg-help" style={{ marginTop: 10 }}>저장 키: {STORAGE_KEY}</div>
      </div>
    </>
  );
}
