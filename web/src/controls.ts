/** Toolbar: seed entry with label search, expansion parameters, fetch-time
 * filters (§3.3), display toggles (§4.2, §5.1), view switching (§5.3).
 * Capability-driven adaptation (§2.1): witness/consensus controls disable
 * themselves when the backend lacks them. */

import { api } from './api.ts';
import type { AppState } from './state.ts';
import type { SearchHit } from './types.ts';

export interface ControlActions {
  load(): void;
}

function make<K extends keyof HTMLElementTagNameMap>(
  tag: K, attrs: Record<string, string> = {}, text = '',
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  if (text) node.textContent = text;
  return node;
}

function labeled(text: string, child: HTMLElement): HTMLElement {
  const wrap = make('label', { class: 'ctl' });
  wrap.appendChild(document.createTextNode(text));
  wrap.appendChild(child);
  return wrap;
}

export class Controls {
  private seedInput = make('input', {
    placeholder: 'seeds: Q42, Douglas Adams, …',
    class: 'seeds', autocomplete: 'off', spellcheck: 'false',
  });
  private suggestBox = make('div', { class: 'suggest' });
  private hits: SearchHit[] = [];
  private highlight = -1;
  private searchSeq = 0;
  private status = make('span', { class: 'status' });

  constructor(
    private root: HTMLElement,
    private state: AppState,
    private actions: ControlActions,
  ) {
    this.build();
    state.addEventListener('change', () => this.sync());
  }

