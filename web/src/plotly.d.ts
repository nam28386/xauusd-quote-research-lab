declare module "plotly.js-cartesian-dist-min" {
  type PlotNode = HTMLElement & {on: (name: string, callback: (event: {points: {customdata: number | null}[]}) => void) => void};
  const plotly: {
    newPlot(node: HTMLElement, traces: object[], layout: object, config: object): Promise<PlotNode>;
    purge(node: HTMLElement): void;
  };
  export default plotly;
}
