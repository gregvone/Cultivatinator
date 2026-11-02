import { useEffect, useState } from "react";
import { getApi } from "./api";
export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
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
  }, [path, attempt]);
  return { data, error, retry: () => setAttempt((n) => n + 1) };
}