  private build(): void {
    const s = this.state;
    const root = this.root;

    root.appendChild(make('span', { class: 'brand' }, 'algae-microscope'));

    this.seedInput.value = s.seeds.join(', ');
    let debounce = 0;
    this.seedInput.addEventListener('input', () => {
      window.clearTimeout(debounce);
      const raw = this.seedInput.value.split(',').pop()?.trim() ?? '';
      if (raw.length < 2 || /^Q\d*$/i.test(raw)) {
        this.closeSuggest();
        return;
      }
      debounce = window.setTimeout(() => this.fetchSuggestions(raw), 200);
    });
    this.seedInput.addEventListener('keydown', e => {
      if (this.hits.length && this.suggestBox.childElementCount) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const step = e.key === 'ArrowDown' ? 1 : -1;
          this.highlight = (this.highlight + step + this.hits.length)
            % this.hits.length;
          this.renderSuggestions();
          return;
        }
        if (e.key === 'Escape') {
          this.closeSuggest();
          return;
        }
        if (e.key === 'Enter' && this.highlight >= 0) {
          e.preventDefault();
          this.pickSuggestion(this.hits[this.highlight]);
          return;
        }
      }
      if (e.key === 'Enter') this.submit();
    });
    this.seedInput.addEventListener('blur', () => {
      // delay so a mousedown on a suggestion row still lands
      window.setTimeout(() => this.closeSuggest(), 150);
    });
    const seedWrap = make('span', { class: 'seedwrap' });
    seedWrap.appendChild(this.seedInput);
    seedWrap.appendChild(this.suggestBox);
    root.appendChild(seedWrap);

    const hops = make('input', { type: 'number', min: '1', max: '3', class: 'num' });
    hops.value = String(s.hops);
    hops.onchange = () => { s.hops = +hops.value; };
    root.appendChild(labeled('hops', hops));

    const budget = make('input', { type: 'number', min: '5', max: '1000', step: '5', class: 'num wide' });
    budget.value = String(s.budget);
    budget.onchange = () => { s.budget = +budget.value; };
    root.appendChild(labeled('budget', budget));

    const minCons = make('input', { type: 'number', min: '0', class: 'num' });
    minCons.value = String(s.filters.min_consensus ?? 0);
    minCons.onchange = () => { s.filters.min_consensus = +minCons.value; };
    root.appendChild(labeled('min wp', minCons));

    const props = make('select', {});
    for (const value of ['all', 'cg']) {
      props.appendChild(make('option', { value }, value === 'cg' ? 'cg rels' : 'all props'));
    }
    props.value = typeof s.filters.props === 'string' ? s.filters.props : 'all';
    props.onchange = () => { s.filters.props = props.value; };
    root.appendChild(labeled('props', props));

    const direction = make('select', {});
    for (const value of ['both', 'out', 'in']) {
      direction.appendChild(make('option', { value }, value));
    }
    direction.value = s.filters.direction ?? 'both';
    direction.onchange = () => {
      s.filters.direction = direction.value as 'both' | 'out' | 'in';
    };
    root.appendChild(labeled('dir', direction));

    const load = make('button', { class: 'btn primary' }, 'load');
    load.onclick = () => this.submit();
    root.appendChild(load);

    root.appendChild(make('span', { class: 'spacer' }));

    // view toggle (§5.3): one neighborhood, two projections
    const viewWrap = make('span', { class: 'viewtoggle' });
    for (const view of ['graph', 'temporal'] as const) {
      const btn = make('button', { class: 'btn toggle', 'data-view': view }, view);
      btn.onclick = () => {
        s.view = view;
        s.emit();
        s.emit('viewchange');
      };
      viewWrap.appendChild(btn);
    }
    root.appendChild(viewWrap);

    const row2 = make('div', { class: 'row2' });

    const consensus = make('input', { type: 'checkbox', 'data-role': 'consensus' });
    consensus.checked = s.showConsensus;
    consensus.onchange = () => { s.showConsensus = consensus.checked; s.emit(); };
    row2.appendChild(labeled('consensus', consensus));

    const typed = make('input', { type: 'checkbox' });
    typed.checked = s.showTyped;
    typed.onchange = () => { s.showTyped = typed.checked; s.emit(); };
    row2.appendChild(labeled('typed', typed));

    const effective = make('input', { type: 'checkbox', 'data-role': 'witness' });
    effective.checked = s.useEffective;
    effective.onchange = () => { s.useEffective = effective.checked; s.emit(); };
    row2.appendChild(labeled('effective counts', effective));

    const witnessFilter = make('input', {
      placeholder: 'witness lang', class: 'lang', 'data-role': 'witness',
    });
    witnessFilter.onchange = () => {
      s.witnessFilter = witnessFilter.value.trim();
      s.emit();
    };
    row2.appendChild(labeled('witnessed by', witnessFilter));

    const minStrength = make('input', {
      type: 'range', min: '0', max: '50', step: '1', 'data-role': 'consensus',
    });
    minStrength.value = String(s.minStrength);
    minStrength.oninput = () => { s.minStrength = +minStrength.value; s.emit(); };
    row2.appendChild(labeled('min strength', minStrength));

    const sizeBy = make('select', {});
    for (const value of ['wp_count', 'degree', 'uniform']) {
      sizeBy.appendChild(make('option', { value }, value));
    }
    sizeBy.value = s.sizeBy;
    sizeBy.onchange = () => {
      s.sizeBy = sizeBy.value as AppState['sizeBy'];
      s.emit();
    };
    row2.appendChild(labeled('size by', sizeBy));

    const undated = make('select', { 'data-role': 'temporal' });
    for (const value of ['margin', 'infer']) {
      undated.appendChild(make('option', { value }, value));
    }
    undated.value = s.undatedMode;
    undated.onchange = () => {
      s.undatedMode = undated.value as 'margin' | 'infer';
      s.emit();
    };
    row2.appendChild(labeled('undated', undated));

    const events = make('input', { type: 'checkbox', 'data-role': 'temporal' });
    events.checked = s.showAllEvents;
    events.onchange = () => { s.showAllEvents = events.checked; s.emit(); };
    row2.appendChild(labeled('event ticks', events));

    row2.appendChild(this.status);
    root.appendChild(row2);
  }

  private async fetchSuggestions(query: string): Promise<void> {
    const seq = ++this.searchSeq;
    try {
      const hits = await api.search(query);
      if (seq !== this.searchSeq) return; // a newer keystroke superseded us
      this.hits = hits;
      this.highlight = hits.length ? 0 : -1;
      this.renderSuggestions();
    } catch (err) {
      if (seq !== this.searchSeq) return;
      this.hits = [];
      this.highlight = -1;
      this.suggestBox.textContent = '';
      const row = make('div', { class: 'suggest-row disabled' },
        String(err instanceof Error ? err.message : err));
      this.suggestBox.appendChild(row);
      this.suggestBox.classList.add('open');
    }
  }

  private renderSuggestions(): void {
    this.suggestBox.textContent = '';
    if (!this.hits.length) {
      this.suggestBox.classList.remove('open');
      return;
    }
    this.hits.forEach((hit, index) => {
      const row = make('div', {
        class: 'suggest-row' + (index === this.highlight ? ' hl' : ''),
      });
      row.appendChild(make('span', { class: 's-label' }, hit.label));
      row.appendChild(make('span', { class: 's-qid' }, hit.qid));
      if (hit.description) {
        row.appendChild(make('span', { class: 's-desc' }, hit.description));
      }
      // mousedown fires before the input's blur handler closes the box
      row.addEventListener('mousedown', e => {
        e.preventDefault();
        this.pickSuggestion(hit);
      });
      this.suggestBox.appendChild(row);
    });
    this.suggestBox.classList.add('open');
  }

  private pickSuggestion(hit: SearchHit): void {
    // replace the segment being typed with the exact QID (labels are
    // ambiguous; the chosen entity should not depend on server tie-breaks)
    const parts = this.seedInput.value.split(',').map(part => part.trim());
    parts[parts.length - 1] = hit.qid;
    this.seedInput.value = parts.filter(Boolean).join(', ');
    this.seedInput.title = this.seedInput.value;
    this.closeSuggest();
    this.seedInput.focus();
  }

  private closeSuggest(): void {
    this.hits = [];
    this.highlight = -1;
    this.suggestBox.textContent = '';
    this.suggestBox.classList.remove('open');
  }

  private submit(): void {
    this.state.seeds = this.seedInput.value
      .split(',').map(part => part.trim()).filter(Boolean);
    if (this.state.seeds.length) this.actions.load();
  }

  sync(): void {
    const s = this.state;
    this.status.textContent = s.busy ? 'loading…'
      : s.error ? s.error
      : s.capabilities && !s.capabilities.consensus
        ? 'API-only: Wikidata structure + dates' : '';
    this.status.classList.toggle('err', !!s.error);
    for (const btn of this.root.querySelectorAll<HTMLButtonElement>('[data-view]')) {
      btn.classList.toggle('active', btn.dataset.view === s.view);
    }
    // capability-driven adaptation (§2.1): no witness legend in API-only mode
    const caps = s.capabilities;
    for (const node of this.root.querySelectorAll<HTMLInputElement>('[data-role="witness"]')) {
      node.disabled = !caps?.witnesses;
      node.closest('label')?.classList.toggle('disabled', !caps?.witnesses);
    }
    for (const node of this.root.querySelectorAll<HTMLInputElement>('[data-role="consensus"]')) {
      node.disabled = !caps?.consensus;
      node.closest('label')?.classList.toggle('disabled', !caps?.consensus);
    }
    for (const node of this.root.querySelectorAll<HTMLElement>('[data-role="temporal"]')) {
      node.closest('label')!.style.display =
        s.view === 'temporal' ? '' : 'none';
    }
  }
}
