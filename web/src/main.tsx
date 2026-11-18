import React, {useEffect, useRef, useState} from "react";
import {createRoot} from "react-dom/client";
import {contrasts, display, heatmap, intervals, lookup, metrics, params, plotNumber, widths} from "./model";
import type {Metric} from "./model";
import type {Configuration, Counterexample, Data, Dataset, Evidence, Family, Page, Query, Quote, Row} from "./types";
import "./style.css";

const routes = [
  ["overview", "Research Overview", "Research observatory"],
  ["sampling", "Sampling Sensitivity", "Sampling sensitivity explorer"],
  ["factorial", "Factorial Stress", "Factorial stress explorer"],
  ["tail", "Tail Decomposition", "Tail decomposition explorer"],
  ["atlas", "Identifiability Atlas", "Identifiability atlas"],
  ["evidence", "Evidence & Provenance", "Evidence & provenance inspector"],
] as const;
type Route = typeof routes[number][0];
const sections = {p1: "P1", p2: "P2", p21: "P2.1"};
type Packet = {name: string; sha256: string; packet: Evidence};

function api<T>(path: string) {
  const [value, setValue] = useState<{path: string; result?: T; error?: string}>();
  useEffect(() => {
    const controller = new AbortController();
    fetch(path, {signal: controller.signal}).then(async response => {
      if (!response.ok) throw new Error((await response.json()).error || response.statusText);
      return response.json() as Promise<T>;
    }).then(result => setValue({path, result})).catch(error => {
      if (!controller.signal.aborted) setValue({path, error: String(error.message ?? error)});
    });
    return () => controller.abort();
  }, [path]);
  return value?.path === path ? value : undefined;
}

function Loading({error}: {error?: string}) {
  return <p className={error ? "notice error" : "notice"} role={error ? "alert" : "status"}>{error || "Loading verified data…"}</p>;
}

function Select({label, value, options, change}: {label: string; value: string; options: (number|string)[]; change: (next: string) => void}) {
  return <label>{label}<select value={value} onChange={event => change(event.target.value)}>
    {options.map(item => <option key={item} value={item}>{item === "" ? "All" : item}</option>)}
  </select></label>;
}

function Plot({traces, axes, onSelect, label}: {
  traces: object[]; axes: object; onSelect?: (ordinal: number) => void; label: string;
}) {
  const node = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const chart = node.current!;
    let active = true;
    let dispose: (() => void) | undefined;
    import("plotly.js-cartesian-dist-min").then(plotly => {
      if (!active) return;
      dispose = () => plotly.purge(chart);
      return plotly.newPlot(chart, traces, {
        height: 355, margin: {l: 71, r: 25, t: 24, b: 62}, paper_bgcolor: "#fff",
        plot_bgcolor: "#fff", font: {family: "system-ui, sans-serif", color: "#344358", size: 13},
        ...axes,
      }, {responsive: true, displaylogo: false, displayModeBar: false}).then(ready => {
        if (!active) return;
        ready.on("plotly_click", (event) => {
          const selected = event.points[0]?.customdata;
          if (typeof selected === "number") onSelect?.(selected);
        });
      });
    }).catch(cause => {if (active) setError(String(cause));});
    return () => {active = false; dispose?.();};
  }, [traces, axes, onSelect]);
  return <><div ref={node} className="plot" role="img" aria-label={label}/>{error && <Loading error={error}/>}</>;
}

function FigureNote({page, title, unit, support, version, limit}: {
  page: Page<unknown>; title: string; unit: string; support: string; version: string; limit: string;
}) {
  return <figcaption>
    <div><b>{title}</b><span className="tag">Synthetic</span></div>
    <p>{page.source_experiment} · {version} · {unit} · {support}</p>
    <p>Filters {Object.entries(page.filters).map(([key, value]) => `${key}=${value}`).join(" · ") || "none"}</p>
    <p>{limit}</p>
  </figcaption>;
}

function Exact({value, reason}: {value: string|null; reason?: string|null}) {
  const text = display(value, reason);
  return <span className={value === null ? "unavailable" : "exact"} title={text}>
    {text.length > 24 && value !== null ? <details><summary>{text.slice(0, 16)}…</summary><code>{text}</code></details> : text}
  </span>;
}

