declare module "plotly.js-cartesian-dist-min" {
  export function newPlot(node: HTMLElement, traces: object[], layout: object, config: object): Promise<PlotNode>;
  export function purge(node: HTMLElement): void;
  type PlotNode = HTMLElement & {on: (name: string, callback: (event: {points: {customdata: number | null}[]}) => void) => void};
}
