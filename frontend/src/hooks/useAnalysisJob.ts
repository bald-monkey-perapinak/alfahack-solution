import { useEffect, useRef, useState } from 'react';
import { AnalyticsApi, ApiError, isAborted } from '../api/client';
import type { Job } from '../api/types';
import { jobPublicationKey } from '../domain';

const storageKey = (userId: number) => `alfa.analysis-job.${userId}`;
function rememberedJob(userId: number): string | null {
  try { const id = sessionStorage.getItem(storageKey(userId)); return id && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/iu.test(id) ? id : null; } catch { return null; }
}
// Only the job identifier is remembered. Tokens, profiles and analytic content stay out of storage.
export function useAnalysisJob(api: AnalyticsApi, userId: number, completed: () => void) {
  const [id, setId] = useState<string | null>(() => rememberedJob(userId));
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  const published = useRef(new Map<string, string>());
  const completeCallback = useRef(completed);
  completeCallback.current = completed;
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    async function poll() {
      try {
        const next = await api.job(id!, controller.signal);
        if (controller.signal.aborted) return;
        setJob(next); setError(null); failures = 0;
        const key = jobPublicationKey(next);
        if (key !== (published.current.get(next.id) || '')) { published.current.set(next.id, key); completeCallback.current(); }
        if (next.status === 'pending' || next.status === 'running') timer = setTimeout(poll, 1500);
      } catch (cause) {
        if (controller.signal.aborted || isAborted(cause)) return;
        setError(cause);
        if (!(cause instanceof ApiError) || ![401, 403, 404].includes(cause.status)) {
          failures += 1;
          timer = setTimeout(poll, Math.max(cause instanceof ApiError && cause.retryAfter ? cause.retryAfter * 1000 : 0, Math.min(15000, 2000 * failures)));
        }
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, id, retry]);
  function watch(next: Job) {
    try { sessionStorage.setItem(storageKey(userId), next.id); } catch { /* Storage is optional. */ }
    setJob(next); setId(next.id); setError(null); setRetry((value) => value + 1);
  }
  function clear() {
    try { sessionStorage.removeItem(storageKey(userId)); } catch { /* Storage is optional. */ }
    setId(null); setJob(null); setError(null);
  }
  return { job, restoring: Boolean(id && !job && !error), error, watch, clear, retry: () => setRetry((value) => value + 1), active: job?.status === 'pending' || job?.status === 'running' };
}
