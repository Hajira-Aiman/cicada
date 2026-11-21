import React, { useEffect, useState } from 'react';
import { apiFetch } from '@/services/apiClient';

// Row-wise PostgreSQL viewer (engineer login only; password hashes are never sent).
const DBS = ['airlock_in', 'airlock_eu', 'airlock_core'];
const cell = (v: any) => (v !== null && typeof v === 'object' ? JSON.stringify(v) : String(v ?? ''));

export const DatabaseTab: React.FC = () => {
  const [db, setDb] = useState(DBS[0]);
  const [tables, setTables] = useState<{ name: string; rows: number }[]>([]);
  const [table, setTable] = useState('');
  const [data, setData] = useState<{ columns: string[]; rows: any[] }>({ columns: [], rows: [] });
  const [err, setErr] = useState('');

  const load = () => {
    setErr('');
    apiFetch<{ tables: { name: string; rows: number }[] }>(`/api/db/tables?db=${db}`)
      .then((r) => { setTables(r.tables); setTable((t) => (r.tables.some((x) => x.name === t) ? t : r.tables[0]?.name || '')); })
      .catch((e) => setErr(String(e.message || e)));
  };
  useEffect(load, [db]);
  useEffect(() => {
    if (!table) return;
    apiFetch(`/api/db/rows?db=${db}&table=${table}&limit=200`).then(setData).catch((e) => setErr(String(e.message || e)));
  }, [db, table]);

  return (
    <div className="p-5 space-y-3 font-mono text-xs">
      <div className="flex flex-wrap items-center gap-2">
        {DBS.map((d) => (
          <button key={d} onClick={() => setDb(d)} className={`px-2 py-1 rounded border border-white/10 ${db === d ? 'bg-sky-500 text-black font-bold' : 'text-slate-400 hover:bg-white/5'}`}>{d}</button>
        ))}
        <button onClick={() => { load(); setTable((t) => t); apiFetch(`/api/db/rows?db=${db}&table=${table}&limit=200`).then(setData).catch(() => {}); }}
          className="px-2 py-1 rounded border border-white/10 text-slate-300 hover:bg-white/5">REFRESH</button>
        {err && <span className="text-red-400">{err}</span>}
      </div>
      <div className="flex flex-wrap gap-1">
        {tables.map((t) => (
          <button key={t.name} onClick={() => setTable(t.name)} className={`px-2 py-0.5 rounded border border-white/10 ${table === t.name ? 'bg-white/15 text-white' : 'text-slate-400 hover:bg-white/5'}`}>
            {t.name} <span className="text-slate-500">({t.rows})</span>
          </button>
        ))}
      </div>
      <div className="hud-panel overflow-auto max-h-[70vh] border border-white/10">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-[#0A0D15]"><tr>{data.columns.map((c) => <th key={c} className="px-2 py-1 text-sky-400 whitespace-nowrap">{c}</th>)}</tr></thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i} className="border-t border-white/5">
                {data.columns.map((c) => <td key={c} className="px-2 py-1 text-slate-300 max-w-[24rem] truncate" title={cell(r[c])}>{cell(r[c])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {!data.rows.length && <div className="p-6 text-center text-slate-500">No rows.</div>}
      </div>
    </div>
  );
};

export default DatabaseTab;
