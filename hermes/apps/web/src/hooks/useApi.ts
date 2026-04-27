"use client";
import { useState, useEffect, useCallback } from "react";

type UseApiResult<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  refetch: () => void;
};

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message ?? "Unknown error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  return { data, error, loading, refetch };
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 30000
): UseApiResult<T> {
  const result = useApi(fetcher);

  useEffect(() => {
    const id = setInterval(result.refetch, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, result.refetch]);

  return result;
}
