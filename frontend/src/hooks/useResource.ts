import { useEffect, useRef, useState, type DependencyList } from 'react';
import { isAborted } from '../api/client';

export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>, dependencies: DependencyList) {
  const currentLoader = useRef(loader);
  currentLoader.current = loader;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: unknown }>({ data: null, loading: true, error: null });
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, loading: true, error: null });
    currentLoader.current(controller.signal).then((data) => {
      if (!controller.signal.aborted) setState({ data, loading: false, error: null });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted && !isAborted(error)) setState({ data: null, loading: false, error });
    });
    return () => controller.abort();
  }, [...dependencies, attempt]);
  return { ...state, reload: () => setAttempt((value) => value + 1) };
}
