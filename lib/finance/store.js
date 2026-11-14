import { useEffect, useRef, useState } from 'react';

// 브라우저 localStorage에 상태를 저장하는 훅 (SSR 안전)
export function useLocalState(key, initial) {
  const [state, setState] = useState(initial);
  const [loaded, setLoaded] = useState(false);
  const first = useRef(true);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        setState((prev) => ({ ...prev, ...parsed }));
      }
    } catch { /* 손상된 데이터는 무시 */ }
    setLoaded(true);
  }, [key]);

  useEffect(() => {
    if (!loaded) return;
    if (first.current) { first.current = false; return; }
    const t = setTimeout(() => {
      try { window.localStorage.setItem(key, JSON.stringify(state)); }
      catch (e) { console.warn('저장 실패', e); }
    }, 300);
    return () => clearTimeout(t);
  }, [key, state, loaded]);

  return [state, setState, loaded];
}

export function downloadJSON(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function readJSONFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => { try { resolve(JSON.parse(r.result)); } catch (e) { reject(new Error('JSON 형식이 아닙니다.')); } };
    r.onerror = () => reject(new Error('파일을 읽을 수 없습니다.'));
    r.readAsText(file);
  });
}
