import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api.js";
import ManualLightTracking from "./ManualLightTracking.jsx";
import TrajectoryEditor from "./TrajectoryEditor.jsx";
import CbResultsDashboard from "./CbResultsDashboard.jsx";

// Palette
const COLORS = [
  "#F23535","#F24C35","#F26335","#F27935","#F29035","#F2A735","#F2BD35","#F2D435","#F2EB35","#E3F235",
  "#CCF235","#B6F235","#9FF235","#88F235","#72F235","#5BF235","#44F235","#35F23D","#35F254","#35F26A",
  "#35F281","#35F298","#35F2AE","#35F2C5","#35F2DC","#35F2F2","#35DCF2","#35C5F2","#35AEF2","#3598F2",
  "#3581F2","#356AF2","#3554F2","#353DF2","#4435F2","#5B35F2","#7235F2","#8835F2","#9F35F2","#B635F2",
  "#CC35F2","#E335F2","#F235EB","#F235D4","#F235BD","#F235A7","#F23590","#F23579","#F23563","#F2354C",
];

const TOOL_LABELS = {
  "Manual Circular Trajectory": "Light Tracking",
  "Subject Detector": "Subject Detection",
  "Positional Tracker": "Positional Tracking",
  "Subject Kinematics": "Subject Kinematics",
  "Collective Behavior Analysis": "Collective Behavior",
};
const TOOL_ORDER = [
  "Manual Circular Trajectory",
  "Subject Detector",
  "Positional Tracker",
  "Subject Kinematics",
  "Collective Behavior Analysis",
];
const TOOL_DOWNLOAD_ROLE = {
  "Collective Behavior Analysis": "windows",
};

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function App() {
  const [user, setUser] = useState(null);
  const [nav, setNav] = useState({ view: "home", lab: null, experiment: null, video: null });
  const [showAccount, setShowAccount] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [labs, setLabs] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [videos, setVideos] = useState([]);
  const [runs, setRuns] = useState([]);
  const [experimentFps, setExperimentFps] = useState(null);

  useEffect(() => {
    if (!nav.experiment) { setExperimentFps(null); return; }
    try {
      const v = localStorage.getItem(`cba-fps-${nav.experiment.id}`);
      setExperimentFps(v ? Number(v) : null);
    } catch { setExperimentFps(null); }
  }, [nav.experiment?.id]);

  function handleExperimentFpsChange(fps) {
    setExperimentFps(fps);
    if (!nav.experiment) return;
    try {
      if (fps == null) localStorage.removeItem(`cba-fps-${nav.experiment.id}`);
      else localStorage.setItem(`cba-fps-${nav.experiment.id}`, String(fps));
    } catch {}
  }

  useEffect(() => {
    const saved = sessionStorage.getItem("cba-session");
    if (saved) {
      const s = JSON.parse(saved);
      api.setToken(s.token);
      api.setSessionExpiredCallback(logout);
      setUser(s.user);
      api.scheduleRefresh(api.tokenExpiresIn(s.token));
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    if (nav.view === "home") loadLabs();
    if (nav.view === "lab" && nav.lab) loadExperiments(nav.lab.id);
    if (nav.view === "experiment" && nav.experiment) loadExperimentData(nav.experiment.id);
    if (nav.view === "video" && nav.experiment && nav.video) loadRuns(nav.experiment.id, nav.video.current_version_id);
  }, [user, nav.view, nav.lab?.id, nav.experiment?.id]);

  const run = async (work) => {
    setBusy(true); setError("");
    try { await work(); }
    catch (e) {
      if (e.message?.startsWith("401")) { logout(); return; }
      setError(e.message);
    }
    finally { setBusy(false); }
  };

  function onLoggedIn(auth) {
    api.setToken(auth.access_token);
    api.setSessionExpiredCallback(logout);
    api.scheduleRefresh(auth.expires_in);
    sessionStorage.setItem("cba-session", JSON.stringify({ token: auth.access_token, user: auth.user }));
    setUser(auth.user);
  }

  function logout() {
    api.setToken(null);
    api.cancelRefresh();
    api.setSessionExpiredCallback(null);
    sessionStorage.removeItem("cba-session");
    setUser(null);
    setNav({ view: "home", lab: null, experiment: null, video: null });
    setShowAccount(false);
    setLabs([]); setExperiments([]); setVideos([]); setRuns([]);
  }

  async function loadLabs() {
    const list = await api.listLaboratories().catch(() => []);
    setLabs(list);
  }

  async function loadExperiments(labId) {
    const list = await api.listExperiments(labId).catch(() => []);
    setExperiments(list);
  }

  async function loadExperimentData(experimentId) {
    const [files, runList] = await Promise.all([
      api.listFiles(experimentId).catch(() => []),
      api.listExperimentRuns(experimentId).catch(() => []),
    ]);
    setVideos(files.filter((f) => f.file_type === "video" && !f.deleted_at));
    setRuns(runList);
  }

  async function loadRuns(experimentId, fileVersionId = null) {
    const list = await api.listExperimentRuns(experimentId, fileVersionId).catch(() => []);
    setRuns(list);
  }

  const goHome = () => setNav({ view: "home", lab: null, experiment: null, video: null });
  const goLab = (lab) => setNav({ view: "lab", lab, experiment: null, video: null });
  const goExperiment = (exp) => setNav((p) => ({ ...p, view: "experiment", experiment: exp, video: null }));
  const goVideo = (video) => setNav((p) => ({ ...p, view: "video", video }));
  async function goVideoFromVideo(video) {
    if (nav.experiment) await loadRuns(nav.experiment.id);
    goVideo(video);
  }

  if (!user) return <LoginPanel onLoggedIn={onLoggedIn} run={run} busy={busy} />;

  return (
    <div className="shell" onClick={() => setShowAccount(false)}>
      {}
      <div className="topbar" onClick={(e) => e.stopPropagation()}>
        <div className="palette-strip" />
        <div className="navbar">
          <nav className="breadcrumb">
            {nav.view === "home"
              ? <span className="bc-current">Laboratories</span>
              : <button className="bc-btn" onClick={goHome}>Laboratories</button>}
            {nav.lab && <>
              <span className="bc-sep">›</span>
              {nav.view === "lab"
                ? <span className="bc-current">{nav.lab.name}</span>
                : <button className="bc-btn" onClick={() => goLab(nav.lab)}>{nav.lab.name}</button>}
            </>}
            {nav.experiment && <>
              <span className="bc-sep">›</span>
              {nav.view === "experiment"
                ? <span className="bc-current">{nav.experiment.title}</span>
                : <button className="bc-btn" onClick={() => goExperiment(nav.experiment)}>{nav.experiment.title}</button>}
            </>}
            {nav.video && <>
              <span className="bc-sep">›</span>
              <span className="bc-current">{nav.video.logical_name}</span>
            </>}
          </nav>
          <div className="account-area">
            <button className="account-btn" onClick={() => setShowAccount((s) => !s)}>
              <span className="avatar">{user.full_name.charAt(0).toUpperCase()}</span>
              {user.full_name}
            </button>
            {showAccount && (
              <div className="account-panel">
                <p className="ap-name">{user.full_name}</p>
                <p className="ap-email">{user.email}</p>
                <span className={`ap-role${user.is_system_admin ? " admin" : ""}`}>
                  {user.is_system_admin ? "System Administrator" : "Member"}
                </span>
                <button className="primary" style={{ width: "100%" }} onClick={logout}>Log out</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {}
      <div className="content-inner">
        {error && <p className="error" style={{ marginBottom: 12 }}>{error}</p>}

        {nav.view === "home" && (
          <HomeView
            labs={labs} user={user} busy={busy}
            onSelectLab={goLab}
            onCreateLab={(name) => run(async () => {
              const lab = await api.createLaboratory(name);
              await loadLabs();
              goLab(lab);
            })}
          />
        )}

        {nav.view === "lab" && nav.lab && (
          <LabView
            lab={nav.lab} experiments={experiments} busy={busy}
            onSelectExperiment={goExperiment}
            onCreateExperiment={(title) => run(async () => {
              const exp = await api.createExperiment(nav.lab.id, title);
              await loadExperiments(nav.lab.id);
              goExperiment(exp);
            })}
          />
        )}

        {nav.view === "experiment" && nav.experiment && (
          <ExperimentView
            experiment={nav.experiment} videos={videos} runs={runs} busy={busy}
            experimentFps={experimentFps} onExperimentFpsChange={handleExperimentFpsChange}
            onSelectVideo={goVideo}
            onUploaded={() => loadExperimentData(nav.experiment.id)}
            onRunsChanged={() => loadExperimentData(nav.experiment.id)}
            user={user}
          />
        )}

        {nav.view === "video" && nav.video && nav.experiment && (
          <VideoView
            key={nav.video.id}
            video={nav.video}
            experiment={nav.experiment}
            experimentFps={experimentFps}
            runs={runs}
            sortedVideos={[...videos].sort((a, b) => a.logical_name.localeCompare(b.logical_name, undefined, { numeric: true, sensitivity: "base" }))}
            onSessionExpired={() => { logout(); setError("Session expired. Please log in again."); }}
            onNavigate={goVideoFromVideo}
            onRunsChanged={() => loadRuns(nav.experiment.id, nav.video.current_version_id)}
          />
        )}
      </div>
    </div>
  );
}

function LoginPanel({ onLoggedIn, run, busy }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");

  const submit = (e) => {
    e.preventDefault();
    run(async () => onLoggedIn(
      registering ? await api.register(email, fullName, password) : await api.login(email, password)
    ));
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="palette-strip" style={{ borderRadius: "6px 6px 0 0", margin: "-32px -28px 24px", height: "10px", width: "auto" }} />
        <h2>{registering ? "Create account" : "Sign in"}</h2>
        <form className="column" onSubmit={submit}>
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          {registering && (
            <input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          )}
          <input
            type="password"
            placeholder={registering ? "Password (12+ characters)" : "Password"}
            value={password} onChange={(e) => setPassword(e.target.value)} required
          />
          <div className="row" style={{ marginTop: 4 }}>
            <button className="primary" type="submit" disabled={busy} style={{ flex: 1 }}>
              {registering ? "Register" : "Sign in"}
            </button>
            <button className="link" type="button" onClick={() => setRegistering(!registering)}>
              {registering ? "I have an account" : "Create account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function HomeView({ labs, user, busy, onSelectLab, onCreateLab }) {
  const [newName, setNewName] = useState("");

  return (
    <>
      <div className="view-header">
        <h2>Laboratories</h2>
      </div>

      {user.is_system_admin && (
        <div className="create-row">
          <input
            placeholder="New laboratory name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && newName.trim()) { onCreateLab(newName.trim()); setNewName(""); } }}
          />
          <button
            className="primary" disabled={busy || !newName.trim()}
            onClick={() => { onCreateLab(newName.trim()); setNewName(""); }}
          >
            Create
          </button>
        </div>
      )}

      {labs.length === 0
        ? <p className="empty">{user.is_system_admin ? "No laboratories yet. Create one above." : "No laboratories available."}</p>
        : (
          <div className="card-grid">
            {labs.map((lab) => (
              <button key={lab.id} className="card" onClick={() => onSelectLab(lab)}>
                <h3>{lab.name}</h3>
                <p>Click to view experiments</p>
              </button>
            ))}
          </div>
        )
      }
    </>
  );
}

function LabView({ lab, experiments, busy, onSelectExperiment, onCreateExperiment }) {
  const [newTitle, setNewTitle] = useState("");

  return (
    <>
      <div className="view-header">
        <h2>{lab.name}</h2>
      </div>

      <div className="create-row">
        <input
          placeholder="New experiment title"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && newTitle.trim()) { onCreateExperiment(newTitle.trim()); setNewTitle(""); } }}
        />
        <button
          className="primary" disabled={busy || !newTitle.trim()}
          onClick={() => { onCreateExperiment(newTitle.trim()); setNewTitle(""); }}
        >
          New experiment
        </button>
      </div>

      {experiments.length === 0
        ? <p className="empty">No experiments yet. Create one above.</p>
        : (
          <div className="card-grid">
            {experiments.map((exp) => (
              <button key={exp.id} className="card" onClick={() => onSelectExperiment(exp)}>
                <h3>{exp.title}</h3>
                <p>{exp.status}</p>
              </button>
            ))}
          </div>
        )
      }
    </>
  );
}


const naturalCompare = (a, b) =>
  a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });

const NICE_FPS = [1, 2, 5, 10, 15, 20, 24, 25, 30, 50, 60];