function Overview({datasets, navigate}: {datasets: Dataset[]; navigate: (page: Route) => void}) {
  return <>
    <div className="hero"><div className="eyebrow"><span></span> Offline research workspace</div>
      <h2>Inspect what survives<br/>the sampling process.</h2>
      <p>Explore synthetic quote experiments, compare measurement support, and trace every result to its verified artifact.</p>
      <button className="primary" onClick={() => navigate("factorial")}>Explore factorial stress <span>↗</span></button>
    </div>
    <div className="dataset-grid">{datasets.map(dataset => <article className="panel dataset" key={dataset.id}>
      <span className="tag">{sections[dataset.id]}</span><h3>{dataset.experiment}</h3>
      <p>{dataset.row_count?.toLocaleString("en-US") ?? "Golden replay"}{dataset.row_count !== null && " result rows"}</p>
      <small>{dataset.verification.replaceAll("-", " ")} · {Object.keys(dataset.artifacts).length} artifacts</small>
      <button className="link" onClick={() => navigate(dataset.id === "p1" ? "evidence" : dataset.id === "p2" ? "sampling" : "factorial")}>Inspect dataset ↗</button>
    </article>)}</div>
    <section className="panel boundary"><h3>Interpretation boundaries</h3>
      <p>These artifacts describe deterministic synthetic scenarios. The factorial cells are configurations, and the as-of tolerance is a snapshot age cap. The evidence leaves real tick completeness, broker independence, execution costs and actor identity unknown.</p>
    </section>
  </>;
}

function ConfigurationTable({rows, metric, session, select}: {
  rows: Row<Configuration>[]; metric: Metric; session: string; select: (ordinal: number) => void;
}) {
  return <div className="table-wrap"><table>
    <thead><tr><th>Configuration</th><th>Poll (ms)</th><th>Width (ms)</th><th>{metrics[metric].label}</th><th>Detected / truth</th><th>Right-censored</th><th>Broker coverage</th></tr></thead>
    <tbody>{rows.map(({ordinal, data}) => {
      const stream = data.streams.find(item => item.session_id === session);
      const stat = lookup(data, stream, metric);
      return <tr key={ordinal}><td><button className="link" onClick={() => select(ordinal)}>Row {ordinal} ↗</button></td><td>{data.interval_ms}</td>
        <td>{data.duration_ms ?? "—"}</td><td><Exact value={stat.value} reason={stat.reason}/></td>
        <td>{stream ? `${stream.events.detected} / ${stream.events.eligible_truth}` : "Unavailable"}</td>
        <td>{stream?.events.sample_right_censored ?? "—"}</td><td><Exact value={data.broker.coverage}/></td></tr>;
    })}</tbody>
  </table></div>;
}

function Detail({table, ordinal, close}: {table: string; ordinal: number; close: () => void}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.scrollIntoView({block: "start"});
    panel.current?.focus({preventScroll: true});
  }, [ordinal]);
  const result = api<{row: Row<Configuration>; artifact_sha256: string; metric_versions: string[]}>(`/api/v1/row/${table}/${ordinal}`);
  const data = result?.result?.row.data;
  return <section ref={panel} tabIndex={-1} className="panel detail" aria-label="Exact configuration">
    <div className="panel-head"><h3>Exact configuration · Row {ordinal}</h3><button onClick={close}>Close</button></div>
    {!data ? <Loading error={result?.error}/> : <>
      <p>{data.scenario} · poll {data.interval_ms} ms · phase {data.phase_percent}% · as-of {data.tolerance_ms ?? data.broker.tolerance_ms} ms</p>
      {data.duration_ms !== undefined && <p>Width {data.duration_ms} ms · transport {data.transport_ms} ms · processing {data.processing_ms} ms</p>}
      <small>Metric versions {result.result?.metric_versions.join(" · ")}</small>
      <p><b>Result artifact SHA-256</b> <code>{result.result?.artifact_sha256}</code></p>
      {data.input_sha256 ? <TruthDetail sha={data.input_sha256}/> :
        <a href={`/api/v1/artifact/p2/evidence-${data.scenario}.json`}>Download original scenario evidence</a>}
      <a href={`/api/v1/evidence/${table}`}>Evidence references</a>
      <details><summary>Complete row, exclusions and match boundaries</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
    </>}
  </section>;
}

