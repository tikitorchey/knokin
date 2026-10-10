import type { Frame } from './loader';

/** Canvas 2D view. The frame is drawn scaled to fit (contain); the canvas backing store follows DPR. */
export class CanvasView {
  private ctx: CanvasRenderingContext2D;
  checker = false;
  private last: { frame: Frame } | null = null;

  constructor(readonly canvas: HTMLCanvasElement, private readonly aspect: number) {
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('2D canvas is not available');
    this.ctx = ctx;
  }

  /** Fit the canvas into `maxW` x `maxH` CSS px, keeping the image aspect ratio. */
  resize(maxW: number, maxH: number, dpr: number): void {
    let w = maxW;
    let h = w / this.aspect;
    if (h > maxH) {
      h = maxH;
      w = h * this.aspect;
    }
    this.canvas.style.width = `${Math.floor(w)}px`;
    this.canvas.style.height = `${Math.floor(h)}px`;
    this.canvas.width = Math.max(1, Math.round(w * dpr));
    this.canvas.height = Math.max(1, Math.round(h * dpr));
    if (this.last) this.draw(this.last.frame);
  }

  draw(frame: Frame): void {
    const { ctx, canvas } = this;
    this.last = { frame };
    if (this.checker) this.paintChecker();
    else {
      ctx.fillStyle = '#1b1d22';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    ctx.drawImage(frame.source, 0, 0, canvas.width, canvas.height);
  }

  private paintChecker(): void {
    const { ctx, canvas } = this;
    const s = Math.max(8, Math.round(canvas.width / 48));
    for (let y = 0; y < canvas.height; y += s) {
      for (let x = 0; x < canvas.width; x += s) {
        ctx.fillStyle = ((x / s + y / s) & 1) === 0 ? '#3a3d45' : '#2a2c32';
        ctx.fillRect(x, y, s, s);
      }
    }
  }
}
