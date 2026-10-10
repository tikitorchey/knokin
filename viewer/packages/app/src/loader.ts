/** Network + decode. The only module that touches fetch / createImageBitmap / ImageDecoder. */
import type { Metrics } from './metrics';

export type DecodeStrategy = 'createImageBitmap' | 'imageDecoder';
export type Premultiply = 'premultiply' | 'none' | 'default';

export interface LoaderOpt {
  strategy: DecodeStrategy;
  premultiply: Premultiply;
}

export const DEFAULT_LOADER_OPT: LoaderOpt = { strategy: 'createImageBitmap', premultiply: 'premultiply' };

/** A decoded frame ready to draw. `source` is what goes into drawImage. */
export interface Frame {
  readonly source: CanvasImageSource;
  readonly width: number;
  readonly height: number;
  close(): void;
}

export function supportsImageDecoder(): boolean {
  return typeof (globalThis as { ImageDecoder?: unknown }).ImageDecoder === 'function';
}

export function makeLoader(
  baseUrl: string, urlOf: (key: string) => string, opt: () => LoaderOpt, metrics: Metrics,
): (key: string, signal: AbortSignal) => Promise<Frame> {
  return async (key, signal) => {
    const o = opt();
    const url = new URL(urlOf(key), baseUrl).href;
    const t0 = performance.now();
    const res = await fetch(url, { signal });
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    const blob = await res.blob();
    const t1 = performance.now();
    metrics.fetchMs.add(t1 - t0);
    metrics.frameBytes.add(blob.size);
    const out = await decode(blob, o);
    metrics.decodeMs.add(performance.now() - t1);
    return out;
  };
}

async function decode(blob: Blob, o: LoaderOpt): Promise<Frame> {
  if (o.strategy === 'imageDecoder' && supportsImageDecoder()) {
    const Dec = (globalThis as unknown as { ImageDecoder: new (init: unknown) => ImageDecoderLike }).ImageDecoder;
    const dec = new Dec({ data: blob.stream(), type: blob.type || 'image/avif' });
    try {
      const { image } = await dec.decode({ frameIndex: 0 });
      return { source: image, width: image.displayWidth, height: image.displayHeight, close: () => image.close() };
    } finally {
      dec.close();
    }
  }
  const bm = await createImageBitmap(blob, { premultiplyAlpha: o.premultiply });
  return { source: bm, width: bm.width, height: bm.height, close: () => bm.close() };
}

interface ImageDecoderLike {
  decode(o: { frameIndex: number }): Promise<{ image: VideoFrame }>;
  close(): void;
}