function ExperimentView({ experiment, videos, runs, busy, experimentFps, onExperimentFpsChange, onSelectVideo, onUploaded, onRunsChanged, user }) {
  const [pending, setPending] = useState([]);
  const [sortOrder, setSortOrder] = useState("natural");
  const [minVideoFps, setMinVideoFps] = useState(null);
  const [activeTab, setActiveTab] = useState("videos");
  const fileRef = useRef(null);

  const videoVersionIdsKey = videos.map((v) => v.current_version_id).filter(Boolean).sort().join(",");
  useEffect(() => {
    const ids = videos.map((v) => v.current_version_id).filter(Boolean);
    if (!ids.length) return;
    Promise.allSettled(ids.map((id) => api.getVideoMetadata(id))).then((results) => {
      const fpsList = results
        .filter((r) => r.status === "fulfilled" && r.value.fps > 0)
        .map((r) => r.value.fps);
      if (fpsList.length) setMinVideoFps(Math.min(...fpsList));
    });
  }, [videoVersionIdsKey]);

  const fpsOptions = NICE_FPS.filter((f) => minVideoFps == null || f <= Math.round(minVideoFps));
  const highestOption = fpsOptions.length ? fpsOptions[fpsOptions.length - 1] : null;

  function handleFpsSelect(e) {
    const raw = e.target.value;
    const next = raw === "" ? null : Number(raw);
    const hasKin = runs.some((r) => r.tool_name === "Subject Kinematics" && r.status === "succeeded");
    if (hasKin && experimentFps != null && next !== experimentFps) {
      if (!window.confirm(
        "This experiment already has kinematics runs. Changing FPS will make future runs produce different timestamps and speed units than existing ones.\n\nProceed?"
      )) return;
    }
    onExperimentFpsChange(next);
  }

  const isUploading = pending.some((p) => p.status === "uploading");

  const sortedVideos = [...videos].sort((a, b) => {
    const cmp = naturalCompare(a.logical_name, b.logical_name);
    return (sortOrder === "alpha-desc" || sortOrder === "natural-desc") ? -cmp : cmp;
  });

  function onFilesSelected(e) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setPending(files.map((f) => ({ file: f, status: "waiting", error: "" })));
    e.target.value = "";
  }

  async function upload() {
    const CONCURRENCY = 3;
    setPending((prev) => prev.map((p) => ({ ...p, status: "uploading", error: "" })));
    const results = Array(pending.length);
    const queue = pending.map((p, i) => ({ p, i }));
    async function worker() {
      let item;
      while ((item = queue.shift())) {
        const { p, i } = item;
        try {
          await api.uploadVideo(experiment.id, p.file);
          results[i] = { status: "fulfilled" };
        } catch (e) {
          results[i] = { status: "rejected", reason: e };
        }
        setPending((prev) =>
          prev.map((entry, idx) =>
            idx === i
              ? results[i].status === "fulfilled"
                ? { ...entry, status: "done" }
                : { ...entry, status: "error", error: results[i].reason?.message ?? "Failed" }
              : entry
          )
        );
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    if (results.some((r) => r.status === "fulfilled")) onUploaded();
  }

  const allDone = pending.length > 0 && pending.every((p) => p.status === "done" || p.status === "error");

  const TABS = [
    { key: "videos", label: "Videos" },
    { key: "data-import", label: "Data Import" },
    { key: "collective-behavior", label: "Collective Behavior Analysis" },
    { key: "debug", label: "Debug" },
  ];

  return (
    <>
      {/* Row 1: title + upload */}
      <div className="view-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>{experiment.title}</h2>
        <button className="primary" disabled={isUploading || busy} onClick={() => fileRef.current?.click()}>
          + Upload videos
        </button>
      </div>

      {/* Row 2: controls */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-end", margin: "10px 0 16px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: "9pt", color: "var(--text-muted, #aaa)" }}>Analysis FPS</span>
          <select
            value={experimentFps ?? ""}
            onChange={handleFpsSelect}
            style={{ fontSize: "9.5pt", minHeight: 32, padding: "0 6px" }}
          >
            <option value="">Native (auto)</option>
            {fpsOptions.map((f) => (
              <option key={f} value={f}>
                {f}{f === highestOption && minVideoFps != null ? " (highest available)" : ""} FPS
              </option>
            ))}
          </select>
        </div>
      </div>

      <input
        ref={fileRef} type="file" accept="video/*,.avi,.mp4,.mov,.mkv"
        multiple style={{ display: "none" }}
        onChange={onFilesSelected}
      />

      {pending.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8 }}>
            {pending.map((p, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: "10pt" }}>
                <span className={`pill ${p.status === "done" ? "succeeded" : p.status === "error" ? "failed" : p.status === "uploading" ? "running" : "queued"}`}>
                  {p.status}
                </span>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.file.name}</span>
                {p.error && <span className="step-err">{p.error}</span>}
              </div>
            ))}
          </div>
          <div className="row">
            {!allDone && (
              <button className="primary" disabled={isUploading} onClick={upload}>
                {isUploading ? `Uploading ${pending.length} file${pending.length > 1 ? "s" : ""}…` : `Upload ${pending.length} file${pending.length > 1 ? "s" : ""}`}
              </button>
            )}
            <button disabled={isUploading} onClick={() => setPending([])}>
              {allDone ? "Clear" : "Cancel"}
            </button>
          </div>
        </div>
      )}

      {/* Tab bar */}
      <div style={{ display: "flex", borderBottom: "2px solid var(--border, #333)", marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === t.key ? "2px solid var(--accent, #5BF235)" : "2px solid transparent",
              marginBottom: -2,
              padding: "8px 16px",
              cursor: "pointer",
              fontSize: "10pt",
              fontWeight: activeTab === t.key ? 600 : 400,
              color: activeTab === t.key ? "var(--accent, #5BF235)" : "var(--text-muted, #aaa)",
              transition: "color 0.15s, border-color 0.15s",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ minHeight: "60vh", width: "100%" }}>

        {/* Tab: Videos */}
        {activeTab === "videos" && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 14, width: "fit-content" }}>
              <span style={{ fontSize: "9pt", color: "var(--text-muted, #aaa)" }}>Sort Order</span>
              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
                style={{ fontSize: "9.5pt", minHeight: 32, padding: "0 8px" }}
              >
                <option value="natural">Numerical (Increasing)</option>
                <option value="natural-desc">Numerical (Decreasing)</option>
                <option value="alpha">Alphabetical (A → Z)</option>
                <option value="alpha-desc">Alphabetical (Z → A)</option>
              </select>
            </div>
            {sortedVideos.length === 0
              ? <p className="empty">No videos uploaded yet. Use the button above to add one.</p>
              : (
                <div className="card-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
                  {sortedVideos.map((v) => (
                    <VideoCard key={v.id} video={v} onClick={() => onSelectVideo(v)} />
                  ))}
                </div>
              )
            }
          </>
        )}

        {/* Tab: Data Import */}
        {activeTab === "data-import" && (
          <>
            <LightCsvImportPanel
              experiment={experiment} videos={videos} fps={experimentFps} busy={busy} onRunsChanged={onRunsChanged}
            />
            <CsvImportPanel
              experiment={experiment} videos={videos} fps={experimentFps} busy={busy} onRunsChanged={onRunsChanged}
            />
          </>
        )}

        {/* Tab: Collective Behavior Analysis */}
        {activeTab === "collective-behavior" && (
          <CollectiveBehaviorExperimentPanel
            experiment={experiment} videos={sortedVideos} runs={runs} busy={busy}
            experimentFps={experimentFps} onRunsChanged={onRunsChanged}
          />
        )}

        {activeTab === "debug" && (
          <DebugPanel videos={videos} user={user} onVideoDeleted={() => { onUploaded(); }} />
        )}

      </div>
    </>
  );
}

function LightCsvImportPanel({ experiment, videos, fps, busy, onRunsChanged }) {
  const [csvFiles, setCsvFiles] = useState([]);
  const [importing, setImporting] = useState(false);
  const [importResults, setImportResults] = useState(null);
  const [error, setError] = useState("");
  const csvRef = useRef(null);

  const videoStems = new Set(videos.map((v) => v.logical_name.replace(/\.[^.]+$/, "").toLowerCase()));

  function onCsvSelected(e) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setCsvFiles(files);
    setImportResults(null);
    setError("");
    e.target.value = "";
  }

  async function runImport() {
    setImporting(true);
    setError("");
    setImportResults(null);
    try {
      const started = await api.importLightCsv(experiment.id, fps, csvFiles);
      const finished = await api.waitForRun(started.id);
      setImportResults(finished.runtime_info);
      onRunsChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{ marginTop: 24 }}>
      <p className="section-label">Import Light Data</p>
      <div className="analysis-wizard">
        <p className="hint">
          Upload Light CSV files with columns: <code>frame</code>, <code>x</code>, <code>y</code> in pixel coordinates.
          Position <code>-1,-1</code> means no light.
        </p>

        <div className="row" style={{ marginBottom: 8 }}>
          <button disabled={importing || busy} onClick={() => csvRef.current?.click()}>
            Select light CSV files
          </button>
          <input
            ref={csvRef} type="file" accept=".csv,.txt" multiple style={{ display: "none" }}
            onChange={onCsvSelected}
          />
          {csvFiles.length > 0 && (
            <button className="primary" disabled={importing || busy} onClick={runImport}>
              {importing
                ? `Importing ${csvFiles.length} file${csvFiles.length > 1 ? "s" : ""}…`
                : `Import ${csvFiles.length} file${csvFiles.length > 1 ? "s" : ""}`}
            </button>
          )}
          {csvFiles.length > 0 && !importing && (
            <button onClick={() => { setCsvFiles([]); setImportResults(null); setError(""); }}>
              Clear
            </button>
          )}
        </div>

        {csvFiles.length > 0 && !importResults && (
          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 8 }}>
            {csvFiles.map((f, i) => {
              const stem = f.name.replace(/\.[^.]+$/, "").toLowerCase();
              const matched = videoStems.has(stem);
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "9.5pt" }}>
                  <span className={`pill ${matched ? "succeeded" : "failed"}`}>
                    {matched ? "matched" : "no video"}
                  </span>
                  <span style={{ color: "#ccc" }}>{f.name}</span>
                </div>
              );
            })}
          </div>
        )}

        {importResults && (
          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 8 }}>
            {Object.entries(importResults.results ?? {}).map(([name, r]) => (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "9.5pt" }}>
                <span className={`pill ${r.success ? "succeeded" : "failed"}`}>
                  {r.success ? "ok" : "error"}
                </span>
                <span style={{ color: "#ccc" }}>{name}</span>
                {r.success && (
                  <span className="hint">
                    cx={r.center_x} cy={r.center_y} r={r.radius_px}px · {r.n_valid_light_frames}/{r.n_frames} frames
                  </span>
                )}
                {r.error && <span className="step-err">{r.error}</span>}
              </div>
            ))}
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

function CsvImportPanel({ experiment, videos, fps, busy, onRunsChanged }) {
  const [csvFiles, setCsvFiles] = useState([]);
  const [importing, setImporting] = useState(false);
  const [importResults, setImportResults] = useState(null);
  const [error, setError] = useState("");
  const csvRef = useRef(null);

  const videoStems = new Set(videos.map((v) => v.logical_name.replace(/\.[^.]+$/, "").toLowerCase()));

  function onCsvSelected(e) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setCsvFiles(files);
    setImportResults(null);
    setError("");
    e.target.value = "";
  }

  async function runImport() {
    setImporting(true);
    setError("");
    setImportResults(null);
    try {
      const started = await api.importPositionCsv(experiment.id, fps, csvFiles);
      const finished = await api.waitForRun(started.id);
      setImportResults(finished.runtime_info);
      onRunsChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{ marginTop: 24 }}>
      <p className="section-label">Import Position Data</p>
      <div className="analysis-wizard">
        <p className="hint">
          Upload Position CSV with columns paired as x, y per subject in arena-centered coordinates (right = +x, down = +y).
        </p>

        <div className="row" style={{ marginBottom: 8 }}>
          <button disabled={importing || busy} onClick={() => csvRef.current?.click()}>
            Select CSV files
          </button>
          <input
            ref={csvRef} type="file" accept=".csv,.txt" multiple style={{ display: "none" }}
            onChange={onCsvSelected}
          />
          {csvFiles.length > 0 && (
            <button
              className="primary"
              disabled={importing || busy}
              onClick={runImport}
            >
              {importing ? `Importing ${csvFiles.length} file${csvFiles.length > 1 ? "s" : ""}…` : `Import ${csvFiles.length} file${csvFiles.length > 1 ? "s" : ""}`}
            </button>
          )}
          {csvFiles.length > 0 && !importing && (
            <button onClick={() => { setCsvFiles([]); setImportResults(null); setError(""); }}>
              Clear
            </button>
          )}
        </div>

        {csvFiles.length > 0 && !importResults && (
          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 8 }}>
            {csvFiles.map((f, i) => {
              const stem = f.name.replace(/\.[^.]+$/, "").toLowerCase();
              const matched = videoStems.has(stem);
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "9.5pt" }}>
                  <span className={`pill ${matched ? "succeeded" : "failed"}`}>
                    {matched ? "matched" : "no video"}
                  </span>
                  <span style={{ color: "#ccc" }}>{f.name}</span>
                </div>
              );
            })}
          </div>
        )}

        {importResults && (
          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 8 }}>
            {Object.entries(importResults.results ?? {}).map(([name, r]) => (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "9.5pt" }}>
                <span className={`pill ${r.success ? "succeeded" : "failed"}`}>
                  {r.success ? "ok" : "error"}
                </span>
                <span style={{ color: "#ccc" }}>{name}</span>
                {r.success && (
                  <span className="hint">
                    {r.n_subjects} subjects · {r.n_frames} frames · kinematics queued
                  </span>
                )}
                {r.error && <span className="step-err">{r.error}</span>}
              </div>
            ))}
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