function TruthDetail({sha}: {sha: string}) {
  const result = api<Page<Data>>(`/api/v1/table/truth?input_sha256=${sha}&limit=1`);
  return <><p><b>Truth input SHA-256</b> <code>{sha}</code></p>
    <details><summary>Verified synthetic input</summary>{result?.result ?
      <pre>{JSON.stringify(result.result.rows[0]?.data.input, null, 2)}</pre> : <Loading error={result?.error}/>}</details>
  </>;
}

function ConfigurationView({route, datasets}: {route: "sampling"|"factorial"|"tail"; datasets: Dataset[]}) {
  const sampling = route === "sampling";
  const tail = route === "tail";
  const table = sampling ? "p2" : "p21";
  const choices = datasets.find(dataset => dataset.id === table)?.scenarios ?? [];
  const [scenario, setScenario] = useState(sampling ? "short-spike" : "isolated");
  const [interval, setInterval] = useState(tail ? "250" : "");
  const [width, setWidth] = useState(tail ? "250" : "");
  const [phase, setPhase] = useState("0");
  const [transport, setTransport] = useState("0");
  const [processing, setProcessing] = useState("0");
  const [tolerance, setTolerance] = useState("250");
  const [session, setSession] = useState("");
  const [metric, setMetric] = useState<Metric>("recall");
  const [ordinal, setOrdinal] = useState<number|null>(null);

  const query = params({scenario, interval_ms: interval, phase_percent: phase, limit: 64, ...(sampling ? {tolerance_ms: tolerance} :
    {duration_ms: width, transport_ms: transport, processing_ms: processing})});
  const loaded = api<Page<Configuration>>(`/api/v1/table/${table}?${query}`);
  const data = loaded?.result;
  const sessions = [...new Set(data?.rows.flatMap(row => row.data.streams.map(item => item.session_id)))];
  const active = sessions.includes(session) ? session : sessions[0] ?? "";
  const change = (action: (value: string) => void) => (value: string) => {setOrdinal(null); action(value);};
  let chart: React.ReactNode = null;
  const support = `${data?.rows.length ?? 0} configurations · ${active || "no source"}`;
  if (data?.rows.length && tail) {
    const stream = data.rows[0].data.streams.find(item => item.session_id === active);
    const values = stream?.tails;
    if (values) chart = <>
      <Plot label="Tail-decomposition bars" traces={contrasts.map(c => ({
        type: "bar", name: c.label, x: ["p95", "p99"], marker: {color: c.color},
        y: (["p95", "p99"] as const).map(key => plotNumber(values[key][c.key])),
        text: (["p95", "p99"] as const).map(key => display(values[key][c.key], values[key][c.reason])),
        hovertemplate: "%{x} · %{text}<extra></extra>",
      }))} axes={{barmode: "group", yaxis: {title: {text: "USD / troy oz"}, zerolinecolor: "#8390a3"}}}/>
      <div className="table-wrap"><table><thead><tr><th>Tail</th><th>Oracle duration (O)</th><th>Sampled duration (D)</th><th>Sampled snapshot (S)</th>{contrasts.map(c => <th key={c.key}>{c.label}</th>)}</tr></thead>
        <tbody>{(["p95", "p99"] as const).map(key => <tr key={key}><th>{key}</th>
          <td><Exact value={values[key].oracle_duration}/></td><td><Exact value={values[key].sampled_duration}/></td><td><Exact value={values[key].sampled_snapshot}/></td>
          {contrasts.map(c => <td key={c.key}><Exact value={values[key][c.key]} reason={values[key][c.reason]}/></td>)}
        </tr>)}</tbody></table></div>
    </>;
  } else if (data?.rows.length && sampling) {
    const ordered = [...data.rows].sort((a,b) => a.data.interval_ms - b.data.interval_ms);
    const stats = ordered.map(row => lookup(row.data, row.data.streams.find(s => s.session_id === active), metric));
    chart = <Plot label="Sensitivity curve" onSelect={setOrdinal} traces={[{
      type: "scatter", mode: "lines+markers", x: ordered.map(row => row.data.interval_ms),
      y: stats.map(s => plotNumber(s.value)), customdata: ordered.map(row => row.ordinal),
      text: stats.map(s => `${display(s.value, s.reason)} · support ${s.support ?? "unavailable"}`),
      hovertemplate: "%{x} ms · %{text}<extra></extra>", connectgaps: false,
      line: {color: "#526ee7", width: 3}, marker: {size: 10, color: "#526ee7"},
    }]} axes={{xaxis: {title: {text: "Polling interval (ms)"}, tickvals: intervals},
      yaxis: {tickformat: ".0%", range: [-0.03, 1.03]}}}/>;
  } else if (data?.rows.length) {
    const {axes, cells} = heatmap(data.rows, active, metric);
    chart = <Plot label="Factorial detection heatmap" onSelect={setOrdinal} traces={[{
      type: "heatmap", x: axes.x.map(String), y: axes.y.map(String), z: cells.map(row => row.map(c => plotNumber(c.value))),
      text: cells.map(row => row.map(c => c.text)), customdata: cells.map(row => row.map(c => c.ordinal)),
      colorscale: [[0, "#e9efff"], [.48, "#a4b8f9"], [1, "#384dcc"]], zmin: 0, zmax: 1, xgap: 4, ygap: 4,
      colorbar: {tickformat: ".0%"}, hoverongaps: false, hovertemplate: "%{x} ms poll / %{y} ms width<br>%{text}<extra></extra>",
    }]} axes={{xaxis: {type: "category", title: {text: "Polling interval (ms)"}},
      yaxis: {type: "category", title: {text: "Widening duration (ms)"}}}}/>;
  }

  return <>
    <section className="panel controls" aria-label="Experiment filters">
      <Select label="Scenario" value={scenario} options={choices} change={change(setScenario)}/>
      <Select label="Polling interval (ms)" value={interval} options={tail ? intervals : ["", ...intervals]} change={change(setInterval)}/>
      <Select label="Sampling phase (%)" value={phase} options={[0,25,50,75]} change={change(setPhase)}/>
      {sampling ? <Select label="As-of tolerance (ms)" value={tolerance} options={intervals} change={change(setTolerance)}/> :
        <><Select label="Transport delay (ms)" value={transport} options={[0,25,100,250]} change={change(setTransport)}/>
          <Select label="Processing delay (ms)" value={processing} options={[0,25,100]} change={change(setProcessing)}/>
          <Select label="Widening duration (ms)" value={width} options={tail ? widths : ["", ...widths]} change={change(setWidth)}/></>}
      {!tail && <label>Metric type<select value={metric} onChange={e => setMetric(e.target.value as Metric)}>
        {Object.entries(metrics).filter(([key]) => !(sampling && key === "revisions")).map(([key,m]) => <option key={key} value={key}>{m.label}</option>)}
      </select></label>}
      {sessions.length > 1 && <Select label="Source session" value={active} options={sessions} change={setSession}/>}
    </section>
    {!data ? <Loading error={loaded?.error}/> : <>
      <figure className="panel analysis">{chart || <p className="notice">No configurations match these filters.</p>}
        <FigureNote page={data} title={tail ? "Exact tail components" : metrics[metric].label}
          unit={tail ? "USD/troy oz" : metrics[metric].unit} support={support}
          version={tail ? "p21-tail-decomposition-v1" : metrics[metric].version}
          limit={tail ? "O = oracle duration, D = sampled duration, S = sampled snapshot. S−O combines both effects." : "Deterministic scenario support. As-of measures snapshot age, and uncovered cells are unavailable."}/>
      </figure>
      <section className="panel"><div className="panel-head"><h3>Configuration results</h3><a href={`/api/v1/export/${table}?${query}&${params({view_metric:tail ? "tail" : metric, view_session:active})}`}>Export filtered JSON ↓</a></div>
        <ConfigurationTable rows={data.rows} metric={metric} session={active} select={setOrdinal}/></section>
      {ordinal !== null && <Detail table={table} ordinal={ordinal} close={() => setOrdinal(null)}/>}
      {sampling && <AsOfSweep interval={interval || "500"}/>}
    </>}
  </>;
}

