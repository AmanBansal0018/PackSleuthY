import { useEffect, useState } from "react";
import "./App.css";

const API = {
  download: "/api/packages/download",
  source: "/api/source/discover",
  extract: "/api/artifacts/extract",
  compare: "/api/comparison/run",
  history: "/api/scans/history",
};

export default function App() {
  const [ecosystem, setEcosystem] = useState("npm");
  const [packageName, setPackageName] = useState("");
  const [version, setVersion] = useState("");
  const [backendStatus, setBackendStatus] = useState("Checking backend...");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [download, setDownload] = useState(null);
  const [source, setSource] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);

  async function request(path, body) {
    const response = await fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status})`);
    return data;
  }
  async function run(label, task) {
    setBusy(label); setError("");
    try { await task(); }
    catch (err) { setError(err.message || "Something went wrong."); }
    finally { setBusy(""); }
  }
  async function refreshHistory() {
    try {
      const response = await fetch(API.history);
      const data = await response.json();
      setHistory(data.scans || []);
    } catch { /* history is supplementary */ }
  }
  useEffect(() => {
    fetch("/api/health").then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(d => setBackendStatus(`${d.message} · v${d.version || "1.0"}`))
      .catch(() => setBackendStatus("Backend is not reachable. Start the API on port 8000."));
    refreshHistory();
  }, []);

  function scanPackage(event) {
    event.preventDefault();
    setDownload(null); setSource(null); setExtracted(null); setReport(null);
    run("download", async () => {
      const data = await request(API.download, { ecosystem, package_name: packageName.trim(), version: version.trim() });
      setDownload(data);
    });
  }
  function discover() {
    run("source", async () => {
      const data = await request(API.source, {
        ecosystem: download.ecosystem, package_name: download.package_name,
        version: download.version, saved_artifact_id: download.saved_artifact_id,
      });
      setSource(data);
    });
  }
  function extract() {
    run("extract", async () => {
      const data = await request(API.extract, {
        saved_artifact_id: download.saved_artifact_id, source_archive_id: source.source_archive_id,
      });
      setExtracted(data);
    });
  }
  function compare() {
    run("compare", async () => {
      const data = await request(API.compare, {
        package_extraction_id: extracted.package.extraction_id,
        source_extraction_id: extracted.source.extraction_id,
        ecosystem: download.ecosystem, package_name: download.package_name,
        version: download.version, saved_artifact_id: download.saved_artifact_id,
        source_status: source.match_status,
      });
      setReport(data); refreshHistory();
    });
  }

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#"><span className="brand-mark">P</span><span>PackSleuthY<small>SUPPLY CHAIN INSPECTOR</small></span></a>
        <span className="status"><i />{backendStatus}</span>
      </header>
      <main>
        <section className="hero">
          <p className="eyebrow">PACKAGE TRANSPARENCY · OPEN SOURCE SECURITY</p>
          <h1>Look beyond the<br/><em>published package.</em></h1>
          <p className="hero-copy">Trace a registry release back to its source, compare what was published, and inspect differences with evidence. No package code is installed or executed.</p>
        </section>

        <section className="workspace">
          <div className="section-heading"><div><span className="step">01</span><h2>Start an inspection</h2></div><span className="muted">Exact release required</span></div>
          <form className="scan-form" onSubmit={scanPackage}>
            <label>ECOSYSTEM<select value={ecosystem} onChange={e=>setEcosystem(e.target.value)} disabled={!!busy}><option value="npm">npm registry</option><option value="pypi">Python · PyPI</option></select></label>
            <label>PACKAGE NAME<input value={packageName} onChange={e=>setPackageName(e.target.value)} placeholder="express" required disabled={!!busy}/></label>
            <label>VERSION<input value={version} onChange={e=>setVersion(e.target.value)} placeholder="4.18.2" required disabled={!!busy}/></label>
            <button className="primary" disabled={!!busy}>{busy==="download"?"Downloading…":"Download release ↗"}</button>
          </form>
          {error && <div className="error" role="alert">{error}</div>}
          {download && <div className="result-panel">
            <div className="panel-title"><span className="check">✓</span><div><b>Published artifact downloaded</b><small>{download.package_name} · {download.version}</small></div><span className="pill">{download.integrity_verification_status}</span></div>
            <div className="metric-grid">
              <Metric label="ARTIFACT" value={download.artifact_filename}/><Metric label="FILE SIZE" value={formatSize(download.file_size_bytes)}/>
              <Metric label="SHA-256" value={download.sha256}/><Metric label="REGISTRY CHECK" value={download.integrity_verification_status}/>
            </div>
            <p className="safety-note">{download.safety_note}</p>
          </div>}
        </section>

        {download && <section className="workspace">
          <div className="section-heading"><div><span className="step">02</span><h2>Find the original source</h2></div><span className="muted">Registry metadata → GitHub</span></div>
          {!source ? <button className="secondary" onClick={discover} disabled={!!busy}>{busy==="source"?"Discovering repository…":"Discover source repository →"}</button> :
            <div className="result-panel">
              <div className="panel-title"><div><b>{source.repository_url || "Source repository unavailable"}</b><small>{source.explanation}</small></div><span className={`pill ${source.match_status}`}>{source.match_status}</span></div>
              <div className="metric-grid"><Metric label="MATCHING TAG" value={source.matching_tag || "Not found"}/><Metric label="COMMIT SHA" value={source.commit_sha || "Unavailable"}/><Metric label="CONFIDENCE" value={source.confidence}/></div>
              {source.source_archive_id && <button className="secondary" onClick={extract} disabled={!!busy}>{busy==="extract"?"Safely extracting…":"Extract package + source →"}</button>}
              {!source.source_archive_id && <p className="safety-note">A source archive could not be retrieved. Comparison is unavailable for this release.</p>}
            </div>}
        </section>}

        {extracted && <section className="workspace">
          <div className="section-heading"><div><span className="step">03</span><h2>Compare release contents</h2></div><span className="muted">Static analysis only</span></div>
          <div className="metric-grid"><Metric label="PACKAGE FILES" value={extracted.package.file_count}/><Metric label="SOURCE FILES" value={extracted.source.file_count}/><Metric label="REJECTED ENTRIES" value={(extracted.package.rejected_file_count || 0) + (extracted.source.rejected_file_count || 0)}/><Metric label="EXTRACTION" value="Complete"/></div>
          {((extracted.package.rejected_files || []).length + (extracted.source.rejected_files || []).length) > 0 && <div className="safety-note"><b>Some archive entries were deliberately rejected:</b><ul className="file-list">{[...extracted.package.rejected_files, ...extracted.source.rejected_files].slice(0,20).map((item,i)=><li key={`${item.path}-${i}`}><code>{item.path}</code> — {item.reason}</li>)}</ul></div>}
          <button className="primary" onClick={compare} disabled={!!busy}>{busy==="compare"?"Comparing files…":"Run file comparison →"}</button>
        </section>}

        {report && <section className="workspace report">
          <div className="section-heading"><div><span className="step">04</span><h2>Inspection report</h2></div><span className="pill">{report.findings.length} findings</span></div>
          <h3>{report.assessment}</h3>
          <div className="report-actions"><button className="secondary" onClick={()=>downloadReport(report, download, source, "json")}>Export JSON report ↓</button><button className="secondary" onClick={()=>downloadReport(report, download, source, "html")}>Export HTML report ↓</button></div>
          <div className="metric-grid">{Object.entries(report.comparison.summary).map(([k,v])=><Metric key={k} label={k.toUpperCase()+" FILES"} value={v}/>)}</div>
          <h4>Added files</h4><FileList files={report.comparison.added_files}/>
          <h4>Deleted files</h4><FileList files={report.comparison.deleted_files}/>
          <h4>Modified files</h4>
          {report.comparison.modified_files.length===0?<p className="muted">No modified files detected.</p>:report.comparison.modified_files.map(f=><details className="diff" key={f.path}><summary>{f.path}</summary><pre>{f.diff || "Binary or non-text file. Compare SHA-256 values in the API report."}</pre></details>)}
          <h4>Security indicators</h4>
          {report.findings.length===0?<p className="muted">No current heuristic indicators were triggered. This is not proof that the package is safe.</p>:report.findings.map((f,i)=><div className="finding" key={i}><span className={`severity ${f.severity}`}>{f.severity}</span><b>{f.title}</b><small>{f.file} · {f.confidence} confidence</small><p>{f.why_it_matters}</p><code>{f.evidence}</code></div>)}
          <p className="safety-note">{report.limitations.join(" ")}</p>
        </section>}

        <section className="history">
          <div className="section-heading"><div><span className="step">↗</span><h2>Recent comparisons</h2></div><button className="text-button" onClick={refreshHistory}>Refresh</button></div>
          {history.length===0?<p className="muted">Completed comparisons will appear here.</p>:history.map(item=><div className="history-row" key={item.id}><b>{item.package_name} <small>{item.version}</small></b><span>{item.ecosystem} · {item.source_status || "unknown"}</span><time>{new Date(item.created_at*1000).toLocaleString()}</time></div>)}
        </section>
      </main>
      <footer>PackSleuthY <span>·</span> Evidence-led package inspection <span>·</span> Never executes downloaded code</footer>
    </div>
  );
}
function Metric({label,value}) { return <div className="metric"><small>{label}</small><b title={String(value)}>{value}</b></div>; }
function FileList({files}) { return files.length ? <ul className="file-list">{files.map(f=><li key={f}>{f}</li>)}</ul> : <p className="muted">None detected.</p>; }
function formatSize(n) { if(typeof n!=="number") return "Unknown"; return n<1024?`${n} B`:n<1048576?`${(n/1024).toFixed(1)} KB`:`${(n/1048576).toFixed(2)} MB`; }

function downloadReport(report, packageInfo, sourceInfo, format) {
  const payload = { generated_at: new Date().toISOString(), package: packageInfo, source: sourceInfo, ...report };
  let content, type, filename;
  if (format === "json") {
    content = JSON.stringify(payload, null, 2); type = "application/json"; filename = "packsleuthy-report.json";
  } else {
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const findings = (report.findings || []).map(f => `<li><b>${esc(f.severity)} · ${esc(f.title)}</b><p>${esc(f.file)} — ${esc(f.why_it_matters)}</p><pre>${esc(f.evidence)}</pre></li>`).join("");
    const summary = Object.entries(report.comparison.summary).map(([k,v]) => `<li>${esc(k)}: ${esc(v)}</li>`).join("");
    content = `<!doctype html><html><head><meta charset="utf-8"><title>PackSleuthY report</title><style>body{font:15px system-ui;max-width:900px;margin:40px auto;padding:0 20px;color:#172334}pre{white-space:pre-wrap;background:#f2f5f8;padding:12px}li{margin:14px 0}</style></head><body><h1>PackSleuthY inspection report</h1><p>${esc(packageInfo.package_name)} ${esc(packageInfo.version)} · ${esc(packageInfo.ecosystem)}</p><p>Source: ${esc(sourceInfo?.repository_url || "Unavailable")} · tag: ${esc(sourceInfo?.matching_tag || "Unmatched")} · status: ${esc(sourceInfo?.match_status || "unknown")}</p><h2>${esc(report.assessment)}</h2><h3>Comparison summary</h3><ul>${summary}</ul><h3>Security findings</h3><ul>${findings || "<li>No current heuristic indicators were triggered.</li>"}</ul><p>Heuristic findings are indicators, not proof. A clean result does not prove a package is safe.</p></body></html>`;
    type = "text/html"; filename = "packsleuthy-report.html";
  }
  const url = URL.createObjectURL(new Blob([content], {type}));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}
