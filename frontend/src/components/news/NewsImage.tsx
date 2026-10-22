import { useState } from 'react';
import type { NewsImage as NewsImageData } from '../../types/news';

export function NewsImage({ image, priority = false }: { image?: NewsImageData; priority?: boolean }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`news-image${!image || failed ? ' news-image--fallback' : ''}`}>
      {image && !failed ? (
        <img src={image.url} alt={image.alt} style={{ objectPosition: image.position }}
          loading={priority ? 'eager' : 'lazy'} onError={() => setFailed(true)} />
      ) : (
        <div className="news-image__placeholder" role="img" aria-label="Новость без фотографии">
          <span aria-hidden="true">А</span><span>Новости бизнеса</span>
        </div>
      )}
    </div>
  );
}
