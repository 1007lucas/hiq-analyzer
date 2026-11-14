import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

export const FINANCE_CSS = `
:root{--navy:#1F3864;--navy2:#15264A;--navylt:#2a4a80;--gold:#B08A2E;--goldl:#D8C28A;--goldfaint:#f5efd6;--paper:#F8F7F3;--white:#fff;--ink:#1a1a1a;--gray:#6b7280;--graylt:#e5e7eb;--red:#B23A2E;--redfaint:#fdf2f0;--green:#1a6b3a;--greenfaint:#f0faf4;--amber:#9a6700;--amberfaint:#fff7e0;--border:#d1d5db;
--series-1:#2a78d6;--series-2:#eb6834;--seq-200:#9ec5f4;--seq-450:#2a78d6;--seq-600:#184f95;--status-good:#008300;--status-warn:#c98500;--status-bad:#e34948;}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Noto Sans KR','Malgun Gothic',sans-serif;background:var(--paper);color:var(--ink);min-height:100vh;line-height:1.65;}
header.fin{background:var(--navy);padding:0 28px;display:flex;align-items:center;justify-content:space-between;height:58px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25);}
.logo{display:flex;align-items:center;gap:12px;color:#fff;text-decoration:none;}
.logo-mark{width:34px;height:34px;background:var(--gold);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:14px;color:var(--navy2);letter-spacing:.04em;}
.logo-text{color:#fff;font-weight:700;font-size:15px;line-height:1.2;}
.logo-sub{color:var(--goldl);font-size:11px;font-weight:400;display:block;margin-top:2px;}
.topnav{display:flex;gap:4px;}
.topnav a{color:rgba(255,255,255,.75);text-decoration:none;font-size:13px;font-weight:600;padding:6px 12px;border-bottom:2px solid transparent;}
.topnav a.active{color:#fff;border-bottom-color:var(--gold);}
.topnav a:hover{color:#fff;}
.main{max-width:1040px;margin:0 auto;padding:28px 20px 90px;}
.card{background:var(--white);border:1px solid var(--border);border-top:3px solid var(--navy);padding:22px 24px;margin-bottom:20px;box-shadow:0 2px 12px rgba(31,56,100,.08);}
.card.flat{border-top-color:var(--border);}
.card-title{font-weight:700;font-size:15px;color:var(--navy);margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.card-title small{font-weight:400;color:var(--gray);font-size:12px;}
.subtabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px;}
.subtab{padding:8px 16px;font-size:13.5px;font-weight:600;color:var(--gray);cursor:pointer;background:#fff;border:1px solid var(--border);}
.subtab.active{color:#fff;background:var(--navy);border-color:var(--navy);}
.subtab .cnt{display:inline-block;margin-left:6px;font-size:11px;background:var(--red);color:#fff;padding:0 6px;border-radius:9px;}
.btn{padding:9px 18px;font-size:13.5px;font-weight:700;cursor:pointer;border:none;transition:all .15s;display:inline-flex;align-items:center;gap:7px;font-family:inherit;}
.btn-primary{background:var(--navy);color:#fff;}
.btn-primary:hover{background:var(--navylt);}
.btn-primary:disabled{background:#9aafcc;cursor:not-allowed;}
.btn-ghost{background:transparent;color:var(--navy);border:1.5px solid var(--navy);}
.btn-ghost:hover{background:#eef2f8;}
.btn-ghost:disabled{opacity:.5;cursor:not-allowed;}
.btn-danger{background:transparent;color:var(--red);border:1.5px solid var(--red);}
.btn-sm{padding:5px 11px;font-size:12px;}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.btn-copy{background:var(--greenfaint);color:var(--green);border:1px solid #a7d4b8;cursor:pointer;padding:5px 12px;font-size:12px;font-weight:700;font-family:inherit;}
input[type=text],input[type=number],input[type=date],input[type=month],select,textarea{padding:7px 10px;border:1px solid var(--border);background:var(--paper);font-size:13.5px;color:var(--ink);font-family:inherit;}
input:focus,select:focus,textarea:focus{outline:2px solid var(--navy);outline-offset:1px;}
select{appearance:none;padding-right:26px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236b7280' stroke-width='1.5' fill='none'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 8px center;}
label.fl{display:block;font-size:11px;font-weight:700;color:var(--gray);letter-spacing:.06em;margin-bottom:4px;}
.field{display:flex;flex-direction:column;gap:2px;}
.grid{display:grid;gap:12px;}
.g2{grid-template-columns:1fr 1fr;} .g3{grid-template-columns:repeat(3,1fr);} .g4{grid-template-columns:repeat(4,1fr);}
.stat{background:#fff;border:1px solid var(--border);padding:14px 16px;}
.stat .lbl{font-size:11.5px;color:var(--gray);font-weight:700;letter-spacing:.04em;}
.stat .val{font-size:22px;font-weight:800;color:var(--navy);margin-top:2px;letter-spacing:-.01em;font-variant-numeric:tabular-nums;}
.stat .val.neg{color:var(--red);} .stat .val.pos{color:var(--green);}
.stat .delta{font-size:12px;color:var(--gray);margin-top:2px;}
.stat .delta.up{color:var(--red);} .stat .delta.down{color:var(--green);}
.meter-list{display:flex;flex-direction:column;gap:9px;}
.mrow{display:grid;grid-template-columns:150px 1fr 110px;gap:12px;align-items:center;font-size:13px;}
.mrow .nm{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.mrow .trk{height:10px;background:var(--graylt);position:relative;overflow:hidden;}
.mrow .bar{position:absolute;left:0;top:0;height:100%;background:var(--seq-450);border-radius:0 4px 4px 0;}
.mrow .bar.over{background:var(--status-bad);}
.mrow .bar.warn{background:var(--status-warn);}
.mrow .bar.income{background:var(--series-2);}
.mrow .lim{position:absolute;top:-2px;width:2px;height:14px;background:var(--ink);}
.mrow .v{text-align:right;font-variant-numeric:tabular-nums;color:#333;}
.mrow .v small{display:block;color:var(--gray);font-size:11px;}
table.tbl{width:100%;border-collapse:collapse;font-size:13px;}
.tbl th{text-align:left;font-size:11.5px;color:var(--gray);font-weight:700;letter-spacing:.04em;padding:8px 8px;border-bottom:2px solid var(--graylt);white-space:nowrap;}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--graylt);vertical-align:middle;}
.tbl td.num,.tbl th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
.tbl tr:hover td{background:#f6f8fc;}
.tbl .neg{color:var(--red);} .tbl .pos{color:var(--green);}
.tbl select,.tbl input{padding:3px 6px;font-size:12.5px;}
.tbl select{padding-right:22px;}
.chip{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;background:#eef2f8;color:var(--navy);white-space:nowrap;}
.chip.red{background:var(--redfaint);color:var(--red);} .chip.green{background:var(--greenfaint);color:var(--green);} .chip.amber{background:var(--amberfaint);color:var(--amber);} .chip.gray{background:var(--graylt);color:var(--gray);}
.drop-zone{border:2px dashed var(--border);padding:30px 20px;text-align:center;cursor:pointer;background:var(--paper);transition:border-color .2s,background .2s;}
.drop-zone:hover,.drop-zone.over{border-color:var(--navy);background:#eef2f8;}
.note{font-size:12.5px;color:var(--gray);line-height:1.6;}
.banner{padding:10px 14px;font-size:13px;margin-bottom:14px;border-left:4px solid var(--navy);background:#f0f3f9;}
.banner.warn{border-left-color:var(--amber);background:var(--amberfaint);color:#5c3d00;}
.banner.err{border-left-color:var(--red);background:var(--redfaint);color:var(--red);}
.banner.ok{border-left-color:var(--green);background:var(--greenfaint);color:var(--green);}
.ai-box{background:#f0f3f9;border-left:4px solid var(--gold);padding:14px 16px;font-size:13.5px;white-space:pre-wrap;line-height:1.75;}
.month-nav{display:inline-flex;align-items:center;gap:6px;}
.month-nav button{background:#fff;border:1px solid var(--border);width:28px;height:28px;cursor:pointer;font-size:14px;}
.month-nav .cur{font-weight:800;color:var(--navy);min-width:110px;text-align:center;font-size:15px;}
.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:var(--navy);color:#fff;padding:10px 22px;font-size:13.5px;font-weight:600;box-shadow:0 8px 32px rgba(31,56,100,.16);z-index:999;pointer-events:none;}
.spinner{width:14px;height:14px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:inline-block;}
.spinner.dark{border-color:rgba(31,56,100,.25);border-top-color:var(--navy);}
@keyframes spin{to{transform:rotate(360deg)}}
.hub{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:10px;}
.hub a{display:block;text-decoration:none;color:inherit;background:#fff;border:1px solid var(--border);border-top:4px solid var(--navy);padding:26px;box-shadow:0 2px 12px rgba(31,56,100,.08);transition:transform .15s,box-shadow .15s;}
.hub a:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(31,56,100,.14);}
.hub .h-ic{font-size:30px;margin-bottom:8px;}
.hub h2{font-size:18px;color:var(--navy);margin-bottom:6px;}
.hub ul{margin:10px 0 0 18px;font-size:13px;color:#444;}
.hub ul li{margin-bottom:3px;}
.row-actions{display:flex;gap:6px;}
.muted{color:var(--gray);}
.right{text-align:right;}
.sticky-sum{position:sticky;bottom:0;background:var(--goldfaint);border-top:2px solid var(--gold);padding:10px 14px;font-weight:700;font-size:13.5px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.legend{display:flex;gap:14px;font-size:12px;color:var(--gray);align-items:center;}
.legend i{display:inline-block;width:10px;height:10px;margin-right:5px;vertical-align:-1px;}
.tip{position:absolute;background:var(--ink);color:#fff;font-size:12px;padding:6px 9px;pointer-events:none;white-space:nowrap;z-index:5;transform:translate(-50%,-110%);}
@media(max-width:720px){header.fin{padding:0 14px;}.main{padding:18px 12px 70px;}.g3,.g4{grid-template-columns:1fr 1fr;}.hub{grid-template-columns:1fr;}.mrow{grid-template-columns:1fr;gap:4px;}.mrow .v{text-align:left;}.logo-sub{display:none;}.card{padding:16px;}}
@media(max-width:480px){.g2,.g3,.g4{grid-template-columns:1fr;}}
`;

