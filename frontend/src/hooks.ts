import { useCallback, useEffect, useRef, useState } from "react";

/** Load data; optionally re-poll every `interval` ms while `shouldPoll(data)` is true. */
export function useData<T>(load: () => Promise<T>, deps: unknown[], interval = 0, shouldPoll?: (d: T) => boolean) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<number>();
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const d = await load();
      if (!alive.current) return;
      setData(d);
      setError(null);
      if (interval && (!shouldPoll || shouldPoll(d))) {
        timer.current = window.setTimeout(refresh, interval);
      }
    } catch (e) {
      if (alive.current) setError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    alive.current = true;
    setLoading(true);
    refresh();
    return () => {
      alive.current = false;
      window.clearTimeout(timer.current);
    };
  }, [refresh]);

  return { data, error, loading, refresh };
}

import { api, type ServerConfig } from "./api";

let cached: Promise<ServerConfig> | null = null;
/** Server configuration (public mode, upload limit); null while loading. */
export function useServerConfig(): ServerConfig | null {
  const [cfg, setCfg] = useState<ServerConfig | null>(null);
  useEffect(() => {
    cached ??= api.config().catch(() => ({ public: false, max_upload_mb: 0, run_ttl_hours: 0 }));
    cached.then(setCfg);
  }, []);
  return cfg;
}