const CB_FPS_OPTIONS = [
  { label: "Original",   frameStep: 1 },
  { label: "1/2 Frames", frameStep: 2 },
  { label: "1/4 Frames", frameStep: 4 },
  { label: "1/6 Frames", frameStep: 6 },
];

function CollectiveBehaviorExperimentPanel({ experiment, videos, runs, busy, experimentFps, onRunsChanged }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [cbFpsOption, setCbFpsOption] = useState(0); // index into CB_FPS_OPTIONS
  const [windowSize, setWindowSize] = useState(100);
  const [windowOverlap, setWindowOverlap] = useState(50);

  const cbRuns = [...runs.filter(
    (r) => r.tool_name === "Collective Behavior Analysis" && !r.parameters?.video_file_version_id
  )].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  const latestSucceeded = cbRuns.find((r) => r.status === "succeeded") ?? null;

  const [selectedRunId, setSelectedRunId] = useState(() => latestSucceeded?.id ?? null);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const videoNames = useMemo(
    () => Object.fromEntries(videos.filter((v) => v.current_version_id).map((v) => [v.current_version_id, v.logical_name])),
    [videos],
  );

  useEffect(() => {
    if (!selectedRunId && latestSucceeded) setSelectedRunId(latestSucceeded.id);
  }, [latestSucceeded?.id]);

  const selectedRun = cbRuns.find((r) => r.id === selectedRunId) ?? null;

  const trackedIds = new Set(
    runs
      .filter((r) => r.tool_name === "Positional Tracker" && r.status === "succeeded")
      .flatMap((r) => [
        r.parameters?.file_version_id,
        r.parameters?.source_file_version_id,
        r.parameters?.video_file_version_id,
      ])
      .filter(Boolean)
  );
  const readyCount = videos.filter((v) => trackedIds.has(v.current_version_id)).length;

  async function runAnalysis() {
    setRunning(true); setError("");
    try {
      const opt = CB_FPS_OPTIONS[cbFpsOption];
      const wstep = Math.max(1, windowSize - windowOverlap);
      const started = await api.startExperimentCB(experiment.id, {
        frameStep: opt.frameStep,
        fps: experimentFps,
        windowSize,
        windowStep: wstep,
      });
      const finished = await api.waitForRun(started.id);
      onRunsChanged();
      setSelectedRunId(finished.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  const olderRuns = cbRuns.slice(1);

  return (
    <div style={{ marginTop: 24 }}>
      <p className="section-label">Collective Behavior Analysis</p>
      <div className="analysis-wizard">
        <p className="hint">Runs GMM clustering and Markov chain analysis.</p>

        {videos.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <p style={{ fontSize: "9pt", color: "var(--text-muted, #aaa)", marginBottom: 6 }}>
              Videos ready for analysis — {readyCount} of {videos.length} have a completed trajectory
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {videos.map((v) => {
                const ready = trackedIds.has(v.current_version_id);
                return (
                  <div key={v.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "9.5pt" }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                      background: ready ? "#5BF235" : "#F23535",
                      boxShadow: ready ? "0 0 4px #5BF23588" : "0 0 4px #F2353588",
                    }} />
                    <span style={{ color: ready ? "var(--fg, #ddd)" : "var(--text-muted, #888)" }}>
                      {v.logical_name}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <label style={{ fontSize: "9pt", color: "var(--muted, #888)", minWidth: 80 }}>Subsampling rate</label>
            <div style={{ display: "flex", gap: 6 }}>
              {CB_FPS_OPTIONS.map((opt, i) => (
                <button
                  key={i}
                  style={{
                    fontSize: "9pt", padding: "3px 10px", borderRadius: 4,
                    background: cbFpsOption === i ? "var(--accent, #3581f2)" : "var(--panel, #fff)",
                    color: cbFpsOption === i ? "#fff" : "var(--fg, #333)",
                    border: `1px solid ${cbFpsOption === i ? "var(--accent, #3581f2)" : "var(--border, #ccc)"}`,
                    cursor: "pointer",
                  }}
                  onClick={() => setCbFpsOption(i)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {experimentFps != null && (
              <span style={{ fontSize: "9pt", color: "var(--muted, #888)" }}>
                {`= ${+(experimentFps / CB_FPS_OPTIONS[cbFpsOption].frameStep).toFixed(2)} fps`}
              </span>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <label style={{ fontSize: "9pt", color: "var(--muted, #888)", minWidth: 80 }}>Window size</label>
            <input
              type="number" min={10} max={10000} step={10}
              value={windowSize}
              onChange={(e) => setWindowSize(Math.max(10, parseInt(e.target.value) || 100))}
              style={{ width: 70, fontSize: "9pt" }}
            />
            <span style={{ fontSize: "9pt", color: "var(--muted, #888)" }}>frames</span>

            <label style={{ fontSize: "9pt", color: "var(--muted, #888)", marginLeft: 12 }}>Overlap</label>
            <input
              type="number" min={0} max={windowSize - 1} step={10}
              value={windowOverlap}
              onChange={(e) => setWindowOverlap(Math.min(windowSize - 1, Math.max(0, parseInt(e.target.value) || 0)))}
              style={{ width: 70, fontSize: "9pt" }}
            />
            <span style={{ fontSize: "9pt", color: "var(--muted, #888)" }}>
              frames&ensp;(step: {Math.max(1, windowSize - windowOverlap)})
            </span>
          </div>
        </div>

        <div className="row">
          <button className="primary" disabled={busy || running} onClick={runAnalysis}>
            {running ? "Running…" : "Run experiment analysis"}
          </button>
        </div>
        {error && <p className="error" style={{ marginTop: 6 }}>{error}</p>}

        {cbRuns.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <p className="section-label" style={{ margin: 0, fontSize: "9pt" }}>Analysis history</p>
              {olderRuns.length > 0 && (
                <button className="link" style={{ fontSize: "9pt" }} onClick={() => setHistoryExpanded((s) => !s)}>
                  {historyExpanded ? "Hide older" : `${olderRuns.length} older`}
                </button>
              )}
            </div>
            {[cbRuns[0], ...(historyExpanded ? olderRuns : [])].map((r) => (
              <CbHistoryItem
                key={r.id}
                run={r}
                selected={r.id === selectedRunId}
                onSelect={() => setSelectedRunId(r.id)}
              />
            ))}
          </div>
        )}
      </div>

      {selectedRun?.status === "succeeded" && (
        <CbResultsDashboard key={selectedRun.id} runIds={[{ label: "Results", id: selectedRun.id }]} videoNames={videoNames} />
      )}
    </div>
  );
}

function CbHistoryItem({ run, selected, onSelect }) {
  const conds = run.runtime_info?.conditions;
  const nVideos = run.runtime_info?.n_videos_processed;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
      padding: "5px 10px", borderRadius: 4, marginBottom: 3,
      border: `1px solid ${selected ? "var(--accent, #5BF235)" : "var(--border, #333)"}`,
      background: selected ? "rgba(91,242,53,0.04)" : "rgba(255,255,255,0.02)",
      fontSize: "9pt",
    }}>
      <span className={`pill ${run.status}`}>{run.status}</span>
      <span className="run-date">{fmtDate(run.created_at)}</span>
      {nVideos != null && <span style={{ color: "var(--muted, #888)" }}>{nVideos} videos</span>}
      {conds && Object.entries(conds).map(([cond, info]) => (
        <span key={cond} style={{ color: "var(--muted, #888)" }}>
          {cond === "no_stimulus" ? "no-stim" : cond}: k={info.best_k}, {info.n_windows}w
        </span>
      ))}
      {run.status === "succeeded" && !selected && (
        <button style={{ marginLeft: "auto" }} onClick={onSelect}>View</button>
      )}
      {run.status === "succeeded" && selected && (
        <span style={{ marginLeft: "auto", fontSize: "9pt", color: "var(--accent, #5BF235)" }}>Viewing</span>
      )}
      {run.error_message && <span className="step-err" style={{ flexBasis: "100%" }}>{run.error_message}</span>}
    </div>
  );
}

function DebugPanel({ videos, user, onVideoDeleted }) {
  const [state, setState] = useState("idle");
  const [done, setDone] = useState(0);
  const [errors, setErrors] = useState([]);

  const [deletingId, setDeletingId] = useState(null);
  const [deleteResults, setDeleteResults] = useState({});

  async function generateAll() {
    setState("running");
    setDone(0);
    setErrors([]);
    const errs = [];
    for (const v of videos) {
      if (!v.current_version_id) continue;
      try {
        await api.generateVideoThumbnail(v.current_version_id);
      } catch (e) {
        errs.push(`${v.logical_name}: ${e.message}`);
      }
      setDone((n) => n + 1);
    }
    setErrors(errs);
    setState("done");
  }

  async function deleteVideo(video) {
    const confirmed = window.confirm(
      `Permanently delete "${video.logical_name}" and all data derived from it?\n\nThis removes all tracking runs, analysis results, and the video file from disk. This action cannot be undone.`
    );
    if (!confirmed) return;
    setDeletingId(video.id);
    setDeleteResults((prev) => ({ ...prev, [video.id]: null }));
    try {
      await api.deleteVideo(video.id);
      setDeleteResults((prev) => ({ ...prev, [video.id]: { ok: true } }));
      onVideoDeleted();
    } catch (e) {
      setDeleteResults((prev) => ({ ...prev, [video.id]: { ok: false, msg: e.message } }));
    } finally {
      setDeletingId(null);
    }
  }

  const total = videos.filter((v) => v.current_version_id).length;
  const sortedVideos = [...videos].sort((a, b) =>
    a.logical_name.localeCompare(b.logical_name, undefined, { numeric: true, sensitivity: "base" })
  );

  return (
    <div>
      <p className="section-label" style={{ marginBottom: 16 }}>Debug Tools</p>

      <div className="analysis-wizard">
        <p className="section-label" style={{ marginBottom: 8, fontSize: "9.5pt" }}>Generate video thumbnails</p>
        <p className="hint" style={{ marginBottom: 10 }}>
          Generates and stores a mid-frame JPEG thumbnail for every video in this experiment.
          New uploads do this automatically; use this to backfill existing videos.
        </p>
        <div className="row" style={{ alignItems: "center", gap: 12 }}>
          <button
            className="primary"
            disabled={state === "running" || total === 0}
            onClick={generateAll}
          >
            {state === "running" ? `Generating… (${done} / ${total})` : "Generate for all videos"}
          </button>
          {state === "running" && (
            <div style={{ flex: 1, maxWidth: 240, height: 6, background: "var(--border, #333)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${total ? (done / total) * 100 : 0}%`, background: "#5BF235", transition: "width 0.2s" }} />
            </div>
          )}
          {state === "done" && (
            <span style={{ fontSize: "9pt", color: errors.length ? "#F23535" : "#5BF235" }}>
              {errors.length ? `Done — ${errors.length} error(s)` : `Done — all ${total} thumbnails generated`}
            </span>
          )}
        </div>
        {errors.length > 0 && (
          <div style={{ marginTop: 10, fontSize: "8.5pt", color: "#F23535", display: "flex", flexDirection: "column", gap: 2 }}>
            {errors.map((e, i) => <span key={i}>{e}</span>)}
          </div>
        )}
      </div>

      {user?.is_system_admin && (
        <div className="analysis-wizard" style={{ marginTop: 20, borderColor: "#F2353540" }}>
          <p className="section-label" style={{ marginBottom: 4, fontSize: "9.5pt", color: "#F23535" }}>Remove Video</p>
          <p className="hint" style={{ marginBottom: 12 }}>
            Permanently deletes a video and all data derived from it — tracking runs, analysis results, and the file on disk.
            This cannot be undone. Administrator only.
          </p>
          {sortedVideos.length === 0
            ? <p className="empty" style={{ fontSize: "9pt" }}>No videos in this experiment.</p>
            : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {sortedVideos.map((v) => {
                  const result = deleteResults[v.id];
                  const isDeleting = deletingId === v.id;
                  const deleted = result?.ok;
                  return (
                    <div key={v.id} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "6px 10px", borderRadius: 4,
                      background: "rgba(242,53,53,0.04)",
                      border: "1px solid #F2353530",
                      opacity: deleted ? 0.4 : 1,
                    }}>
                      <span style={{ flex: 1, fontSize: "9.5pt", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {v.logical_name}
                      </span>
                      {result?.ok && (
                        <span style={{ fontSize: "8.5pt", color: "#5BF235" }}>Deleted</span>
                      )}
                      {result && !result.ok && (
                        <span style={{ fontSize: "8.5pt", color: "#F23535" }}>{result.msg}</span>
                      )}
                      {!deleted && (
                        <button
                          style={{ color: "#F23535", borderColor: "#F2353560", fontSize: "9pt", padding: "3px 10px" }}
                          disabled={isDeleting || deletingId !== null}
                          onClick={() => deleteVideo(v)}
                        >
                          {isDeleting ? "Deleting…" : "Delete"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          }
        </div>
      )}
    </div>
  );
}

function VideoCard({ video, onClick }) {
  const [thumb, setThumb] = useState(null);

  useEffect(() => {
    if (!video.current_version_id) return;
    let url = null;
    let cancelled = false;
    api.getVideoThumbnail(video.current_version_id)
      .catch(() =>
        api.getVideoMetadata(video.current_version_id)
          .then((meta) => api.getVideoFrame(video.current_version_id, Math.floor((meta.frame_count - 1) / 2)))
      )
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setThumb(url);
      })
      .catch(() => {});
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [video.current_version_id]);

  return (
    <button className="video-card" onClick={onClick}>
      <div className="video-thumb">
        {thumb ? <img src={thumb} alt="" /> : <span>No preview</span>}
      </div>
      <div className="video-info">
        <h3>{video.logical_name}</h3>
        <p>{video.file_type}</p>
      </div>
    </button>
  );
}

const VIDEO_STEPS = [
  { n: 1, tool: "Manual Circular Trajectory", label: "Light Tracking" },
  { n: 2, tool: "Subject Detector",            label: "Subject Detection" },
  { n: 3, tool: "Positional Tracker",           label: "Subject Tracking" },
  { n: 4, tool: "Subject Kinematics",           label: "Subject Kinematics" },
];

function VideoView({ video, experiment, experimentFps, runs, sortedVideos, onSessionExpired, onNavigate, onRunsChanged }) {
  const [busy, setBusy] = useState(false);
  const run = async (work) => {
    setBusy(true);
    try { await work(); }
    catch (e) {
      if (e.message?.startsWith("401")) { onSessionExpired?.(); return; }
      throw e;
    }
    finally { setBusy(false); }
  };
  const vfvId = String(video.current_version_id ?? "");
  const forThisVideo = (r) =>
    r.parameters?.file_version_id === vfvId ||
    r.parameters?.source_file_version_id === vfvId ||
    r.parameters?.video_file_version_id === vfvId;

  const videoIndex = sortedVideos?.findIndex((v) => v.id === video.id) ?? -1;
  const prevVideo = videoIndex > 0 ? sortedVideos[videoIndex - 1] : null;
  const nextVideo = videoIndex >= 0 && videoIndex < (sortedVideos?.length ?? 0) - 1 ? sortedVideos[videoIndex + 1] : null;

  const [currentStep, setCurrentStep] = useState(() => {
    if (runs.some((r) => r.tool_name === "Subject Kinematics" && r.status === "succeeded" && forThisVideo(r))) return 4;
    if (runs.some((r) => r.tool_name === "Positional Tracker" && r.status === "succeeded" && forThisVideo(r))) return 4;
    if (runs.some((r) => r.tool_name === "Subject Detector" && r.status === "succeeded" && forThisVideo(r))) return 3;
    if (runs.some((r) => r.tool_name === "Manual Circular Trajectory" && r.status === "succeeded" && forThisVideo(r))) return 2;
    return 1;
  });

  const [selectedDetectionsFvId, setSelectedDetectionsFvId] = useState(() => {
    const r = runs.find((r) => r.tool_name === "Subject Detector" && r.status === "succeeded" && forThisVideo(r));
    return r?.runtime_info?.detections_file_version_id ?? null;
  });
  const [selectedDetectionFps, setSelectedDetectionFps] = useState(() => {
    const r = runs.find((r) => r.tool_name === "Subject Detector" && r.status === "succeeded" && forThisVideo(r));
    return r?.runtime_info?.fps ?? null;
  });
  const [trackingSettings, setTrackingSettings] = useState(() => {
    const r = runs.find((r) => r.tool_name === "Subject Detector" && r.status === "succeeded" && forThisVideo(r));
    const detFvId = r?.runtime_info?.detections_file_version_id;
    if (detFvId) {
      try {
        const saved = localStorage.getItem(`cba-tp-${detFvId}`);
        if (saved) {
          const p = JSON.parse(saved);
          return {
            maxDistance: p.maxDistance ?? 25,
            maxMissedFrames: p.maxMissedFrames ?? 5,
            maxTracks: p.maxTracks != null ? String(p.maxTracks) : "",
          };
        }
      } catch {}
    }
    return { maxDistance: 25, maxMissedFrames: 5, maxTracks: "" };
  });

  const [existingTrackingRun, setExistingTrackingRun] = useState(() =>
    runs.find((r) => r.tool_name === "Positional Tracker" && r.status === "succeeded" && forThisVideo(r)) ?? null
  );
  const [trajProgressList, setTrajProgressList] = useState([]);
  const [progressLoadFvId, setProgressLoadFvId] = useState(null);
  const [selectedTrajFvId, setSelectedTrajFvId] = useState(null);
  const [selectedKinemRunId, setSelectedKinemRunId] = useState(null);

  useEffect(() => {
    if (currentStep !== 3) return;
    const latestTracking = runs.find((r) => r.tool_name === "Positional Tracker" && r.status === "succeeded" && forThisVideo(r));
    if (!latestTracking) return;
    let cancelled = false;
    api.runOutputFileVersionId(latestTracking.id)
      .then((fvId) => api.listTrajectoryProgress(fvId))
      .then((list) => { if (!cancelled) setTrajProgressList(list); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [currentStep]);

  useEffect(() => {
    if (currentStep !== 4 || selectedTrajFvId) return;
    const latestTracking = runs.find((r) => r.tool_name === "Positional Tracker" && r.status === "succeeded" && forThisVideo(r));
    if (!latestTracking) return;
    let cancelled = false;
    api.runOutputFileVersionId(latestTracking.id)
      .then((fvId) => { if (!cancelled) setSelectedTrajFvId(fvId); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [currentStep]);

  const stepDef = VIDEO_STEPS[currentStep - 1];
  const stepRuns = [...runs]
    .filter((r) => r.tool_name === stepDef.tool && forThisVideo(r))
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  const latestSucceeded = stepRuns.find((r) => r.status === "succeeded");

  async function selectRun(r) {
    if (currentStep === 1) {
      setCurrentStep(2);
    } else if (currentStep === 2) {
      const detFvId = r.runtime_info?.detections_file_version_id ?? null;
      setSelectedDetectionsFvId(detFvId);
      setSelectedDetectionFps(r.runtime_info?.fps ?? null);
      if (detFvId) {
        try {
          const saved = localStorage.getItem(`cba-tp-${detFvId}`);
          if (saved) {
            const p = JSON.parse(saved);
            setTrackingSettings((ts) => ({
              ...ts,
              maxDistance: p.maxDistance ?? ts.maxDistance,
              maxMissedFrames: p.maxMissedFrames ?? ts.maxMissedFrames,
              maxTracks: p.maxTracks != null ? String(p.maxTracks) : "",
            }));
          }
        } catch {}
      }
      setExistingTrackingRun(null); // Selecting a detection = new tracking run
      setCurrentStep(3);
    } else if (currentStep === 3) {
      try {
        const fvId = await api.runOutputFileVersionId(r.id);
        setSelectedTrajFvId(fvId);
      } catch {}
      setCurrentStep(4);
    }
    onRunsChanged();
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <button disabled={!prevVideo} onClick={() => prevVideo && onNavigate(prevVideo)}>← Prev</button>
        <button disabled={!nextVideo} onClick={() => nextVideo && onNavigate(nextVideo)}>Next →</button>
        {sortedVideos && <span className="hint" style={{ marginLeft: 4 }}>{videoIndex + 1} / {sortedVideos.length}</span>}
      </div>
      <div className="view-header">
        <h2>{video.logical_name}</h2>
      </div>

      {/* Step navigation header */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
        <div style={{ flex: 1, display: "flex", justifyContent: "flex-start" }}>
          {currentStep > 1 && (
            <button onClick={() => setCurrentStep((s) => s - 1)}>← Previous Step</button>
          )}
        </div>
        <p className="section-label" style={{ margin: 0 }}>
          Step {currentStep} — {stepDef.label}
        </p>
        <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
          {currentStep < VIDEO_STEPS.length && (latestSucceeded || (currentStep === 3 && selectedTrajFvId)) && (
            <button onClick={async () => {
              if (currentStep === 3 && selectedTrajFvId) {
                setCurrentStep(4);
                onRunsChanged();
              } else {
                await selectRun(latestSucceeded);
              }
            }}>Next Step →</button>
          )}
        </div>
      </div>

      {/* Step content */}
      {currentStep === 1 && (
        <LightTrackingStep
          video={video} experiment={experiment} experimentFps={experimentFps} run={run} busy={busy}
          onComplete={() => { setCurrentStep(2); onRunsChanged(); }}
        />
      )}
      {currentStep === 2 && (
        <SubjectDetectionStep
          video={video} experiment={experiment} experimentFps={experimentFps} run={run} busy={busy}
          trackingSettings={trackingSettings} onTrackingSettingsChange={setTrackingSettings}
          onComplete={(detFvId, detFps) => {
            setSelectedDetectionsFvId(detFvId);
            setSelectedDetectionFps(detFps);
            setExistingTrackingRun(null); // New detection = Re-run tracking
            setCurrentStep(3);
            onRunsChanged();
          }}
          onRunsChanged={onRunsChanged}
        />
      )}
      {currentStep === 3 && (
        <SubjectTrackingStep
          video={video} experiment={experiment} experimentFps={experimentFps} run={run} busy={busy}
          detectionsFvId={selectedDetectionsFvId}
          detectionFps={selectedDetectionFps}
          trackingSettings={trackingSettings}
          existingTrackingRun={existingTrackingRun}
          progressLoadFvId={progressLoadFvId}
          onProgressListChange={setTrajProgressList}
          onTrajectoryConfirmed={(fvId) => { setSelectedTrajFvId(fvId); setCurrentStep(4); onRunsChanged(); }}
          onComplete={() => onRunsChanged()}
          onRunsChanged={onRunsChanged}
        />
      )}
      {currentStep === 4 && (
        <SubjectKinematicsStep
          video={video} experiment={experiment} experimentFps={experimentFps} run={run} busy={busy}
          trajectoryFvId={selectedTrajFvId}
          selectedRunId={selectedKinemRunId}
          onComplete={() => onRunsChanged()}
          onRunsChanged={onRunsChanged}
        />
      )}

      {/* Step history */}
      {(stepRuns.length > 0 || (currentStep === 3 && trajProgressList.length > 0)) && (
        <div style={{ marginTop: 24 }}>
          <p className="section-label">Analytics History</p>
          <div className="run-groups">
            {stepRuns.length > 0 && (
              <RunGroup
                label={TOOL_LABELS[stepDef.tool] ?? stepDef.label}
                runs={stepRuns}
                onSelect={
                  currentStep < 3 ? selectRun :
                  currentStep === 4 ? (r) => setSelectedKinemRunId(r.id) :
                  null
                }
              />
            )}
            {currentStep === 3 && trajProgressList.length > 0 && (
              <ProgressGroup
                label="Trajectory Progress"
                items={trajProgressList}
                onLoad={(p) => setProgressLoadFvId(p.file_version_id)}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function RunGroup({ label, runs, onSelect }) {
  const [expanded, setExpanded] = useState(false);
  const latest = runs[0];
  const older = runs.slice(1);

  return (
    <div className="run-group">
      <div className="run-group-title">
        <span>{label}</span>
        {older.length > 0 && (
          <button className="link" style={{ fontSize: "9pt" }} onClick={() => setExpanded((s) => !s)}>
            {expanded ? "Hide history" : `${older.length} older`}
          </button>
        )}
      </div>
      <RunItem run={latest} onSelect={onSelect} />
      {latest.error_message && <p className="run-error">{latest.error_message}</p>}
      {expanded && older.map((r) => (
        <div key={r.id}>
          <RunItem run={r} onSelect={onSelect} />
          {r.error_message && <p className="run-error">{r.error_message}</p>}
        </div>
      ))}
    </div>
  );
}

function ProgressGroup({ label, items, onLoad }) {
  const [expanded, setExpanded] = useState(false);
  const [latest, ...older] = items;

  const row = (p) => (
    <div className="run-item" key={p.file_version_id}>
      <span className="pill">v{p.version_number}</span>
      <span className="run-date">{fmtDate(p.uploaded_at)}</span>
      <button onClick={() => onLoad(p)}>Load</button>
    </div>
  );

  return (
    <div className="run-group">
      <div className="run-group-title">
        <span>{label}</span>
        {older.length > 0 && (
          <button className="link" style={{ fontSize: "9pt" }} onClick={() => setExpanded((s) => !s)}>
            {expanded ? "Hide history" : `${older.length} older`}
          </button>
        )}
      </div>
      {row(latest)}
      {expanded && older.map(row)}
    </div>
  );
}

function RunItem({ run, onSelect }) {
  const [downloading, setDownloading] = useState(false);
  const [dlErr, setDlErr] = useState("");

  async function download() {
    setDownloading(true); setDlErr("");
    try {
      const role = TOOL_DOWNLOAD_ROLE[run.tool_name] ?? null;
      const fvId = await api.runOutputFileVersionId(run.id, role);
      const blob = await api.downloadFileVersion(fvId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = ""; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDlErr(e.message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="run-item">
      <span className={`pill ${run.status}`}>{run.status}</span>
      <span className="run-date">{fmtDate(run.created_at)}</span>
      {run.status === "succeeded" && onSelect && (
        <button onClick={() => onSelect(run)}>Select</button>
      )}
      {run.status === "succeeded" && (
        <button disabled={downloading} onClick={download}>
          {downloading ? "…" : "Download"}
        </button>
      )}
      {dlErr && <span className="step-err">{dlErr}</span>}
    </div>
  );
}

// Detection presets (localStorage)
const PRESETS_KEY = "cba-detection-presets";
function loadPresets() { try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || "[]"); } catch { return []; } }
function savePresets(p) { try { localStorage.setItem(PRESETS_KEY, JSON.stringify(p)); } catch {} }

// Interactive detection preview canvas
function DetectionPreviewCanvas({ analysisData, showBw, onPlateChange, settings }) {
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const [localPlate, setLocalPlate] = useState(null);
  const [tooltip, setTooltip] = useState(null); // {x, y, spot}
  const dragRef = useRef(null); // 'move' | 'resize'

  useEffect(() => {
    if (analysisData?.plate) setLocalPlate({ ...analysisData.plate });
  }, [analysisData?.plate?.cx, analysisData?.plate?.cy, analysisData?.plate?.r]);

  const imgSrc = analysisData
    ? `data:image/jpeg;base64,${showBw ? analysisData.bw_image : analysisData.annotated_image}`
    : null;

  useEffect(() => {
    if (!imgSrc) return;
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = imgSrc;
  }, [imgSrc]);

  useEffect(() => { redraw(); }, [localPlate, showBw, analysisData]);

  function redraw() {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const s = 1080 / img.naturalWidth;
    canvas.width = 1080;
    canvas.height = Math.round(img.naturalHeight * s);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    if (!localPlate) return;
    const { cx, cy, r } = localPlate;
    ctx.beginPath();
    ctx.arc(cx * s, cy * s, r * s, 0, 2 * Math.PI);
    ctx.strokeStyle = "#50c850";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
    // drag handle at center
    ctx.beginPath();
    ctx.arc(cx * s, cy * s, 6, 0, 2 * Math.PI);
    ctx.fillStyle = "#50c850";
    ctx.fill();
  }

  function canvasScale() {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return 1;
    return 1080 / img.naturalWidth;
  }

  function toSource(canvasX, canvasY) {
    const s = canvasScale();
    return { x: canvasX / s, y: canvasY / s };
  }

  function canvasPos(e) {
    const r = canvasRef.current.getBoundingClientRect();
    return {
      x: ((e.clientX - r.left) * canvasRef.current.width) / r.width,
      y: ((e.clientY - r.top) * canvasRef.current.height) / r.height,
    };
  }

  function onPointerDown(e) {
    if (!localPlate) return;
    const s = canvasScale();
    const cp = canvasPos(e);
    const cx = localPlate.cx * s, cy = localPlate.cy * s, r = localPlate.r * s;
    const distCenter = Math.hypot(cp.x - cx, cp.y - cy);
    const distEdge = Math.abs(distCenter - r);
    if (distCenter < 12) { dragRef.current = "move"; canvasRef.current.setPointerCapture(e.pointerId); }
    else if (distEdge < 12) { dragRef.current = "resize"; canvasRef.current.setPointerCapture(e.pointerId); }
  }

  function onPointerMove(e) {
    if (!localPlate) return;
    const cp = canvasPos(e);
    const { x, y } = toSource(cp.x, cp.y);
    if (dragRef.current === "move") {
      setLocalPlate((p) => ({ ...p, cx: Math.round(x), cy: Math.round(y) }));
    } else if (dragRef.current === "resize") {
      const newR = Math.max(10, Math.round(Math.hypot(x - localPlate.cx, y - localPlate.cy)));
      setLocalPlate((p) => ({ ...p, r: newR }));
    } else {
      // hover: find nearest spot
      const spots = analysisData?.spots ?? [];
      let best = null, bestD = 18 ** 2;
      for (const sp of spots) {
        const d = (sp.x - x) ** 2 + (sp.y - y) ** 2;
        if (d < bestD) { bestD = d; best = sp; }
      }
      setTooltip(best ? { canvasX: cp.x, canvasY: cp.y, spot: best } : null);
    }
  }

  function onPointerUp(e) {
    if (dragRef.current && localPlate) {
      onPlateChange(localPlate);
    }
    dragRef.current = null;
  }

  return (
    <div style={{ position: "relative", display: "block", maxWidth: 1080, margin: "0 auto" }}>
      <canvas
        ref={canvasRef}
        style={{ display: "block", width: "100%", height: "auto", borderRadius: 4, cursor: dragRef.current ? "grabbing" : "crosshair" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setTooltip(null)}
      />
      {tooltip && (() => {
        const sp = tooltip.spot;
        const s = settings ?? {};
        const ok = (v, pass) => pass
          ? <span style={{ color: "#5BF235" }}>{v}</span>
          : <span style={{ color: "#f08080" }}>{v}</span>;
        const rows = [
          ["Position (px)", <span>{sp.x}, {sp.y}</span>, "origin top-left"],
          ["Area (px²)", ok(sp.area, sp.area >= (s.minArea ?? 0) && sp.area <= (s.maxArea ?? Infinity)),
           `range ${s.minArea ?? "—"}–${s.maxArea ?? "—"}`],
          ...(sp.solidity != null ? [["Solidity", ok(sp.solidity, sp.solidity > (s.minSolidity ?? 0)),
           `min ${s.minSolidity ?? "—"}`]] : []),
          ...(sp.aspect_ratio != null ? [["Aspect ratio", ok(sp.aspect_ratio,
           sp.aspect_ratio >= (s.minAspectRatio ?? 0) && sp.aspect_ratio <= (s.maxAspectRatio ?? Infinity)),
           `${s.minAspectRatio ?? "—"}–${s.maxAspectRatio ?? "—"}`]] : []),
          ...(sp.circularity != null ? [["Circularity", ok(sp.circularity, sp.circularity > (s.minCircularity ?? 0)),
           `min ${s.minCircularity ?? "—"}`]] : []),
        ];
        return (
          <div style={{
            position: "absolute", left: tooltip.canvasX + 12, top: tooltip.canvasY - 10,
            background: "rgba(0,0,0,0.90)", color: "#ddd", padding: "6px 10px",
            borderRadius: 5, fontSize: "8.5pt", pointerEvents: "none", zIndex: 10, lineHeight: 1.7,
          }}>
            <div style={{ marginBottom: 3, fontWeight: 600 }}>
              {sp.accepted
                ? <span style={{ color: "#5BF235" }}>✓ accepted</span>
                : <span style={{ color: "#f08080" }}>✗ {sp.reject?.replace(/_/g, " ")}</span>}
            </div>
            <table style={{ borderSpacing: "0 1px", fontSize: "8pt" }}>
              <tbody>
                {rows.map(([label, val, threshold]) => (
                  <tr key={label}>
                    <td style={{ paddingRight: 8, color: "#aaa" }}>{label}</td>
                    <td style={{ paddingRight: 8, fontVariantNumeric: "tabular-nums" }}>{val}</td>
                    <td style={{ color: "#666" }}>{threshold}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })()}
    </div>
  );
}

function LightTrackingStep({ video, experiment, experimentFps, run, busy, onComplete }) {
  return (
    <div className="analysis-wizard">
      <ManualLightTracking
        key={video.current_version_id}
        experimentId={experiment.id}
        videoVersionId={video.current_version_id}
        experimentFps={experimentFps}
        run={run} busy={busy}
        onComplete={onComplete}
      />
    </div>
  );
}

// Step 2: Subject Detection
function SubjectDetectionStep({ video, experiment, experimentFps, run, busy, trackingSettings, onTrackingSettingsChange, onComplete, onRunsChanged }) {
  const videoVersionId = video.current_version_id;
  const [settings, setSettings] = useState({
    numberOfFrames: "", minArea: 50, maxArea: 250, brightnessRatio: 0.85,
    minSolidity: 0.80, minAspectRatio: 0.5, maxAspectRatio: 2.0, minCircularity: 0.50,
  });
  const [detStep, setDetStep] = useState({ status: "pending", message: "", progress: 0, total: 0 });
  const [midFrameMeta, setMidFrameMeta] = useState(null);
  const [previewFrameIdx, setPreviewFrameIdx] = useState(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [showBw, setShowBw] = useState(false);
  const [plateLocked, setPlateLocked] = useState(null);
  const [presets, setPresets] = useState(loadPresets);
  const [presetName, setPresetName] = useState("");
  const [presetDeleteMode, setPresetDeleteMode] = useState(false);
  const debounceRef = useRef(null);

  const frameStep = (experimentFps && midFrameMeta?.fps && experimentFps < midFrameMeta.fps)
    ? Math.max(1, Math.round(midFrameMeta.fps / experimentFps))
    : 1;
  const rawFrameLimit = midFrameMeta
    ? (settings.numberOfFrames ? Math.min(Number(settings.numberOfFrames), midFrameMeta.frame_count) : midFrameMeta.frame_count)
    : null;
  const effectiveFrameCount = rawFrameLimit != null ? Math.ceil(rawFrameLimit / frameStep) : null;
  const currentNativeFrame = previewFrameIdx != null ? previewFrameIdx * frameStep : null;

  function jumpPreview(delta) {
    if (effectiveFrameCount == null || previewFrameIdx == null) return;
    setPreviewFrameIdx(Math.max(0, Math.min(effectiveFrameCount - 1, previewFrameIdx + delta)));
  }

  useEffect(() => {
    if (!videoVersionId) return;
    api.getVideoMetadata(videoVersionId)
      .then((meta) => {
        setMidFrameMeta(meta);
        const step = (experimentFps && experimentFps < meta.fps)
          ? Math.max(1, Math.round(meta.fps / experimentFps)) : 1;
        const effCount = Math.ceil(meta.frame_count / step);
        setPreviewFrameIdx(Math.floor((effCount - 1) / 2));
      })
      .catch(() => {});
  }, [videoVersionId, experimentFps]);

  // Fetch analysis data (debounced) on frame, param, or plate change
  useEffect(() => {
    if (!videoVersionId || currentNativeFrame == null) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setAnalysisLoading(true);
      api.getDetectionAnalysis(
        videoVersionId, currentNativeFrame,
        {
          minArea: Number(settings.minArea), maxArea: Number(settings.maxArea),
          brightnessRatio: Number(settings.brightnessRatio),
          minSolidity: Number(settings.minSolidity), minAspectRatio: Number(settings.minAspectRatio),
          maxAspectRatio: Number(settings.maxAspectRatio), minCircularity: Number(settings.minCircularity),
        },
        plateLocked,
      )
        .then((data) => setAnalysisData(data))
        .catch(() => {})
        .finally(() => setAnalysisLoading(false));
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [videoVersionId, currentNativeFrame, settings.minArea, settings.maxArea, settings.brightnessRatio,
      settings.minSolidity, settings.minAspectRatio, settings.maxAspectRatio, settings.minCircularity, plateLocked]);

  useEffect(() => {
    if (effectiveFrameCount != null && previewFrameIdx != null && previewFrameIdx >= effectiveFrameCount) {
      setPreviewFrameIdx(effectiveFrameCount - 1);
    }
  }, [effectiveFrameCount]);

  function handlePlateChange(newPlate) {
    setPlateLocked(newPlate);
  }

  function resetPlate() { setPlateLocked(null); }

  function savePreset() {
    const name = presetName.trim();
    if (!name) return;
    if (presets.some((p) => p.name === name)) return;
    const preset = {
      id: Date.now().toString(),
      name,
      minArea: Number(settings.minArea),
      maxArea: Number(settings.maxArea),
      brightnessRatio: Number(settings.brightnessRatio),
      minSolidity: Number(settings.minSolidity),
      minAspectRatio: Number(settings.minAspectRatio),
      maxAspectRatio: Number(settings.maxAspectRatio),
      minCircularity: Number(settings.minCircularity),
      numberOfFrames: settings.numberOfFrames ? Number(settings.numberOfFrames) : null,
      maxDistance: Number(trackingSettings.maxDistance),
      maxMissedFrames: Number(trackingSettings.maxMissedFrames),
      maxTracks: trackingSettings.maxTracks !== "" ? Number(trackingSettings.maxTracks) : null,
    };
    const updated = [...presets, preset];
    setPresets(updated);
    savePresets(updated);
    setPresetName("");
  }

  function deletePreset(id) {
    const updated = presets.filter((p) => p.id !== id);
    setPresets(updated);
    savePresets(updated);
  }

  function loadPreset(p) {
    setSettings((s) => ({
      ...s,
      minArea: p.minArea, maxArea: p.maxArea, brightnessRatio: p.brightnessRatio,
      minSolidity: p.minSolidity ?? s.minSolidity,
      minAspectRatio: p.minAspectRatio ?? s.minAspectRatio,
      maxAspectRatio: p.maxAspectRatio ?? s.maxAspectRatio,
      minCircularity: p.minCircularity ?? s.minCircularity,
      numberOfFrames: p.numberOfFrames != null ? String(p.numberOfFrames) : s.numberOfFrames,
    }));
    if (p.maxDistance != null || p.maxMissedFrames != null || p.maxTracks !== undefined) {
      onTrackingSettingsChange((ts) => ({
        ...ts,
        ...(p.maxDistance != null ? { maxDistance: p.maxDistance } : {}),
        ...(p.maxMissedFrames != null ? { maxMissedFrames: p.maxMissedFrames } : {}),
        ...(p.maxTracks !== undefined ? { maxTracks: p.maxTracks != null ? String(p.maxTracks) : "" } : {}),
      }));
    }
  }

  async function runDetection() {
    setDetStep({ status: "running", message: "", progress: 0, total: 0 });
    try {
      const started = await api.startRun("subject-detection", {
        experiment_id: experiment.id,
        file_version_id: videoVersionId,
        ...(frameStep > 1 ? { frame_step: frameStep } : {}),
        ...(settings.numberOfFrames ? { number_of_frames: Number(settings.numberOfFrames) } : {}),
        min_area: Number(settings.minArea),
        max_area: Number(settings.maxArea),
        brightness_ratio: Number(settings.brightnessRatio),
        min_solidity: Number(settings.minSolidity),
        min_aspect_ratio: Number(settings.minAspectRatio),
        max_aspect_ratio: Number(settings.maxAspectRatio),
        min_circularity: Number(settings.minCircularity),
        ...(plateLocked ? { plate_cx: plateLocked.cx, plate_cy: plateLocked.cy, plate_r: plateLocked.r } : {}),
      });
      const finished = await api.waitForRunWithProgress(
        started.id,
        (done, total) => setDetStep((s) => ({ ...s, progress: done, total })),
      );
      setDetStep({ status: "done", message: "", progress: 0, total: 0 });
      const detFvId = finished.runtime_info?.detections_file_version_id ?? null;
      if (detFvId) {
        try {
          localStorage.setItem(`cba-tp-${detFvId}`, JSON.stringify({
            maxDistance: Number(trackingSettings.maxDistance),
            maxMissedFrames: Number(trackingSettings.maxMissedFrames),
            maxTracks: trackingSettings.maxTracks !== "" ? Number(trackingSettings.maxTracks) : null,
          }));
        } catch {}
      }
      onComplete(detFvId, finished.runtime_info?.fps ?? null);
    } catch (e) {
      if (e.message?.startsWith("401")) throw e;
      setDetStep({ status: "failed", message: e.message, progress: 0, total: 0 });
      onRunsChanged();
    }
  }

  const acceptedCount = analysisData?.spots?.filter((s) => s.accepted).length ?? null;

  const pct = detStep.total > 0 ? Math.min(100, Math.round(detStep.progress / detStep.total * 100)) : null;
  const detRunning = detStep.status === "running";
  const detDone = detStep.status === "done";
  const detFailed = detStep.status === "failed";

  return (
    <div style={{ marginTop: 20 }}>
      <div className="step-card">

        {/* Preview canvas */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
            <button onClick={() => setShowBw((v) => !v)} style={{ fontWeight: 600 }}>
              {showBw ? "B&W threshold view" : "Color view"}
            </button>
            {analysisLoading && <span className="hint">Updating…</span>}
            {plateLocked && <button onClick={resetPlate} style={{ color: "#f08080", marginLeft: "auto" }}>Reset plate to auto</button>}
          </div>
          {analysisData
            ? <DetectionPreviewCanvas analysisData={analysisData} showBw={showBw} onPlateChange={handlePlateChange} settings={settings} />
            : <div style={{ width: "100%", height: 200, borderRadius: 4, background: "rgba(255,255,255,0.05)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span className="hint">Loading preview…</span>
              </div>
          }
          {effectiveFrameCount != null && previewFrameIdx != null && (
            <>
              <div className="row" style={{ marginTop: 6, gap: 6, alignItems: "center" }}>
                <button onClick={() => jumpPreview(-100)}>−100</button>
                <button onClick={() => jumpPreview(-10)}>−10</button>
                <button onClick={() => jumpPreview(-1)}>−1</button>
                <input type="range" min={0} max={effectiveFrameCount - 1} value={previewFrameIdx}
                  onChange={(e) => setPreviewFrameIdx(Number(e.target.value))} style={{ flex: 1 }} />
                <button onClick={() => jumpPreview(1)}>+1</button>
                <button onClick={() => jumpPreview(10)}>+10</button>
                <button onClick={() => jumpPreview(100)}>+100</button>
                <span className="hint" style={{ whiteSpace: "nowrap" }}>
                  {previewFrameIdx + 1} / {effectiveFrameCount}
                  {frameStep > 1 ? ` (${experimentFps} FPS)` : ""}
                </span>
              </div>
              <p className="hint" style={{ marginTop: 4 }}>
                {analysisData && `${acceptedCount} subject${acceptedCount !== 1 ? "s" : ""} detected`}
                {analysisData && ` · threshold ${analysisData.brightness_threshold} / ${analysisData.max_pixel}`}
                {" — hover spots for full parameter breakdown · drag plate circle to adjust arena boundary"}
              </p>
            </>
          )}
        </div>

        {/* Detection params */}
        <p className="section-label" style={{ fontSize: "9pt", marginBottom: 6 }}>Detection parameters</p>
        <div className="row" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          <label>Min area (px²)
            <input type="number" min="1" value={settings.minArea}
              onChange={(e) => setSettings({ ...settings, minArea: e.target.value })} />
          </label>
          <label>Max area (px²)
            <input type="number" min="1" value={settings.maxArea}
              onChange={(e) => setSettings({ ...settings, maxArea: e.target.value })} />
          </label>
          <label>Brightness ratio (0–1)
            <input type="number" min="0.01" max="1" step="0.01" value={settings.brightnessRatio}
              onChange={(e) => setSettings({ ...settings, brightnessRatio: e.target.value })} />
          </label>
        </div>

        {/* Shape filter params */}
        <p className="section-label" style={{ fontSize: "9pt", marginBottom: 6 }}>Shape filters</p>
        <div className="row" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          <label>Min solidity (0–1)
            <input type="number" min="0.01" max="1" step="0.01" value={settings.minSolidity}
              onChange={(e) => setSettings({ ...settings, minSolidity: e.target.value })} />
          </label>
          <label>Min aspect ratio
            <input type="number" min="0.01" step="0.01" value={settings.minAspectRatio}
              onChange={(e) => setSettings({ ...settings, minAspectRatio: e.target.value })} />
          </label>
          <label>Max aspect ratio
            <input type="number" min="0.01" step="0.01" value={settings.maxAspectRatio}
              onChange={(e) => setSettings({ ...settings, maxAspectRatio: e.target.value })} />
          </label>
          <label>Min circularity (0–1)
            <input type="number" min="0.01" max="1" step="0.01" value={settings.minCircularity}
              onChange={(e) => setSettings({ ...settings, minCircularity: e.target.value })} />
          </label>
        </div>

        {/* Frames limit */}
        <p className="section-label" style={{ fontSize: "9pt", marginBottom: 6 }}>Scope</p>
        <div className="row" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          <label>Frames to analyze (blank = all)
            <input type="number" min="1" value={settings.numberOfFrames}
              onChange={(e) => setSettings({ ...settings, numberOfFrames: e.target.value })} />
          </label>
        </div>

        {/* Tracking params (used in Step 3) */}
        <p className="section-label" style={{ fontSize: "9pt", marginBottom: 6 }}>Tracking parameters</p>
        <div className="row" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          <label>Max distance (px)
            <input type="number" min="1" value={trackingSettings.maxDistance}
              onChange={(e) => onTrackingSettingsChange({ ...trackingSettings, maxDistance: e.target.value })} />
          </label>
          <label>Max missed frames
            <input type="number" min="0" value={trackingSettings.maxMissedFrames}
              onChange={(e) => onTrackingSettingsChange({ ...trackingSettings, maxMissedFrames: e.target.value })} />
          </label>
          <label>Max subjects on screen (blank = unlimited)
            <input type="number" min="1" value={trackingSettings.maxTracks}
              onChange={(e) => onTrackingSettingsChange({ ...trackingSettings, maxTracks: e.target.value })} />
          </label>
        </div>

        {/* Presets */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
          <p className="section-label" style={{ fontSize: "9pt", margin: 0 }}>Presets</p>
          {presets.length > 0 && (
            <button
              onClick={() => setPresetDeleteMode((v) => !v)}
              style={{ color: presetDeleteMode ? "#f08080" : undefined, marginLeft: "auto" }}
            >
              Delete Presets Mode
            </button>
          )}
        </div>
        {presets.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {presets.map((p) => (
              <button
                key={p.id}
                onClick={() => presetDeleteMode ? deletePreset(p.id) : loadPreset(p)}
                style={{ padding: "4px 10px", fontSize: "9pt", color: presetDeleteMode ? "#f08080" : undefined }}
              >
                {p.name}
              </button>
            ))}
          </div>
        )}
        <div className="row" style={{ marginBottom: 16 }}>
          <input type="text" placeholder="Preset name…" value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && savePreset()}
            style={{ width: 180 }} />
          <button
            disabled={!presetName.trim() || presets.some((p) => p.name === presetName.trim())}
            onClick={savePreset}
          >Save preset</button>
        </div>

        <div className="row">
          <button className="primary" disabled={busy || !videoVersionId} onClick={() => run(runDetection)}>
            Run detection
          </button>
        </div>

        {/* Progress bar */}
        {(detRunning || detDone || detFailed) && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span className={`dot ${detStep.status}`} />
            <span className="step-status" style={{ fontSize: "9pt", flexShrink: 0 }}>
              Subject detection{detRunning && pct != null ? ` — ${pct}%` : ` — ${detStep.status}`}
            </span>
            {detStep.message && <span className="step-err" style={{ flexShrink: 0 }}> — {detStep.message}</span>}
            {(detRunning || detDone) && (
              <div style={{ flex: 1, minWidth: 40, height: 10, border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 3,
                  background: detFailed ? "var(--error)" : detRunning ? "#F2BD35" : "var(--success)",
                  width: detRunning && pct == null ? "35%" : `${detDone ? 100 : (pct ?? 0)}%`,
                  transition: detRunning && pct == null ? undefined : "width 0.35s ease",
                  animation: detRunning && pct == null ? "progress-slide 1.4s linear infinite" : undefined,
                }} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Step 3: Subject Tracking
function SubjectTrackingStep({ video, experiment, experimentFps, run, busy, detectionsFvId, detectionFps, trackingSettings, existingTrackingRun, progressLoadFvId, onProgressListChange, onTrajectoryConfirmed, onComplete, onRunsChanged }) {
  const videoVersionId = video.current_version_id;
  const [trackStep, setTrackStep] = useState({ status: "pending", message: "", progress: 0, total: 0 });
  const [originalTrajFvId, setOriginalTrajFvId] = useState(null);
  const [nativeFps, setNativeFps] = useState(null);

  useEffect(() => {
    if (!videoVersionId) return;
    api.getVideoMetadata(videoVersionId).then((m) => setNativeFps(m.fps)).catch(() => {});
  }, [videoVersionId]);

  useEffect(() => {
    if (!detectionsFvId) return;
    if (existingTrackingRun) {
      // Load existing run's output without re-running
      api.runOutputFileVersionId(existingTrackingRun.id)
        .then((fvId) => {
          setOriginalTrajFvId(fvId);
          setTrackStep({ status: "done", message: "", progress: 0, total: 0 });
        })
        .catch(() => run(runTracking));
    } else {
      run(runTracking);
    }
  }, []);

  async function runTracking() {
    setTrackStep({ status: "running", message: "", progress: 0, total: 0 });
    setOriginalTrajFvId(null);
    try {
      const started = await api.startRun("positional-tracking", {
        experiment_id: experiment.id,
        file_version_id: videoVersionId,
        detections_file_version_id: detectionsFvId,
        max_distance: Number(trackingSettings.maxDistance),
        max_missed_frames: Number(trackingSettings.maxMissedFrames),
        ...(trackingSettings.maxTracks ? { max_tracks: Number(trackingSettings.maxTracks) } : {}),
      });
      const finished = await api.waitForRunWithProgress(
        started.id,
        (done, total) => setTrackStep((s) => ({ ...s, progress: done, total })),
      );
      setTrackStep({ status: "done", message: "", progress: 0, total: 0 });
      const fvId = await api.runOutputFileVersionId(finished.id);
      setOriginalTrajFvId(fvId);
    } catch (e) {
      if (e.message?.startsWith("401")) throw e;
      setTrackStep({ status: "failed", message: e.message, progress: 0, total: 0 });
      onRunsChanged();
    }
  }

  function StepBar({ st, label, amber, noTopMargin }) {
    const pct = st.total > 0 ? Math.min(100, Math.round(st.progress / st.total * 100)) : null;
    const running = st.status === "running";
    const done = st.status === "done";
    const failed = st.status === "failed";
    if (!running && !done && !failed) return null;
    const barColor = failed ? "var(--error)" : running ? "#F2BD35" : amber ? "#F2BD35" : "var(--success)";
    const indeterminate = running && pct == null;
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: noTopMargin ? 0 : 12 }}>
        <span className={`dot ${st.status}`} style={amber && done ? { background: "#F2BD35" } : {}} />
        <span className="step-status" style={{ fontSize: "9pt", flexShrink: 0 }}>
          {label}{running && pct != null ? ` — ${pct}%` : ` — ${st.status}`}
        </span>
        {st.message && <span className="step-err" style={{ flexShrink: 0 }}> — {st.message}</span>}
        {(running || done) && (
          <div style={{ flex: 1, minWidth: 40, height: 10, border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 3, background: barColor,
              width: indeterminate ? "35%" : `${done ? 100 : (pct ?? 0)}%`,
              transition: indeterminate ? undefined : "width 0.35s ease",
              animation: indeterminate ? "progress-slide 1.4s linear infinite" : undefined,
            }} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div>

      {/* Tracking progress */}
      <div className="step-card" style={{ marginTop: 20, marginBottom: 16 }}>
        {!detectionsFvId
          ? <p className="hint">No detection data selected. Go back to Step 2 and run detection or select a previous run.</p>
          : (
            <>
              <StepBar st={trackStep} label="Positional tracking" amber noTopMargin />
              {trackStep.status === "done" && (
                <button
                  style={{ marginTop: 8, fontSize: "8pt" }}
                  disabled={busy}
                  onClick={() => { setOriginalTrajFvId(null); run(runTracking); }}
                >
                  ↺ Re-run Tracking
                </button>
              )}
            </>
          )
        }
      </div>

      {/* Trajectory editor: full width */}
      {originalTrajFvId && (
        <div className="panel-enter step-card" style={{ marginBottom: 16 }}>
          <p className="section-label" style={{ fontSize: "9pt", marginBottom: 10 }}>Tracking</p>
          <TrajectoryEditor
            videoVersionId={videoVersionId}
            trajectoryFileVersionId={originalTrajFvId}
            experimentFps={experimentFps}
            nativeFps={nativeFps}
            maxTracks={trackingSettings.maxTracks}
            detectionsFvId={detectionsFvId}
            maxDistance={Number(trackingSettings.maxDistance) || 20}
            maxMissedFrames={Number(trackingSettings.maxMissedFrames) || 5}
            progressLoadFvId={progressLoadFvId}
            onProgressListChange={onProgressListChange}
            onSaved={(newFvId) => onTrajectoryConfirmed?.(newFvId)}
          />
        </div>
      )}

    </div>
  );
}

function parseKinematicsCSV(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
  if (!lines.length) return new Map();
  const headers = lines[0].split(",");
  const col = (name) => headers.indexOf(name);
  const fv = (parts, name) => { const v = parseFloat(parts[col(name)]); return isFinite(v) ? v : null; };
  const tracks = new Map();
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    const tid = parseInt(parts[col("track_id")]);
    if (isNaN(tid)) continue;
    const row = {
      frame: parseInt(parts[col("frame")]) || 0,
      x: fv(parts, "x") ?? 0,
      y: fv(parts, "y") ?? 0,
      speed: fv(parts, "speed"),
      acceleration: fv(parts, "acceleration"),
      displacement_px: fv(parts, "displacement_px"),
      heading_deg: fv(parts, "heading_deg"),
    };
    if (!tracks.has(tid)) tracks.set(tid, []);
    tracks.get(tid).push(row);
  }
  for (const [, pts] of tracks) pts.sort((a, b) => a.frame - b.frame);
  return tracks;
}

function parseTrajectoryCSV(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
  if (!lines.length) return new Map();
  const headers = lines[0].split(",");
  const col = (name) => headers.indexOf(name);
  const byFrame = new Map();
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    const tid = parseInt(parts[col("track_id")]);
    const frame = parseInt(parts[col("frame")]);
    const x = parseFloat(parts[col("x")]);
    const y = parseFloat(parts[col("y")]);
    if (isNaN(tid) || isNaN(frame) || !isFinite(x) || !isFinite(y)) continue;
    const predicted = (parts[col("is_predicted")] ?? "").trim().toLowerCase() === "true";
    if (!byFrame.has(frame)) byFrame.set(frame, new Map());
    byFrame.get(frame).set(tid, { x, y, predicted });
  }
  return byFrame;
}

function KinematicsViewer({ videoVersionId, trajectoryFvId, kinematicsFvId, experimentFps }) {
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const frameUrlRef = useRef(null);
  const hoverRef = useRef(null); // {tid, x, y, predicted, speed, accel, heading}

  // trajectory positions: Map<frame, Map<tid, {x,y,predicted}>>
  const [trajByFrame, setTrajByFrame] = useState(new Map());
  // kinematics for summary: Map<tid, [{frame, speed, ...}]>
  const [kinData, setKinData] = useState(new Map());
  // kinematics by frame for hover: Map<frame, Map<tid, kinRow>>
  const [kinByFrame, setKinByFrame] = useState(new Map());
  const [frameList, setFrameList] = useState([]); // sorted experiment-space frame numbers
  const [frameIdx, setFrameIdx] = useState(0);
  const [nativeFps, setNativeFps] = useState(null);
  const [hoverTid, setHoverTid] = useState(null); // drives re-render on hover change

  // frameStep converts experiment-space frame index → native video frame index
  const frameStep = (experimentFps && nativeFps && experimentFps < nativeFps)
    ? Math.max(1, Math.round(nativeFps / experimentFps)) : 1;

  useEffect(() => {
    if (!videoVersionId) return;
    api.getVideoMetadata(videoVersionId).then((m) => setNativeFps(m.fps)).catch(() => {});
  }, [videoVersionId]);

  useEffect(() => {
    const fvId = trajectoryFvId ?? kinematicsFvId;
    if (!fvId) return;
    api.downloadFileVersion(fvId).then(async (blob) => {
      const text = await blob.text();
      let byFrame;
      if (trajectoryFvId) {
        byFrame = parseTrajectoryCSV(text);
      } else {
        // no trajectory: build positions from kinematics CSV
        byFrame = new Map();
        for (const [tid, pts] of parseKinematicsCSV(text).entries()) {
          for (const p of pts) {
            if (!byFrame.has(p.frame)) byFrame.set(p.frame, new Map());
            byFrame.get(p.frame).set(tid, { x: p.x, y: p.y, predicted: false });
          }
        }
      }
      setTrajByFrame(byFrame);
      setFrameList(Array.from(byFrame.keys()).sort((a, b) => a - b));
      setFrameIdx(0);
    }).catch(() => {});
  }, [trajectoryFvId, kinematicsFvId]);

  useEffect(() => {
    if (!kinematicsFvId) return;
    api.downloadFileVersion(kinematicsFvId).then(async (blob) => {
      const text = await blob.text();
      const data = parseKinematicsCSV(text);
      setKinData(data);
      const kbf = new Map();
      for (const [tid, pts] of data.entries()) {
        for (const p of pts) {
          if (!kbf.has(p.frame)) kbf.set(p.frame, new Map());
          kbf.get(p.frame).set(tid, p);
        }
      }
      setKinByFrame(kbf);
    }).catch(() => {});
  }, [kinematicsFvId]);

  const currentFrame = frameList[frameIdx] ?? 0;

  useEffect(() => {
    if (!videoVersionId || !frameList.length) return;
    let cancelled = false;
    api.getVideoFrame(videoVersionId, currentFrame * frameStep).then((blob) => {
      if (cancelled) return;
      if (frameUrlRef.current) { URL.revokeObjectURL(frameUrlRef.current); frameUrlRef.current = null; }
      const url = URL.createObjectURL(blob);
      frameUrlRef.current = url;
      const img = new Image();
      img.onload = () => { if (!cancelled) { imgRef.current = img; redraw(); } };
      img.src = url;
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [frameIdx, currentFrame, frameStep, videoVersionId, frameList.length]);

  // Redraw when data or hover tid changes
  useEffect(() => { redraw(); }, [trajByFrame, kinByFrame, hoverTid]);

  function redraw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const W = 1080;
    const img = imgRef.current;
    if (!img) {
      canvas.width = W; canvas.height = Math.round(W * 9 / 16);
      const ctx = canvas.getContext("2d"); ctx.fillStyle = "#111"; ctx.fillRect(0, 0, W, canvas.height);
      return;
    }
    const s = W / img.naturalWidth;
    canvas.width = W;
    canvas.height = Math.round(img.naturalHeight * s);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    const frameData = trajByFrame.get(currentFrame);
    if (!frameData) return;

    const trailStart = Math.max(0, frameIdx - 20);
    for (const [tid] of frameData.entries()) {
      const pts = [];
      for (let fi = trailStart; fi <= frameIdx; fi++) {
        const p = trajByFrame.get(frameList[fi])?.get(tid);
        if (p) pts.push(p);
      }
      if (pts.length > 1) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x * s, pts[0].y * s);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x * s, pts[i].y * s);
        ctx.strokeStyle = COLORS[tid % COLORS.length] + "66";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }

    for (const [tid, { x, y, predicted }] of frameData.entries()) {
      const color = COLORS[tid % COLORS.length];
      ctx.beginPath();
      ctx.arc(x * s, y * s, 6, 0, 2 * Math.PI);
      if (predicted) {
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
      } else {
        ctx.fillStyle = color; ctx.fill();
      }
    }

    // Hover overlay
    const hover = hoverRef.current;
    if (!hover) return;
    const { x, y, heading } = hover;
    const hx = x * s, hy = y * s;

    ctx.beginPath();
    ctx.arc(hx, hy, 10, 0, 2 * Math.PI);
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();

    if (heading != null && isFinite(heading)) {
      const rad = (heading * Math.PI) / 180;
      const tx = hx + 26 * Math.cos(rad), ty = hy + 26 * Math.sin(rad);
      ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(tx, ty);
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
      for (const wa of [rad + 2.6, rad - 2.6]) {
        ctx.beginPath(); ctx.moveTo(tx, ty);
        ctx.lineTo(tx + 8 * Math.cos(wa), ty + 8 * Math.sin(wa));
        ctx.stroke();
      }
    }

    const { tid, speed, accel, predicted: isPred } = hover;
    const lines = [
      `Subject ${tid}${isPred ? "  (predicted)" : ""}`,
      `x=${x.toFixed(1)}  y=${y.toFixed(1)}`,
      speed != null ? `speed: ${speed.toFixed(2)} px/${experimentFps ? "s" : "frame"}` : "speed: n/a",
      accel != null ? `accel: ${accel.toFixed(2)} px/${experimentFps ? "s" : "frame"}²` : "accel: n/a",
      heading != null ? `heading: ${heading.toFixed(0)}°` : "heading: n/a",
    ];
    ctx.font = "13px sans-serif";
    const lh = 17, pad = 8;
    const bw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + pad * 2;
    const bh = lines.length * lh + pad * 2;
    let bx = hx + 14, by = hy + 14;
    if (bx + bw > canvas.width - 4) bx = hx - bw - 14;
    if (by + bh > canvas.height - 4) by = hy - bh - 14;
    ctx.fillStyle = "rgba(0,0,0,0.78)";
    ctx.fillRect(bx, by, bw, bh);
    ctx.fillStyle = "#fff";
    for (let i = 0; i < lines.length; i++) {
      ctx.font = i === 0 ? "bold 13px sans-serif" : "13px sans-serif";
      ctx.fillText(lines[i], bx + pad, by + pad + (i + 1) * lh - 3);
    }
  }

  function handleMouseMove(e) {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const rect = canvas.getBoundingClientRect();
    const W = 1080;
    const s = W / img.naturalWidth;
    const cx = (e.clientX - rect.left) * (W / rect.width);
    const cy = (e.clientY - rect.top) * (canvas.height / rect.height);
    const THRESH = 14; // canvas px

    const frameData = trajByFrame.get(currentFrame);
    if (!frameData) { if (hoverRef.current) { hoverRef.current = null; setHoverTid(null); } return; }

    let nearestTid = null, nearestDist = Infinity;
    for (const [tid, { x, y }] of frameData.entries()) {
      const d = Math.hypot(x * s - cx, y * s - cy);
      if (d < THRESH && d < nearestDist) { nearestTid = tid; nearestDist = d; }
    }

    if (nearestTid == null) {
      if (hoverRef.current) { hoverRef.current = null; setHoverTid(null); }
      return;
    }
    const { x, y, predicted } = frameData.get(nearestTid);
    const kin = kinByFrame.get(currentFrame)?.get(nearestTid);
    const next = { tid: nearestTid, x, y, predicted, speed: kin?.speed ?? null, accel: kin?.acceleration ?? null, heading: kin?.heading_deg ?? null };
    if (hoverRef.current?.tid !== nearestTid) {
      hoverRef.current = next;
      setHoverTid(nearestTid);
    } else {
      hoverRef.current = next;
    }
  }

  function handleMouseLeave() {
    if (hoverRef.current) { hoverRef.current = null; setHoverTid(null); }
  }

  function getSummary() {
    return Array.from(kinData.entries()).map(([tid, pts]) => {
      const speeds = pts.map((p) => p.speed).filter((v) => v != null);
      const meanSpd = speeds.length ? speeds.reduce((a, b) => a + b, 0) / speeds.length : null;
      const maxSpd = speeds.length ? Math.max(...speeds) : null;
      const totalDist = pts.reduce((a, p) => a + (p.displacement_px ?? 0), 0);
      return { tid, frames: pts.length, meanSpd, maxSpd, totalDist };
    }).sort((a, b) => a.tid - b.tid);
  }

  return (
    <div>
      <div style={{ position: "relative", maxWidth: 1080, margin: "0 auto" }}>
        <canvas
          ref={canvasRef}
          style={{ display: "block", width: "100%", height: "auto", borderRadius: 4, cursor: "crosshair" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />
      </div>
      {frameList.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          <button onClick={() => setFrameIdx((i) => Math.max(0, i - 100))}>−100</button>
          <button onClick={() => setFrameIdx((i) => Math.max(0, i - 10))}>−10</button>
          <button onClick={() => setFrameIdx((i) => Math.max(0, i - 1))}>−1</button>
          <span className="hint" style={{ margin: "0 4px", minWidth: 110, textAlign: "center" }}>
            Frame {frameIdx + 1} / {frameList.length}
          </span>
          <button onClick={() => setFrameIdx((i) => Math.min(frameList.length - 1, i + 1))}>+1</button>
          <button onClick={() => setFrameIdx((i) => Math.min(frameList.length - 1, i + 10))}>+10</button>
          <button onClick={() => setFrameIdx((i) => Math.min(frameList.length - 1, i + 100))}>+100</button>
        </div>
      )}
      {frameList.length > 0 && (
        <p style={{ fontSize: "8pt", color: "var(--muted)", marginTop: 4 }}>
          Hover over a subject for details. Hollow ring = gap-filled position.
        </p>
      )}
      {kinData.size > 0 && (
        <div style={{ marginTop: 16, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "9pt" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>Track</th>
                <th style={{ textAlign: "right", padding: "4px 8px" }}>Frames</th>
                <th style={{ textAlign: "right", padding: "4px 8px" }}>Mean Speed</th>
                <th style={{ textAlign: "right", padding: "4px 8px" }}>Max Speed</th>
                <th style={{ textAlign: "right", padding: "4px 8px" }}>Total Distance (px)</th>
              </tr>
            </thead>
            <tbody>
              {getSummary().map(({ tid, frames, meanSpd, maxSpd, totalDist }) => (
                <tr key={tid} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "4px 8px" }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: COLORS[tid % COLORS.length], marginRight: 6, verticalAlign: "middle" }} />
                    #{tid}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px" }}>{frames}</td>
                  <td style={{ textAlign: "right", padding: "4px 8px" }}>{meanSpd != null ? meanSpd.toFixed(2) : "—"}</td>
                  <td style={{ textAlign: "right", padding: "4px 8px" }}>{maxSpd != null ? maxSpd.toFixed(2) : "—"}</td>
                  <td style={{ textAlign: "right", padding: "4px 8px" }}>{totalDist > 0 ? totalDist.toFixed(1) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SubjectKinematicsStep({ video, experiment, experimentFps, run, busy, trajectoryFvId, selectedRunId, onComplete, onRunsChanged }) {
  const videoVersionId = video.current_version_id;
  const [kinemStep, setKinemStep] = useState({ status: "pending", message: "", progress: 0, total: 0 });
  const [outputFvId, setOutputFvId] = useState(null);

  useEffect(() => {
    if (!selectedRunId) return;
    setOutputFvId(null);
    api.runOutputFileVersionId(selectedRunId).then(setOutputFvId).catch(() => {});
  }, [selectedRunId]);

  async function runKinematics() {
    setKinemStep({ status: "running", message: "", progress: 0, total: 0 });
    setOutputFvId(null);
    try {
      const started = await api.startRun("subject-kinematics", {
        experiment_id: experiment.id,
        trajectory_file_version_id: trajectoryFvId,
        video_file_version_id: videoVersionId,
        ...(experimentFps ? { fps: experimentFps } : {}),
      });
      const finished = await api.waitForRunWithProgress(
        started.id,
        (done, total) => setKinemStep((s) => ({ ...s, progress: done, total })),
      );
      setKinemStep({ status: "done", message: "", progress: 0, total: 0 });
      const fvId = await api.runOutputFileVersionId(finished.id);
      setOutputFvId(fvId);
      onComplete();
    } catch (e) {
      if (e.message?.startsWith("401")) throw e;
      setKinemStep({ status: "failed", message: e.message, progress: 0, total: 0 });
      onRunsChanged();
    }
  }

  function StepBar({ st, label, noTopMargin }) {
    const pct = st.total > 0 ? Math.min(100, Math.round(st.progress / st.total * 100)) : null;
    const running = st.status === "running";
    const done = st.status === "done";
    const failed = st.status === "failed";
    if (!running && !done && !failed) return null;
    const barColor = failed ? "var(--error)" : running ? "#F2BD35" : "var(--success)";
    const indeterminate = running && pct == null;
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: noTopMargin ? 0 : 12 }}>
        <span className={`dot ${st.status}`} />
        <span className="step-status" style={{ fontSize: "9pt", flexShrink: 0 }}>
          {label}{running && pct != null ? ` — ${pct}%` : ` — ${st.status}`}
        </span>
        {st.message && <span className="step-err" style={{ flexShrink: 0 }}> — {st.message}</span>}
        {(running || done) && (
          <div style={{ flex: 1, minWidth: 40, height: 10, border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 3, background: barColor,
              width: indeterminate ? "35%" : `${done ? 100 : (pct ?? 0)}%`,
              transition: indeterminate ? undefined : "width 0.35s ease",
              animation: indeterminate ? "progress-slide 1.4s linear infinite" : undefined,
            }} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="step-card" style={{ marginTop: 20, marginBottom: 16 }}>
        {!trajectoryFvId
          ? <p className="hint">No confirmed trajectory. Go back to Step 3 and confirm trajectories.</p>
          : (
            <>
              <button
                className="primary"
                disabled={busy || kinemStep.status === "running" || kinemStep.status === "done"}
                onClick={() => run(runKinematics)}
              >
                Run Kinematics
              </button>
              <StepBar st={kinemStep} label="Subject kinematics" />
            </>
          )
        }
      </div>
      {outputFvId && (
        <div className="panel-enter step-card" style={{ marginBottom: 16 }}>
          <p className="section-label" style={{ fontSize: "9pt", marginBottom: 10 }}>Kinematics Visualization</p>
          <KinematicsViewer videoVersionId={videoVersionId} trajectoryFvId={trajectoryFvId} kinematicsFvId={outputFvId} experimentFps={experimentFps} />
        </div>
      )}
    </div>
  );
}

function CollectiveBehaviorStep({ video, experiment, lightRun, trackingRun, run, busy, onComplete, onRunsChanged }) {
  const [arenaParams, setArenaParams] = useState(null);
  const [trajectoryFvId, setTrajectoryFvId] = useState(null);
  const [stepStatus, setStepStatus] = useState("pending");
  const [cbRunId, setCbRunId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!lightRun || !trackingRun) return;
    let cancelled = false;
    Promise.all([
      api.getRun(lightRun.id),
      api.runOutputFileVersionId(trackingRun.id),
    ]).then(([lr, fvId]) => {
      if (cancelled) return;
      const p = lr.parameters;
      const omega = (360 / p.frames_per_rotation) * p.direction;
      const thetaAtFirst = Math.atan2(p.first_y - p.center_y, p.first_x - p.center_x) * (180 / Math.PI);
      setArenaParams({
        arena_center_x: p.center_x,
        arena_center_y: p.center_y,
        arena_radius: p.radius_px,
        omega,
        theta_light_0: thetaAtFirst - omega * p.first_frame,
        fps: lr.runtime_info?.source_fps ?? null,
      });
      setTrajectoryFvId(fvId);
    }).catch((e) => { if (!cancelled) setError("Cannot load parameters: " + e.message); });
    return () => { cancelled = true; };
  }, [lightRun?.id, trackingRun?.id]);

  async function runAnalysis() {
    setStepStatus("running"); setError("");
    try {
      const body = {
        experiment_id: experiment.id,
        trajectory_file_version_id: trajectoryFvId,
        arena_center_x: arenaParams.arena_center_x,
        arena_center_y: arenaParams.arena_center_y,
        arena_radius: arenaParams.arena_radius,
        stimulus: { omega: arenaParams.omega, theta_light_0: arenaParams.theta_light_0 },
        ...(arenaParams.fps ? { fps: arenaParams.fps } : {}),
        ...(video?.current_version_id ? { video_file_version_id: video.current_version_id } : {}),
      };
      const started = await api.startRun("collective-behavior", body);
      await api.waitForRun(started.id);
      setStepStatus("done");
      setCbRunId(started.id);
      onComplete();
    } catch (e) {
      setStepStatus("failed");
      setError(e.message);
      onRunsChanged();
    }
  }

  return (
    <div className="analysis-wizard">
      <p className="section-label" style={{ marginBottom: 8 }}>Step 3 — Collective behavior analysis</p>
      {!arenaParams && !error && <p className="hint">Loading arena parameters…</p>}
      {arenaParams && (
        <p className="hint">
          Arena center ({arenaParams.arena_center_x.toFixed(1)}, {arenaParams.arena_center_y.toFixed(1)}),
          radius {arenaParams.arena_radius.toFixed(1)} px.
          Stimulus {Math.abs(arenaParams.omega).toFixed(4)} deg/frame
          {arenaParams.omega > 0 ? " CW" : " CCW"}.
        </p>
      )}
      <div className="row">
        <button
          className="primary"
          disabled={busy || !arenaParams || !trajectoryFvId || stepStatus === "running" || stepStatus === "done"}
          onClick={() => run(runAnalysis)}
        >
          Run collective behavior analysis
        </button>
        <span className={`dot ${stepStatus}`} />
        <span className="step-status">{stepStatus}</span>
        {arenaParams && !trajectoryFvId && <span className="hint">Waiting for trajectory output…</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {cbRunId && <CbResultsDashboard runIds={[{ label: "Results", id: cbRunId }]} videoNames={{ single: video.logical_name }} />}
    </div>
  );
}