export default function FinanceLayout({ title, children, active }) {
  const router = useRouter();
  const path = router?.pathname || '';
  const is = (p) => (active ? active === p : path === p);
  return (
    <>
      <Head>
        <title>{title ? `${title} · HIQ 재무 비서` : 'HIQ 재무 비서'}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700;800;900&display=swap" rel="stylesheet" />
      </Head>
      <style dangerouslySetInnerHTML={{ __html: FINANCE_CSS }} />
      <header className="fin">
        <Link href="/finance" className="logo">
          <div className="logo-mark">HIQ</div>
          <div className="logo-text">재무 비서<span className="logo-sub">학원 · 개인 전담</span></div>
        </Link>
        <nav className="topnav">
          <Link href="/finance/academy" className={is('/finance/academy') ? 'active' : ''}>학원</Link>
          <Link href="/finance/personal" className={is('/finance/personal') ? 'active' : ''}>개인</Link>
          <Link href="/">지문 분석기</Link>
        </nav>
      </header>
      <div className="main">{children}</div>
    </>
  );
}

export function useToast() {
  const [toast, setToast] = useState('');
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 2800);
    return () => clearTimeout(t);
  }, [toast]);
  const el = toast ? <div className="toast">{toast}</div> : null;
  return [setToast, el];
}