function AsOfSweep({interval}: {interval: string}) {
  type AsOf = {tolerance_ms: number; coverage: string | null; consensus_coverage: string | null; cells: number};
  const response = api<Page<AsOf>>(`/api/v1/table/asof-sensitivity?interval_ms=${interval}`);
  const page = response?.result;
  if (!page) return <Loading error={response?.error}/>;
  const rows = page.rows.map(row => row.data);
  return <figure className="panel analysis">
    <Plot label="Broker as-of sensitivity curve" traces={[
      {key: "coverage", name: "Broker coverage", color: "#27a98c"},
      {key: "consensus_coverage", name: "Consensus coverage", color: "#526ee7"},
    ].map(trace => {
      const values = rows.map(row => row[trace.key as "coverage" | "consensus_coverage"]);
      return {type:"scatter",mode: "lines+markers",name: trace.name,
        x: rows.map(row => row.tolerance_ms), y: values.map(plotNumber),
        text: values.map(value => display(value)), hovertemplate: "%{x} ms · %{text}<extra></extra>",
        line: {color: trace.color}, connectgaps: false};
    })} axes={{xaxis: {title: {text:"As-of tolerance (ms)"}, tickvals: intervals},
      yaxis: {tickformat: ".0%", range: [-.03, 1.03]}}}/>
    <FigureNote page={page} title="Broker as-of sensitivity · P2.1" version="broker-comparison-v1.1"
      unit="fraction" support={`${rows.length} tolerances · ${rows[0]?.cells ?? 0} configurations per tolerance`}
      limit="Published asynchronous sweep at transport 100 ms and processing 25 ms. This cohort uses three widths and all phases. Age tolerance is a snapshot age cap."/>
    <a href={`/api/v1/export/asof-sensitivity?interval_ms=${interval}`}>Export published sweep ↓</a>
  </figure>;
}

