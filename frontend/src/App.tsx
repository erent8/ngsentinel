import { useEffect } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Logo } from "./components/common";
import { LIVE_URL, REPO_URL, STATIC } from "./config";
import Dashboard from "./pages/Dashboard";
import NewAnalysis from "./pages/NewAnalysis";
import RunDetailPage from "./pages/RunDetail";
import Runs from "./pages/Runs";
import Rules from "./pages/Rules";
import Tools from "./pages/Tools";
import TryIt from "./pages/TryIt";

const NAV = [
  { to: "/", label: "Dashboard", icon: "◈", end: true },
  { to: "/new", label: "New analysis", icon: "＋" },
  { to: "/runs", label: "Analysis history", icon: "≡" },
  { to: "/rules", label: "QC rules", icon: "⚖" },
  { to: "/tools", label: "Tools", icon: "⚙" },
];

export default function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0); // statement body: scrollTo returns a Promise in newer browsers, which React would treat as a cleanup function
  }, [pathname]);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo size={36} />
          <div>
            <b>
              <span>NGS</span>entinel
            </b>
            <small>NGS Quality Control Platform</small>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              <span style={{ width: 18, textAlign: "center", opacity: 0.8 }}>{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="foot">
          v1.0.0 · research use only
          <br />
          not for clinical diagnosis
        </div>
      </aside>
      <main className="content">
        {STATIC && (
          <div className="showcase-banner">
            <div>
              <b>Interactive showcase</b> — real results from a public <i>E. coli</i> sequencing run (ENA SRR2589044) and a clearly labelled synthetic demo,
              produced by NGSentinel with FastQC, fastp and MultiQC. Read-only: browse every chart, rule and report.
            </div>
            <div className="row">
              {LIVE_URL && (
                <a className="btn sm primary" href={LIVE_URL} target="_blank" rel="noreferrer">
                  Live app
                </a>
              )}
              {REPO_URL && (
                <a className="btn sm" href={REPO_URL} target="_blank" rel="noreferrer">
                  Source code
                </a>
              )}
            </div>
          </div>
        )}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={STATIC ? <TryIt /> : <NewAnalysis />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:id" element={<RunDetailPage />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/tools" element={<Tools />} />
          <Route path="*" element={<div className="empty">Page not found.</div>} />
        </Routes>
      </main>
    </div>
  );
}
