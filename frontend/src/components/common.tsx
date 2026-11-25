import type { ReactNode } from "react";
import logoUrl from "../assets/logo.svg";
import type { RunState, Status } from "../types";

export const Logo = ({ size = 34 }: { size?: number }) => <img src={logoUrl} width={size} height={size} alt="NGSentinel" />;

export const StatusChip = ({ status, big }: { status: Status | null | undefined; big?: boolean }) =>
  status ? <span className={`chip ${status === "N/A" ? "NA" : status}${big ? " big" : ""}`}>{status}</span> : <span className="muted">—</span>;

export const StateChip = ({ state }: { state: RunState }) => <span className={`chip ${state}`}>{state.toUpperCase()}</span>;

export const Kpi = ({ label, value, sub, color }: { label: string; value: ReactNode; sub?: ReactNode; color?: string }) => (
  <div className="card kpi">
    <div className="label">{label}</div>
    <div className="value" style={color ? { color } : undefined}>
      {value}
    </div>
    {sub && <div className="sub">{sub}</div>}
  </div>
);

export const PageHead = ({ eyebrow, title, children }: { eyebrow: string; title: ReactNode; children?: ReactNode }) => (
  <div className="page-head">
    <div>
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
    </div>
    <div className="row">{children}</div>
  </div>
);

export const ErrorBox = ({ error }: { error: unknown }) =>
  error ? <div className="alert err">{error instanceof Error ? error.message : String(error)}</div> : null;