function Atlas() {
  const data = api<Page<Counterexample>>("/api/v1/table/identifiability");
  const [selection, select] = useState("hidden-1");
  const example = data?.result?.rows.find(row => row.data.id === selection)?.data;
  const record = (title: string, rows: (Quote & {event?:string})[], truth?: boolean) =>
    <article className="panel"><h3>{title}</h3><div className="table-wrap"><table><thead><tr><th>{truth ? "Event" : "Poll"} ns</th><th>Bid</th><th>Ask</th><th>Spec</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.event ?? row.received_wall_ns}><td>{row.event ?? row.received_wall_ns}</td><td><Exact value={row.bid_text}/></td><td><Exact value={row.ask_text}/></td><td>{row.instrument_spec_version}</td></tr>)}</tbody></table></div></article>;
  if (!example) return <Loading error={data?.error}/>;
  return <>
    <div className="panel controls"><Select label="Counterexample" value={selection} options={data!.result!.rows.map(row => row.data.id)} change={select}/>
      <div><span className="tag">Synthetic · {data?.result?.source_experiment}</span><p>Poll {example.interval_ms} ms · phase {example.phase_percent}% · two histories, one observed record</p></div>
    </div>
    <section className="panel">
      <h3>Different truth under the same observations</h3>
      <p>History A has {example.quiet.episodes} widening episodes and oracle p{example.tail_percentile} of {example.quiet.oracle_tail} USD/troy oz. History B has {example.hidden.episodes} episodes and oracle p{example.tail_percentile} of {example.hidden.oracle_tail} USD/troy oz.</p>
      <p>The sampled quotes and origin metadata are identical in this construction. Hidden widening and oracle tails therefore require additional assumptions to identify.</p>
      <code>Shared sample SHA-256 {example.sample_sha256}</code>
    </section>
    <div className="paired">{record("Truth history A", example.quiet.truth.events.map(row => ({...row.arrival, event: row.event_ns})), true)}
      {record("Truth history B", example.hidden.truth.events.map(row => ({...row.arrival, event: row.event_ns})), true)}</div>
    {record("Identical sampled observations", example.shared_sample.stream.observations)}
    <a href="/api/v1/export/identifiability">Export both counterexamples ↓</a>
  </>;
}

