import type { ComposedNewsContainer } from './composeNewsContainers.ts';

export interface ContainerArrangementPolicy {
  /** Максимальный сдвиг вперёд И назад относительно входного порядка внутри раздела. */
  maxShift: number;
}

export const DEFAULT_CONTAINER_ARRANGEMENT_POLICY: Readonly<ContainerArrangementPolicy> = Object.freeze({
  maxShift: 4,
});

type Variant = ComposedNewsContainer['variant'];
const variants: readonly Variant[] = ['hero', 'duo', 'trio', 'quartet'];

interface Entry {
  container: ComposedNewsContainer;
  index: number;
}

type Counts = Record<Variant, number>;

/**
 * Нижняя граница длины серии с учётом оставшихся разделителей.
 * Например, 10 Quartet и 2 других блока требуют минимум ceil(10 / 3) = 4 подряд.
 * Продолжающаяся серия занимает часть первого доступного промежутка.
 */
function requiredRun(counts: Counts, previous: Variant, runLength: number): number {
  const total = variants.reduce((sum, variant) => sum + counts[variant], 0);
  return Math.max(runLength, ...variants.map((variant) => Math.ceil(
    (counts[variant] + (variant === previous ? runLength : 0)) / (total - counts[variant] + 1),
  )));
}

function arrangeSection(
  containers: readonly ComposedNewsContainer[],
  maxShift: number,
): ComposedNewsContainer[] {
  if (containers.length < 3 || maxShift === 0) return [...containers];
  const queues: Record<Variant, Entry[]> = { hero: [], duo: [], trio: [], quartet: [] };
  const cursors: Counts = { hero: 0, duo: 0, trio: 0, quartet: 0 };
  const counts: Counts = { hero: 0, duo: 0, trio: 0, quartet: 0 };
  containers.forEach((container, index) => {
    queues[container.variant].push({ container, index });
    counts[container.variant]++;
  });

  const result: ComposedNewsContainer[] = [];
  // Самый важный контейнер раздела не перемещаем.
  let previous = containers[0].variant;
  let runLength = 0;
  let longestRun = 0;

  function take(entry: Entry) {
    const variant = entry.container.variant;
    runLength = variant === previous ? runLength + 1 : 1;
    previous = variant;
    longestRun = Math.max(longestRun, runLength);
    cursors[variant]++;
    counts[variant]--;
    result.push(entry.container);
  }
  take(queues[previous][0]);

  while (result.length < containers.length) {
    const position = result.length;
    // Берём только голову каждой очереди: порядок важности внутри формата сохраняется.
    const heads = variants.flatMap((variant) => {
      const entry = queues[variant][cursors[variant]];
      return entry ? [entry] : [];
    });
    const earliest = heads.reduce((first, entry) => entry.index < first.index ? entry : first);
    // Не даём раннему важному контейнеру опуститься ниже своего лимита.
    if (position - earliest.index >= maxShift) {
      take(earliest);
      continue;
    }

    let best: Entry | undefined;
    let bestRequiredRun = Infinity;
    let bestNextRun = Infinity;
    for (const entry of heads) {
      if (entry.index - position > maxShift) continue;
      const variant = entry.container.variant;
      const nextRun = variant === previous ? runLength + 1 : 1;
      counts[variant]--;
      const futureRun = Math.max(longestRun, requiredRun(counts, variant, nextRun));
      counts[variant]++;

      // Сначала сохраняем разделители для остатка, потом избегаем повтора сейчас,
      // при равенстве выбираем более ранний контейнер исходного рейтинга.
      if (futureRun < bestRequiredRun
        || (futureRun === bestRequiredRun && nextRun < bestNextRun)
        || (futureRun === bestRequiredRun && nextRun === bestNextRun && entry.index < best!.index)) {
        best = entry;
        bestRequiredRun = futureRun;
        bestNextRun = nextRun;
      }
    }
    // Самый ранний оставшийся блок всегда допустим по пределу продвижения.
    take(best ?? earliest);
  }
  return result;
}

/**
 * Второй этап ПОСЛЕ composeNewsContainers: меняет только порядок готовых контейнеров.
 * Обрабатывает непрерывные разделы с одинаковыми sourceGroupId и placement независимо.
 * Первый контейнер закреплён. Внутри каждого формата порядок сохраняется.
 * Это ограниченная расстановка: разнообразие не гарантируется, если других форматов
 * нет, их недостаточно или maxShift не позволяет взять нужный разделитель.
 */
export function arrangeNewsContainers(
  containers: readonly ComposedNewsContainer[],
  options: Partial<ContainerArrangementPolicy> = {},
): ComposedNewsContainer[] {
  const maxShift = options.maxShift ?? DEFAULT_CONTAINER_ARRANGEMENT_POLICY.maxShift;
  if (!Number.isSafeInteger(maxShift) || maxShift < 0) {
    throw new RangeError('maxShift должен быть неотрицательным безопасным целым числом');
  }
  const ids = new Set<string>();
  for (const container of containers) {
    if (ids.has(container.id)) throw new Error(`Повторяющийся id контейнера: ${container.id}`);
    ids.add(container.id);
  }

  const result: ComposedNewsContainer[] = [];
  let start = 0;
  while (start < containers.length) {
    const first = containers[start];
    let end = start + 1;
    while (end < containers.length && containers[end].placement === first.placement
      && containers[end].sourceGroupId === first.sourceGroupId) end++;
    result.push(...arrangeSection(containers.slice(start, end), maxShift));
    start = end;
  }
  return result;
}
