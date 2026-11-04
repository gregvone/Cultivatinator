import { useCallback, useEffect, useRef, useState } from "react";
import { getApi } from "./api";
export function useApi<T>(path: string, preserveOnRefresh = false) {
  const previousPath = useRef(path);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    if (!preserveOnRefresh || previousPath.current !== path) setData(null);
    previousPath.current = path;
    setError(null);
    getApi<T>(path, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error ? reason.message : "Request failed.",
          );
      });
    return () => controller.abort();
  }, [path, attempt, preserveOnRefresh]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, error, retry };
}
