/** Side panel: node/edge inspection, witness lists and set operations
 * (§4.1), expand/hide/pin actions. */

import type { AppState } from './state.ts';
import type { NEdge } from './types.ts';
import { CATEGORY_COLORS } from './render.ts';
import { DEFAULT_POLICY, selectAnchor, withPriority } from './temporal/index.ts';

export interface PanelActions {
  expand(qid: string): void;
}

function el(tag: string, cls = '', text = ''): HTMLElement {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text) node.textContent = text;
  return node;
}

export class Panel {
  constructor(
    private root: HTMLElement,
    private state: AppState,
    private actions: PanelActions,
  ) {
    state.addEventListener('change', () => this.render());
    this.render();
  }

  private label(qid: string): string {
    return this.state.nodes.get(qid)?.label ?? qid;
  }

  private witnessChips(container: HTMLElement, langs: string[]): void {
    const wrap = el('div', 'chips');
    for (const lang of langs) {
      const chip = el('button', 'chip'
        + (this.state.witnessFilter === lang ? ' active' : ''), lang);
      chip.title = `show only edges witnessed by ${lang}`;
      chip.onclick = () => {
        this.state.witnessFilter =
          this.state.witnessFilter === lang ? '' : lang;
        this.state.emit();
      };
      wrap.appendChild(chip);
    }
    container.appendChild(wrap);
  }

  private renderEdge(edge: NEdge): void {
    const root = this.root;
    root.appendChild(el('h3', '',
      `${this.label(edge.src)} ${edge.kind === 'typed' ? '→' : '↔'} ${this.label(edge.dst)}`));

    if (edge.kind === 'typed') {
      const category =
        this.state.clientConfig?.prop_categories?.[edge.prop ?? ''] ?? 'other';
      const propLabel =
        this.state.clientConfig?.cg_rels?.[edge.prop ?? ''] ?? '';
      const row = el('div', 'kv');
      const swatch = el('span', 'swatch');
      swatch.style.background = CATEGORY_COLORS[category] ?? '#9ca3af';
      row.appendChild(swatch);
      row.appendChild(el('span', '',
        ` ${edge.prop}${propLabel ? ` (${propLabel})` : ''} · ${category}`));
      root.appendChild(row);
      return;
    }

    root.appendChild(el('div', 'kv',
      `wp_count ${edge.wp_count}`
      + (edge.effective_count != null
         ? ` · effective ${(+edge.effective_count).toFixed(1)}` : '')));
    if (edge.wp_not_wd) {
      root.appendChild(el('div', 'badge-wpnotwd',
        'WP-not-WD: linked across Wikipedias, no Wikidata statement'));
    }
    if (edge.langs) {
      root.appendChild(el('div', 'kv dim',
        `${edge.langs.length} witnessing editions`));
      this.witnessChips(root, edge.langs);
    }

    const compare = this.state.compareEdge
      ? this.state.edges.get(this.state.compareEdge) : null;
    if (compare && compare.kind === 'consensus' && edge.langs
        && compare.langs) {
      // set operations across the selected edge pair (§4.1)
      const a = new Set(edge.langs);
      const b = new Set(compare.langs);
      root.appendChild(el('h4', '',
        `vs ${this.label(compare.src)} ↔ ${this.label(compare.dst)}`));
      const shared = [...a].filter(l => b.has(l)).sort();
      const onlyA = [...a].filter(l => !b.has(l)).sort();
      const onlyB = [...b].filter(l => !a.has(l)).sort();
      root.appendChild(el('div', 'kv', `shared (${shared.length}): ${shared.join(' ') || '—'}`));
      root.appendChild(el('div', 'kv', `only this (${onlyA.length}): ${onlyA.join(' ') || '—'}`));
      root.appendChild(el('div', 'kv', `only other (${onlyB.length}): ${onlyB.join(' ') || '—'}`));
    } else {
      root.appendChild(el('div', 'hint',
        'shift-click another consensus edge to compare witnesses'));
    }
  }

