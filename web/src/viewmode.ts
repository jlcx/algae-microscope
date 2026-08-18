/** Interface both views implement; main.ts animates shared node positions
 * toward the active view's targets, so switching views transitions (§5.3). */

import type { Position } from './state.ts';
import type { RenderStyle } from './render.ts';

export interface ViewMode {
  /** Called when the view becomes active (seed continuity from current
   * positions) and when the neighborhood/filters change. */
  refresh(): void;
  /** Desired screen position per visible node, recomputed each frame. */
  targets(width: number, height: number): Map<string, Position>;
  drawUnder(ctx: CanvasRenderingContext2D, width: number, height: number): void;
  drawOver(ctx: CanvasRenderingContext2D, width: number, height: number): void;
  /** View-specific hover target (e.g. temporal event ticks): tooltip lines
   * for the decoration under the cursor, or null. */
  tooltipAt?(x: number, y: number): string[] | null;
  renderStyle(): RenderStyle;
  onWheel(e: WheelEvent, x: number, y: number): void;
  /** Returns true if the view claims the drag (e.g. node drag in graph). */
  onDragStart(x: number, y: number, nodeId: string | null): boolean;
  onDragMove(dx: number, dy: number, x: number, y: number): void;
  onDragEnd(): void;
}
