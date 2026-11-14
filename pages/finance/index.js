import Link from 'next/link';
import FinanceLayout from '../../components/finance/Layout';

export default function FinanceHub() {
  return (
    <FinanceLayout title="홈">
      <div style={{ marginBottom: 6 }}>
        <h1 style={{ fontSize: 22, color: 'var(--navy)', fontWeight: 800 }}>어느 비서를 부를까요?</h1>
        <p className="note">은행·카드 거래내역 파일을 올리면 AI가 분류하고, 각 비서가 할 일을 정리해 드립니다. 데이터는 브라우저에만 저장됩니다.</p>
      </div>
      <div className="hub">
        <Link href="/finance/academy">
          <div className="h-ic">🏫</div>
          <h2>학원 전담 재무 비서</h2>
          <p className="note">학원 사업용 계좌·카드 내역으로</p>
          <ul>
            <li>수강료 수납·미납 관리 (입금 자동 대조, 안내 문자)</li>
            <li>월 손익 분석 + AI 코멘트</li>
            <li>강사 급여 계산 (3.3% / 4대보험)</li>
            <li>세금·신고 일정 알림 (원천세·사업장현황·종소세)</li>
          </ul>
        </Link>
        <Link href="/finance/personal">
          <div className="h-ic">👤</div>
          <h2>개인 전담 재무 비서</h2>
          <p className="note">개인 계좌·카드 내역으로</p>
          <ul>
            <li>지출 분류·월 리포트 + AI 절약 제안</li>
            <li>카테고리별 예산 설정·초과 경고</li>
            <li>저축·목표 추적</li>
            <li>고정지출·구독 자동 점검</li>
          </ul>
        </Link>
      </div>
    </FinanceLayout>
  );
}
