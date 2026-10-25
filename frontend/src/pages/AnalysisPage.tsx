import { Button } from '@alfalab/core-components/button';
import { BarChartMIcon } from '@alfalab/icons-glyph/BarChartMIcon';

/** Навигационный экран: полноценные отчёты появятся после подключения сервиса анализа. */
export function AnalysisPage() {
  return (
    <main className="workspace">
      <div className="page-heading"><div><h1>Анализ</h1><p className="page-description">Аналитические отчёты и влияние событий на ваш бизнес</p></div></div>
      <section className="analysis-placeholder" aria-labelledby="analysis-placeholder-title">
        <BarChartMIcon aria-hidden="true" />
        <h2 id="analysis-placeholder-title">Раздел анализа готовится</h2>
        <p>Персональные отчёты появятся после подключения сервиса анализа. Сейчас в карточках новостей доступен демонстрационный предпросмотр.</p>
        <Button href="#/" view="secondary" size={40}>Перейти к новостям</Button>
      </section>
    </main>
  );
}