function EvidenceView() {
  const [family, setFamily] = useState<Family>("p21");
  const [selected, select] = useState("");
  const packets = api<{packets: Packet[]}>(`/api/v1/evidence/${family}`);
  const provenance = api<Dataset & {manifest: Data|null}>(`/api/v1/provenance/${family}`);
  const active = packets?.result?.packets.find(item => item.name === selected) ?? packets?.result?.packets[0];
  const meta = provenance?.result;
  return <>
    <div className="panel controls">
      <Select label="Evidence version / dataset" value={family} options={["p1", "p2", "p21"]} change={value => {setFamily(value as Family); select("");}}/>
      {active && <Select label="Evidence packet" value={active.name} options={packets!.result!.packets.map(item => item.name)} change={select}/>}
    </div>
    {!active ? <Loading error={packets?.error}/> : <section className="panel">
      <div className="panel-head"><h3>{active.packet.research_id}</h3><a href={`/api/v1/artifact/${family}/${active.name}`}>Download original packet ↓</a></div>
      <p>{active.packet.question}</p><p><span className="tag">Synthetic</span> {active.packet.version} · {active.packet.metric_versions.join(" · ")}</p>
      <p>Packet SHA-256 <code>{active.sha256}</code></p>
      {[...active.packet.findings, ...active.packet.candidate_explanations].map((claim, i) => <div className="claim" key={i}>
        <b>{claim.status}</b><span>{claim.statement} {claim.value !== null && `${claim.value} ${claim.unit ?? ""}`}</span>
      </div>)}
      <h4>Assumptions and limits</h4><ul>{[...active.packet.clock_assumptions, ...active.packet.limitations].map(item => <li key={item}>{item}</li>)}</ul>
      <h4>Falsifiers</h4><ul>{active.packet.falsifiers.map(item => <li key={item}>{item}</li>)}</ul>
      <details><summary>Input references and full packet</summary><pre>{JSON.stringify(active.packet, null, 2)}</pre></details>
    </section>}
    {!meta ? <Loading error={provenance?.error}/> : <section className="panel"><div className="panel-head"><h3>Artifact provenance</h3>
      {meta.manifest && <a href={`/api/v1/artifact/${family}/manifest.json`}>Download original manifest ↓</a>}</div>
      <p><b>Verification method</b> {meta.verification.replaceAll("-", " ")}. A declared code SHA is provenance metadata. Authenticity requires an independently trusted reference.</p>
      {meta.manifest_sha256 && <p>Manifest SHA-256 <code>{meta.manifest_sha256}</code></p>}
      <p>Declared code SHA <code>{meta.declared_code_sha}</code></p>
      <div className="table-wrap"><table><thead><tr><th>Artifact</th><th>Classification</th><th>Bytes</th><th>SHA-256</th></tr></thead>
        <tbody>{Object.entries(meta.artifacts).map(([name, artifact]) => <tr key={name}><td>{name}</td><td>{artifact.classification}</td><td>{artifact.bytes}</td><td><code>{artifact.sha256}</code></td></tr>)}</tbody></table></div>
    </section>}
  </>;
}

function current(): Route {
  return routes.find(([name]) => name === location.hash.slice(1))?.[0] ?? "overview";
}

function App() {
  const [route, setRoute] = useState(current);
  const datasetResponse = api<{datasets: Dataset[]}>("/api/v1/datasets");
  const datasets = datasetResponse?.result?.datasets;
  useEffect(() => {
    const update = () => {setRoute(current()); window.scrollTo(0, 0);};
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return <div className="app">
    <aside><div className="brand"><span>◈</span><div>XAUUSD<small>RESEARCH LAB</small></div></div>
      <nav aria-label="Research views">{routes.map(([id,name]) => <a key={id} href={`#${id}`} aria-current={id === route ? "page" : undefined}><span>{["◉","∿","▦","◫","◇","≡"][routes.findIndex(r => r[0] === id)]}</span>{name}</a>)}</nav>
      <div className="side-note"><span className="status-dot"/> Read-only · Local workspace</div>
    </aside>
    <main><header><div className="eyebrow">XAUUSD / SYNTHETIC STUDIES</div><span className="tag">Synthetic data only</span></header>
      <h1>{routes.find(item => item[0] === route)?.[2]}</h1>
      {!datasets ? <Loading error={datasetResponse?.error}/> : route === "overview" ? <Overview datasets={datasets} navigate={page => {location.hash = page;}}/> :
        route === "atlas" ? <Atlas/> : route === "evidence" ? <EvidenceView/> :
        <ConfigurationView key={route} route={route} datasets={datasets}/>}
      <footer>Local synthetic research · LOCAL_MT5_UNVERIFIED</footer>
    </main>
  </div>;
}

createRoot(document.getElementById("root")!).render(<App/>);
