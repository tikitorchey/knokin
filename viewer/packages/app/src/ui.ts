/** Declarative debug controls. Each control reads/writes through get/set, so state lives in one place. */

export type Control =
  | { kind: 'range'; label: string; min: number; max: number; step: number; get: () => number; set: (v: number) => void }
  | { kind: 'select'; label: string; options: string[]; get: () => string; set: (v: string) => void }
  | { kind: 'check'; label: string; get: () => boolean; set: (v: boolean) => void };

export function buildPanel(host: HTMLElement, controls: Control[]): void {
  host.textContent = '';
  for (const c of controls) {
    const row = document.createElement('label');
    row.className = 'row';
    const name = document.createElement('span');
    name.textContent = c.label;
    row.append(name);
    if (c.kind === 'range') {
      const input = document.createElement('input');
      input.type = 'range';
      input.min = String(c.min);
      input.max = String(c.max);
      input.step = String(c.step);
      input.value = String(c.get());
      const val = document.createElement('output');
      val.textContent = input.value;
      input.addEventListener('input', () => {
        c.set(Number(input.value));
        val.textContent = input.value;
      });
      row.append(input, val);
    } else if (c.kind === 'select') {
      const sel = document.createElement('select');
      for (const o of c.options) sel.add(new Option(o, o));
      sel.value = c.get();
      sel.addEventListener('change', () => c.set(sel.value));
      row.append(sel);
    } else {
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = c.get();
      cb.addEventListener('change', () => c.set(cb.checked));
      row.append(cb);
    }
    host.append(row);
  }
}