  private renderNode(qid: string): void {
    const node = this.state.nodes.get(qid);
    if (!node) return;
    const root = this.root;
    root.appendChild(el('h3', '', node.label));
    const link = el('a', 'kv', qid) as HTMLAnchorElement;
    link.href = `https://www.wikidata.org/wiki/${qid}`;
    link.target = '_blank';
    root.appendChild(link);
    root.appendChild(el('div', 'kv',
      `${node.seed ? 'seed · ' : `hop ${node.hop} · `}`
      + (node.wp_count != null ? `wp_count ${node.wp_count}` : 'no coverage data')));

    const actions = el('div', 'actions');
    const expandBtn = el('button', 'btn', 'expand +1 hop');
    expandBtn.onclick = () => this.actions.expand(qid);
    actions.appendChild(expandBtn);
    const hideBtn = el('button', 'btn', 'hide');
    hideBtn.onclick = () => {
      this.state.hidden.add(qid);
      this.state.selection = null;
      this.state.emit();
    };
    actions.appendChild(hideBtn);
    if (this.state.pinned.has(qid)) {
      const unpinBtn = el('button', 'btn', 'unpin');
      unpinBtn.onclick = () => {
        this.state.pinned.delete(qid);
        this.state.emit();
      };
      actions.appendChild(unpinBtn);
    }
    root.appendChild(actions);

    if (node.dates.length) {
      const policy = withPriority(DEFAULT_POLICY,
        this.state.clientConfig?.temporal.anchor_priority ?? []);
      const anchor = selectAnchor(node.dates, policy);
      if (anchor) {
        root.appendChild(el('div', 'kv dim',
          `temporal anchor: ${anchor.property}`
          + (anchor.kind === 'end' ? ' (end-anchored ‹)' : '')));
        if (anchor.conflict) {
          root.appendChild(el('div', 'warn',
            `⚠ Wikidata has conflicting ${anchor.property} values at the `
            + 'same precision — the timeline position uses one of them'));
        }
      }
      root.appendChild(el('h4', '', 'date claims'));
      const list = el('div', 'dates');
      for (const d of node.dates) {
        const nested = d.source_property
          ? ` (on ${d.source_property} → ${this.label(d.source_target)})` : '';
        list.appendChild(el('div', 'kv mono',
          `${d.property} ${d.time_value} p${d.precision}${nested}`));
      }
      root.appendChild(list);
    }
  }

  render(): void {
    this.root.textContent = '';
    const sel = this.state.selection;
    if (this.state.error) {
      this.root.appendChild(el('div', 'error', this.state.error));
    }
    if (!sel) {
      const caps = this.state.capabilities;
      if (caps && !caps.consensus) {
        this.root.appendChild(el('div', 'notice',
          'API-only mode: Wikidata structure and dates only — no '
          + 'cross-language consensus or witnesses.'));
      }
      if (this.state.nodes.size) {
        this.root.appendChild(el('div', 'hint',
          `${this.state.nodes.size} nodes · ${this.state.edges.size} edges`));
        this.root.appendChild(el('div', 'hint',
          'click: select · double-click: expand · drag node: pin · '
          + 'scroll: zoom'));
        if (this.state.hidden.size) {
          const btn = el('button', 'btn',
            `unhide ${this.state.hidden.size} nodes`);
          btn.onclick = () => {
            this.state.hidden.clear();
            this.state.emit();
          };
          this.root.appendChild(btn);
        }
      } else {
        this.root.appendChild(el('div', 'hint',
          'enter seed QIDs or labels above and load a neighborhood'));
      }
      return;
    }
    if (sel.type === 'node') this.renderNode(sel.id);
    else {
      const edge = this.state.edges.get(sel.id);
      if (edge) this.renderEdge(edge);
    }
  }
}
