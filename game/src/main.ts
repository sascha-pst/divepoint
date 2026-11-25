/// <reference types="vite/client" />
import type Phaser from "phaser";
import type { Ocean } from "./ocean";
import type { Card, DiveScenery, LogEntry, Manifest, Place, Species } from "./types";
import { DepthSurvey, speciesNearDepth, surveyStops } from "./sequences";
import terrain from "./terrain.json";
import "./style.css";

const publicDemo = import.meta.env.MODE === "demo";
const demoPlaces = ["Monterey Bay", "Red Sea", "Raja Ampat"];
let demoCards: Record<number, Card> = {};

const root = document.querySelector<HTMLDivElement>("#app")!;
const esc = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
const safeURL = (value: string) =>
  value.startsWith("https://") ? esc(value) : "#";
const icon = '<span class="brand-icon" aria-hidden="true">◒</span>';
let manifest: Manifest | null = null;
let engine: Phaser.Game | null = null;
let ocean: Ocean | null = null;
let currentDepth = 15;
let survey: DepthSurvey | null = null;
let session = new Set<number>();
let seenThisDive: Species[] = [];
let requestBody: {
  text: string;
  depth_m: number;
  month: number | null;
  place_id?: number;
  allow_sparse?: boolean;
};
let cardToken = 0;
let busy = false;
let sceneGeneration = 0;
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function readLogs(): LogEntry[] {
  try {
    const value = JSON.parse(
      localStorage.getItem("divepoint-fishdex-v1") || "[]",
    );
    return Array.isArray(value)
      ? value.filter(
          (l) =>
            l &&
            typeof l.aphia_id === "number" &&
            typeof l.common === "string" &&
            typeof l.name === "string" &&
            typeof l.place === "string" &&
            typeof l.date === "string",
        )
      : [];
  } catch {
    return [];
  }
}
let logs = readLogs();
function saveLogs() {
  try {
    localStorage.setItem("divepoint-fishdex-v1", JSON.stringify(logs));
  } catch {
    toast(
      "Browser storage is unavailable. Discoveries will last for this visit.",
    );
  }
}
function toast(message: string) {
  const target = document.querySelector("#toast");
  if (target) {
    target.textContent = message;
    window.setTimeout(() => {
      if (target.textContent === message) target.textContent = "";
    }, 4500);
  }
}
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(90000),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "We couldn’t prepare that dive. Check the place and try again.",
    );
  return data;
}
async function loadRecordedDive() {
  const slug = requestBody.text.toLowerCase().replaceAll(" ", "-");
  const key = `${slug}-${requestBody.depth_m}-${requestBody.month ?? 0}`;
  const response = await fetch(`./dives/${key}.json`, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error("Couldn’t load this recorded dive. Try again.");
  const data: { manifest: Manifest; cards: Record<number, Card> } = await response.json();
  demoCards = data.cards;
  return data.manifest;
}

function shell(content: string, dark = false) {
  document.body.classList.toggle("diving", dark);
  root.innerHTML = `<header class="topbar"><button class="brand" id="home">${icon}divepoint<span class="beta">FIELD NOTES / 01</span></button>
    <nav><span class="nav-note">A WORLD WORTH LOOKING CLOSER AT</span><button class="nav-link" id="logbook">Fishdex <span class="count">${new Set(logs.map((l) => l.aphia_id)).size}</span></button></nav></header>
    ${content}<footer class="footer"><span>Real places. Real species. Endless curiosity.</span><button id="credits">Sources & credits ↗</button></footer>
    <div id="toast" role="status" aria-live="polite"></div><dialog id="modal" class="modal"></dialog>`;
  document.querySelector("#home")!.addEventListener("click", () => {
    if (ocean) surface();
    else home();
  });
  document.querySelector("#logbook")!.addEventListener("click", logbook);
  document.querySelector("#credits")!.addEventListener("click", credits);
  const dialog = modal();
  dialog.addEventListener("close", () => {
    ++cardToken;
    ocean?.pauseDive(false);
  });
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });
}
function modal() {
  return document.querySelector<HTMLDialogElement>("#modal")!;
}
function openModal(html: string) {
  const dialog = modal();
  ocean?.pauseDive(true);
  dialog.innerHTML = `<button class="close" aria-label="Close dialog">×</button>${html}`;
  dialog
    .querySelector(".close")!
    .addEventListener("click", () => dialog.close());
  if (!dialog.open) dialog.showModal();
}
function dispose() {
  ++sceneGeneration;
  ++cardToken;
  ocean = null;
  engine?.destroy(true);
  engine = null;
}
function home() {
  dispose();
  manifest = null;
  shell(`<main class="home-grid"><section class="intro"><p class="eyebrow"><span class="tiny-dot"></span> AN OCEAN OF TRUE STORIES</p>
    <h1>A little curiosity.<br>A whole <em>ocean.</em></h1>
    <p class="lede">Pick a place. Slip beneath the surface.<br>Meet the life that calls it home.</p>
    <form id="plan-form"><label for="place">WHERE SHALL WE GO?</label>${publicDemo
      ? `<select id="place" name="place">${demoPlaces.map((place) => `<option>${place}</option>`).join("")}</select>`
      : '<div class="input-wrap"><span aria-hidden="true">⌕</span><input id="place" name="place" required maxlength="300" value="Monterey Bay" placeholder="A bay, a reef, a sea…" autocomplete="off"></div>'}
    <div class="filter-row"><label for="maxdepth">EXPLORE DOWN TO<select id="maxdepth"><option value="15">15 metres</option><option value="30" selected>30 metres</option><option value="60">60 metres</option></select></label>
      <label for="month">WHEN<select id="month"><option value="">Any month</option>${MONTHS.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("")}</select></label></div>
    <button class="primary" id="explore" type="submit">Find my dive <span>↗</span></button><p id="plan-status" class="form-status" role="status" aria-live="polite"></p></form>
    ${publicDemo ? "" : `<div class="suggestions"><span>FOLLOW A HUNCH</span><button data-place="Monterey Bay">Monterey Bay</button><button data-place="Red Sea">Red Sea</button><button data-place="Raja Ampat">Raja Ampat</button></div>`}
    <p class="small-note">${publicDemo ? "Noncommercial demo · Three destinations with recorded sightings." : "Monterey Bay, Red Sea, and Raja Ampat are ready to dive offline.<br>Other destinations search live marine records."}</p></section>
    <aside class="ocean-postcard"><div class="postcard-top"><span>THE PACIFIC COLLECTION</span><span>36°48′ N · 121°54′ W</span></div>
      <div class="sun-halo"></div><div class="water-line"></div><div class="water-rays"></div>
      <div class="contour c1"></div><div class="contour c2"></div><div class="contour c3"></div>
      <div class="kelp-art">${Array.from({ length: 9 }, (_, i) => `<i style="--i:${i}"><b></b><b></b><b></b><b></b></i>`).join("")}</div>
      <div class="depth-mark"><span>00</span><i></i><span>15</span><i></i><span>30 m</span></div>
      <div class="postcard-bottom"><span class="pill">A CLOSER LOOK</span><h2>There’s a world<br>beneath this one.</h2><p>Every encounter begins with a real record.</p></div>
    </aside></main><section class="principles"><span><b>01</b> Describe a place</span><span><b>02</b> Meet its marine life</span><span><b>03</b> Keep a little wonder</span></section>`);
  document
    .querySelector<HTMLFormElement>("#plan-form")!
    .addEventListener("submit", (e) => {
      e.preventDefault();
      requestBody = {
        text: document.querySelector<HTMLInputElement>("#place")!.value,
        depth_m: Number(
          document.querySelector<HTMLSelectElement>("#maxdepth")!.value,
        ),
        month:
          Number(document.querySelector<HTMLSelectElement>("#month")!.value) ||
          null,
      };
      void plan();
    });
  document.querySelectorAll<HTMLButtonElement>("[data-place]").forEach(
    (button) =>
      (button.onclick = () => {
        document.querySelector<HTMLInputElement>("#place")!.value =
          button.dataset.place!;
        document.querySelector<HTMLInputElement>("#place")!.focus();
      }),
  );
}
async function plan() {
  if (busy) return;
  busy = true;
  const button = document.querySelector<HTMLButtonElement>("#explore");
  if (button) {
    button.disabled = true;
    button.textContent = "Looking beneath the surface…";
  }
  const status = document.querySelector("#plan-status");
  if (status)
    status.textContent =
      publicDemo ? "Loading recorded sightings…" :
        "Resolving the place and checking individual species records. Live searches can take a little longer.";
  try {
    const result = publicDemo ? await loadRecordedDive() : await api<
      Manifest | { type: "clarify"; candidates: Place[]; message: string }
    >("/v1/dives/plan", requestBody);
    if (result.type === "clarify") {
      openModal(
        `<p class="eyebrow">CHOOSE YOUR COORDINATES</p><h2>${esc(result.message)}</h2><div class="candidate-list">${result.candidates.map((p) => `<button data-id="${p.mrgid}"><b>${esc(p.name)}</b><span>${p.latitude.toFixed(2)}°, ${p.longitude.toFixed(2)}° ↗</span></button>`).join("") || "<p>Try a named bay, sea, or reef, or choose an offline destination.</p>"}</div>`,
      );
      modal()
        .querySelectorAll<HTMLButtonElement>("[data-id]")
        .forEach(
          (b) =>
            (b.onclick = () => {
              requestBody.place_id = Number(b.dataset.id);
              modal().close();
              void plan();
            }),
        );
    } else {
      manifest = result;
      confirmDive(result);
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Dive search failed.";
    if (status)
      status.textContent = !publicDemo && message.includes("fetch")
        ? "Start the Divepoint API on port 8000, then try again."
        : message;
    else
      openModal(
        `<h2>Not quite there yet.</h2><p>${esc(message)}</p><button class="primary" id="retry">Try another place</button>`,
      );
    document.querySelector("#retry")?.addEventListener("click", home);
  } finally {
    busy = false;
    if (button?.isConnected) {
      button.disabled = false;
      button.innerHTML = "Find my dive <span>↗</span>";
    }
  }
}
function globe(place: Place) {
  const y = 150 - (place.latitude / 90) * 110;
  return `<svg viewBox="0 0 400 320" role="img" aria-label="Globe marking ${esc(place.name)} at ${place.latitude.toFixed(2)} latitude, ${place.longitude.toFixed(2)} longitude">
    <defs><radialGradient id="globe"><stop stop-color="#e6eee5"/><stop offset="1" stop-color="#b7cfbf"/></radialGradient></defs>
    <circle cx="200" cy="150" r="125" fill="url(#globe)"/><g fill="none" stroke="#688b7950"><circle cx="200" cy="150" r="125"/><ellipse cx="200" cy="150" rx="60" ry="125"/><ellipse cx="200" cy="150" rx="105" ry="125"/><ellipse cx="200" cy="150" rx="125" ry="45"/><ellipse cx="200" cy="150" rx="125" ry="90"/><path d="M75 150h250M200 25v250"/></g>
    <circle cx="200" cy="${y}" r="16" fill="#e47a5430"/><circle cx="200" cy="${y}" r="5" fill="#dd6c47"/>
    <path d="M210 ${y}h90" stroke="#dd6c47"/><text x="200" y="305" text-anchor="middle" fill="#536c61" font-family="monospace" font-size="11">CENTERED ON ${place.longitude.toFixed(2)}° LONGITUDE</text></svg>`;
}
function confirmDive(data: Manifest) {
  const count = data.species.length;
  const stops = surveyStops(data);
  shell(`<main class="confirm"><button class="back" id="back">← Back to the surface</button><div class="confirm-grid"><section><p class="eyebrow">YOUR NEXT CHAPTER</p><h1>${esc(data.place.name)}<span class="period">.</span></h1><p class="lede">A place on the map.<br>A whole world to meet.</p>
    <div class="dive-stats"><div><b>${count}</b><span>VERIFIED FISH SPECIES</span></div><div><b>0–${data.filters.depth_m[1]}<small> m</small></b><span>DEPTH BAND</span></div></div>
    <p>${esc(data.message)} ${data.type === "too_sparse" ? "This is a small sample. You can explore it or broaden your filters." : "Ready when you are."}</p>
    <button class="primary" id="enter" ${count === 0 ? "disabled" : ""}>${data.type === "too_sparse" ? "Explore this small sample" : "Explore freely"} <span>↓</span></button>
    <div class="survey-option"><button class="text-button" id="survey" aria-describedby="survey-description" ${stops.length ? "" : "disabled"}>Start a depth survey</button>
    <p class="small-note" id="survey-description">${stops.length ? `Log one encounter at each stop in order · ${stops.map((depth) => `${depth} m`).join(" → ")}` : "A survey needs encounters across a wider depth range."}</p></div>
    <button class="text-button" id="change">Change depth or month</button>
    <p class="small-note">${data.source_mode === "recorded" ? `Recorded snapshot · ${new Date(data.captured_at!).toLocaleDateString()}` : "Live OBIS records"}<br>${esc(data.notice)} Encounter rarity reflects this sample.</p>
    </section><aside class="map-card">${globe(data.place)}<div class="map-label"><span class="tiny-dot"></span><b>${esc(data.place.name)}</b><span>${data.place.latitude.toFixed(3)}°, ${data.place.longitude.toFixed(3)}°</span></div><p>${esc(data.place.area_kind)} · <a href="${safeURL(data.place.source_url)}" target="_blank" rel="noopener noreferrer">Marine Regions ↗</a></p></aside></div></main>`);
  document
    .querySelector("#enter")!
    .addEventListener("click", () => startDive(data));
  document.querySelector("#survey")!.addEventListener("click", () => startDive(data, stops));
  document.querySelector("#back")!.addEventListener("click", home);
  document.querySelector("#change")!.addEventListener("click", home);
}
function diveScenery(place: Place): DiveScenery {
  if (place.mrgid === 19167) return "open-sea";
  if (place.mrgid === 4264 || /^red sea$/i.test(place.name.trim())) return "red-sea";
  if (place.mrgid === 21076 || /\braja ampat\b/i.test(place.name)) return "raja-ampat";
  return "kelp";
}

function startingDepth(data: Manifest): number {
  const preferred = Math.floor(Math.min(15, data.filters.depth_m[1]));
  let closest = preferred;
  let distance = Infinity;
  for (const species of data.species) {
    const [shallow, deep] = species.depth_m;
    const depth = Math.max(shallow, Math.min(deep, preferred));
    if (Math.abs(depth - preferred) < distance) {
      closest = depth;
      distance = Math.abs(depth - preferred);
    }
  }
  return distance <= 5 || !Number.isFinite(distance)
    ? preferred
    : Math.min(Math.floor(data.filters.depth_m[1]), Math.round(closest));
}

async function startDive(data: Manifest, stops: readonly number[] = []) {
  dispose();
  manifest = data;
  survey = stops.length ? new DepthSurvey(stops) : null;
  session = new Set();
  seenThisDive = [];
  const generation = sceneGeneration;
  const scenery = diveScenery(data.place);
  const terrainGrid =
    scenery === "red-sea" || scenery === "raja-ampat" ? terrain.grids[scenery] : null;
  const reefZone = scenery === "red-sea" || scenery === "raja-ampat" ? "REEF" : "REEF / KELP";
  const galleryNote = {
    "open-sea": 'Inspired by the aquarium’s <a href="https://www.montereybayaquarium.org/visit/exhibits/open-sea" target="_blank" rel="noopener noreferrer">Open Sea gallery ↗</a>',
    "red-sea": "Southern Red Sea 3D terrain",
    "raja-ampat": "Raja Ampat 3D terrain",
    kelp: "",
  }[scenery];
  currentDepth = survey?.target ?? startingDepth(data);
  shell(
    `<main class="dive-shell">
    <header class="dive-toolbar">
      <div><h1>${esc(data.place.name)}</h1>${galleryNote ? `<p class="gallery-credit">${galleryNote}${terrainGrid ? ` · <a href="${safeURL(terrain.source.url)}" target="_blank" rel="noopener noreferrer">${esc(terrain.source.label)} ↗</a> · Stylized scale` : ""}</p>` : ""}</div>
      <div class="dive-actions">${publicDemo ? "" : '<button id="ask-guide" class="guide-button">Ask the Guide</button>'}<button id="surface" class="surface-button">Surface ↑</button></div>
    </header>
    <div class="dive-layout">
      <div class="dive-gallery ${scenery}-gallery">
        <section class="viewport" aria-label="Interactive underwater dive${terrainGrid ? " over 3D seafloor terrain" : ""}">
          <div id="ocean"></div><p id="scene-loading" role="status">Descending…</p>
          <span class="zone-tag" id="zone"></span>
          <p class="dive-hint">Tap a fish to log it.<span>↑ ↓ change depth · Cards pause the timer</span></p>
        </section>
      </div>
      <section class="dive-computer" aria-labelledby="computer-heading">
        <h2 id="computer-heading">Dive computer <span>SIMULATION</span></h2>
        <div class="instruments">
          <div class="computer-depth"><span>DEPTH</span><b id="depth-readout">${currentDepth}<small> m</small></b></div>
          <div><span>AIR TIMER</span><b id="air-readout">4:00</b><progress id="air" max="240" value="240" aria-label="Remaining game time"></progress></div>
          <div><span>LOGGED</span><b id="found">${session.size} <small>/ ${data.species.length}</small></b></div>
        </div>
        ${survey ? `<div class="survey-progress">
          <p id="survey-progress" role="status"></p>
          <button type="button" class="guide-button" id="survey-next" hidden></button>
        </div>` : ""}
        <div class="depth-control">
          <label for="depth-slider">Adjust depth</label>
          <div class="depth-scale">
            <span aria-hidden="true">0 m</span>
            <input id="depth-slider" type="range" min="0" max="${data.filters.depth_m[1]}" step="1" value="${currentDepth}" disabled>
            <span aria-hidden="true">${data.filters.depth_m[1]} m</span>
          </div>
        </div>
      </section>
      <aside class="encounters" aria-labelledby="encounter-heading">
        <div><h2 id="encounter-heading">Nearby species</h2><p class="small-note">Choose a fish recorded near this depth to open its species card.</p></div>
        <div class="encounter-buttons" id="encounter-buttons"></div>
      </aside>
    </div>
    <p class="dive-provenance">${data.source_mode === "recorded" ? "Recorded occurrence snapshot" : "Live occurrence sample"} · Individual presence records verified · ${data.filters.months.length ? data.filters.months.map((m) => MONTHS[m - 1]).join(", ") : "All months"} · <a href="${safeURL(data.place.source_url)}" target="_blank" rel="noopener noreferrer">Area source ↗</a></p></main>`,
    true,
  );
  renderSurveyProgress();
  document.querySelector("#survey-next")?.addEventListener("click", () => {
    const target = survey?.target;
    if (!ocean || target === undefined) return;
    document.querySelector<HTMLInputElement>("#depth-slider")?.focus();
    ocean.setDepth(target);
  });
  document.querySelector("#ask-guide")?.addEventListener("click", () => askGuide(data));
  document
    .querySelector("#surface")!
    .addEventListener("click", () => (ocean ? surface() : home()));
  try {
    const [{ default: Phaser }, { Ocean }] = await Promise.all([
      import("phaser"),
      import("./ocean"),
    ]);
    if (sceneGeneration !== generation) return;
    ocean = new Ocean(
      data,
      scenery,
      currentDepth,
      terrainGrid?.depthsM,
      (s) => void encounter(s),
      (seconds) => {
        const value = document.querySelector("#air-readout");
        if (value)
          value.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
        const bar = document.querySelector<HTMLProgressElement>("#air");
        if (bar) bar.value = seconds;
      },
      (depth) => {
        currentDepth = depth;
        const label = document.querySelector("#depth-readout");
        if (label) label.innerHTML = `${depth}<small> m</small>`;
        const slider =
          document.querySelector<HTMLInputElement>("#depth-slider");
        if (slider) {
          slider.value = String(depth);
          slider.disabled = false;
          slider.setAttribute("aria-valuetext", `${depth} metres`);
        }
        document.querySelector("#scene-loading")?.remove();
        const zone = document.querySelector("#zone");
        if (zone)
          zone.textContent =
            depth <= 5
              ? "SURFACE · 0–5 M"
              : depth <= 30
                ? `${reefZone} · 5–30 M`
                : "WALL · 30–60 M";
        renderSurveyProgress();
        renderEncounterButtons();
      },
      () => surface(true),
    );
    engine = new Phaser.Game({
      type: Phaser.AUTO,
      parent: "ocean",
      transparent: true,
      scale: { mode: Phaser.Scale.RESIZE, width: "100%", height: "100%" },
      scene: ocean,
      render: { antialias: true },
      audio: { noAudio: true },
    });
    const depthSlider = document.querySelector<HTMLInputElement>("#depth-slider")!;
    depthSlider.oninput = () => ocean?.setDepth(depthSlider.valueAsNumber);
    depthSlider.onkeydown = (event) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      ocean?.setDepth(depthSlider.valueAsNumber + (event.key === "ArrowDown" ? 1 : -1));
    };
    if (modal().open) ocean.pauseDive(true);
  } catch {
    if (sceneGeneration === generation) {
      const message = document.querySelector("#scene-loading");
      if (message)
        message.textContent =
          "The ocean scene could not load. Refresh the page to try again.";
    }
  }
}
function renderSurveyProgress() {
  const status = document.querySelector("#survey-progress");
  if (!status || !survey) return;
  const target = survey.target;
  const instruction = target === undefined
    ? "Survey complete. Surface when ready."
    : currentDepth === target
      ? `Log an encounter at ${target} m.`
      : `Move to ${target} m for the next encounter.`;
  const message = `${survey.completed}/${survey.stops.length} survey stops · ${instruction}`;
  if (status.textContent !== message) status.textContent = message;
  const next = document.querySelector<HTMLButtonElement>("#survey-next")!;
  next.hidden = target === undefined || target === currentDepth;
  if (!next.hidden) next.textContent = `Go to ${target} m`;
}

function renderEncounterButtons() {
  const target = document.querySelector("#encounter-buttons");
  if (!target || !manifest) return;
  const species = manifest.species.filter(
    (species) => speciesNearDepth(species, currentDepth),
  );
  target.innerHTML =
    species
      .map(
        (s) =>
          `<button class="encounter-chip ${session.has(s.aphia_id) ? "logged" : ""}" data-aphia="${s.aphia_id}"><span class="encounter-mark" aria-hidden="true">${session.has(s.aphia_id) ? "✓" : "+"}</span><span>${esc(s.common)}</span>${session.has(s.aphia_id) ? '<small>Logged</small>' : ""}</button>`,
      )
      .join("") ||
    '<p class="small-note">No verified fish in this depth band. Try moving a little shallower or deeper.</p>';
  target.querySelectorAll<HTMLButtonElement>("[data-aphia]").forEach(
    (b) =>
      (b.onclick = () => {
        const s = species.find((s) => s.aphia_id === Number(b.dataset.aphia));
        if (s) void encounter(s);
      }),
  );
}
async function encounter(species: Species) {
  if (!manifest) return;
  survey?.record(currentDepth, species);
  renderSurveyProgress();
  if (!session.has(species.aphia_id)) {
    session.add(species.aphia_id);
    seenThisDive.push(species);
  }
  if (
    !logs.some(
      (l) =>
        l.aphia_id === species.aphia_id && l.place === manifest!.place.name,
    )
  ) {
    logs.push({
      aphia_id: species.aphia_id,
      name: species.name,
      common: species.common,
      rarity: species.rarity,
      place: manifest.place.name,
      date: new Date().toISOString(),
    });
    saveLogs();
  }
  document.querySelector("#found")!.innerHTML =
    `${session.size} <small>/ ${manifest.species.length}</small>`;
  document.querySelector(".count")!.textContent = String(
    new Set(logs.map((l) => l.aphia_id)).size,
  );
  const focusedEncounter = document.activeElement?.getAttribute("data-aphia");
  renderEncounterButtons();
  if (focusedEncounter === String(species.aphia_id)) {
    document.querySelector<HTMLButtonElement>(`[data-aphia="${species.aphia_id}"]`)?.focus();
  }
  openModal(
    `<p class="eyebrow">DISCOVERY LOGGED ✓</p><h2>${esc(species.common)}</h2><p class="loading-card">Opening your field notes…</p>`,
  );
  const token = ++cardToken;
  try {
    const card = publicDemo ? demoCards[species.aphia_id] : await api<Card>(
      `/v1/species/${species.aphia_id}?dive_id=${manifest.id}`,
    );
    if (token !== cardToken || !modal().open) return;
    openModal(`<div class="species-card">
      <div class="card-body"><div class="card-topline"><p class="eyebrow">DISCOVERY LOGGED ✓</p><span class="rarity ${card.rarity}">${card.rarity}</span></div><h2>${esc(card.common)}</h2><a class="scientific" href="${safeURL(card.taxonomy_url)}" target="_blank" rel="noopener noreferrer">${esc(card.name)} ↗</a>
      ${card.photo_link ? `<p class="small-note"><a href="${safeURL(card.photo_link)}" target="_blank" rel="noopener noreferrer">View the original photo on iNaturalist ↗</a></p>` : ""}
      <dl>${card.facts.map((f) => `<div><dt>${esc(f.label)}</dt><dd>${esc(f.value)} <a href="${safeURL(f.source_url)}" title="FishBase ${esc(f.release)}" aria-label="Source for ${esc(f.label)}" target="_blank" rel="noopener noreferrer">↗</a></dd></div>`).join("")}<div><dt>Diet / conservation status</dt><dd>No sourced data yet</dd></div></dl>
      <section class="evidence"><p class="eyebrow">SEEN HERE · ${esc(card.place_name)}</p><p><b>${card.evidence.obis_records}</b> qualifying records in this sample.<br>Latest observation: ${card.evidence.latest_year}.</p>
      <div class="source-links">${card.evidence.record_urls.map((u, i) => `<a href="${safeURL(u)}" target="_blank" rel="noopener noreferrer">OBIS record ${i + 1} ↗</a>`).join("")}</div><details><summary>Dataset credits & evidence scope</summary><p>${esc(card.evidence.scope)}</p><ul>${card.dataset_credits.map((dataset) => `<li><a href="${safeURL(dataset.source_url)}" target="_blank" rel="noopener noreferrer">${esc(dataset.title)} · citation ↗</a> · <a href="${safeURL(dataset.license_url)}" target="_blank" rel="noopener noreferrer">${esc(dataset.license)} ↗</a></li>`).join("")}</ul></details></section><p class="small-note">Rarity is relative to this record sample. It is not a conservation assessment.</p></div></div>`);
    if (publicDemo) return;
    const guideButton = document.createElement("button");
    guideButton.className = "guide-button";
    guideButton.textContent = "Ask the Guide";
    guideButton.addEventListener("click", () => {
      if (manifest) askGuide(manifest, species);
    });
    modal().querySelector(".card-body")!.append(guideButton);
  } catch (error) {
    if (token === cardToken && modal().open)
      openModal(
        `<h2>${esc(species.common)}</h2><p>Discovery logged. The species card could not be loaded.</p><p class="small-note">${esc(error instanceof Error ? error.message : "")}</p>`,
      );
  }
}
interface GuideAnswer {
  mode: "rag" | "records";
  message: string | null;
  evidence: Array<{ text: string; source: string; url: string }>;
}

function askGuide(data: Manifest, species?: Species) {
  ++cardToken;
  const example = species
    ? `How big does ${species.common} get?`
    : "Which fish have been recorded here?";
  openModal(`<section class="guide-dialog">
    <h2>Ask the Guide</h2>
    ${species ? `<p class="small-note">${esc(species.common)}</p>` : ""}
    <form id="guide-form">
      <label for="guide-question">Your question about this dive</label>
      <input id="guide-question" name="question" required minlength="3" maxlength="300" placeholder="${esc(example)}">
      <button class="primary" type="submit">Ask</button>
    </form>
    <div id="guide-answer" role="status" aria-live="polite"></div>
  </section>`);
  const dialog = modal();
  const form = dialog.querySelector<HTMLFormElement>("#guide-form")!;
  const question = form.querySelector<HTMLInputElement>("#guide-question")!;
  const submit = form.querySelector<HTMLButtonElement>("button")!;
  const answer = dialog.querySelector<HTMLDivElement>("#guide-answer")!;
  question.focus();
  form.onsubmit = async (event) => {
    event.preventDefault();
    const text = question.value.trim();
    if (text.length < 3) {
      answer.textContent = "Enter a question with at least three characters.";
      return;
    }
    const token = ++cardToken;
    submit.disabled = true;
    answer.textContent = "Looking up dive records…";
    try {
      const result = await api<GuideAnswer>(`/v1/dives/${data.id}/ask`, {
        question: text,
        aphia_id: species?.aphia_id,
      });
      if (token !== cardToken || !dialog.open) return;
      if (result.message) {
        answer.textContent = result.message;
        return;
      }
      answer.innerHTML = `<ol>${result.evidence.map((item) =>
        `<li>${esc(item.text)} <a href="${safeURL(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.source)} ↗</a></li>`,
      ).join("")}</ol>${result.mode === "records" ? '<p class="small-note">Record lookup</p>' : ""}`;
    } catch (error) {
      if (token === cardToken && dialog.open)
        answer.textContent = error instanceof Error ? error.message : "The guide is unavailable.";
    } finally {
      submit.disabled = false;
    }
  };
}

function surface(timerExpired = false) {
  if (!manifest || !ocean) {
    home();
    return;
  }
  const data = manifest,
    discovered = [...seenThisDive];
  const finishedSurvey = survey;
  ocean.finish();
  dispose();
  shell(`<main class="summary"><p class="eyebrow">BACK IN THE SUNLIGHT</p><h1>A little more<br><em>connected.</em></h1><p class="lede">${esc(data.place.name)} · ${discovered.length} species discovered</p>
    ${finishedSurvey ? `<p>${finishedSurvey.completed === finishedSurvey.stops.length ? "Depth survey complete." : timerExpired ? "Air timer expired. Survey incomplete." : "Surfaced before completing the survey."} ${finishedSurvey.completed} of ${finishedSurvey.stops.length} stops logged.</p>` : ""}
    <div class="summary-grid">${discovered.map((s) => `<div><span class="rarity ${s.rarity}">${s.rarity}</span><h3>${esc(s.common)}</h3><i>${esc(s.name)}</i></div>`).join("") || "<p>The ocean will be here when you’re ready. Click a fish next time to log your first encounter.</p>"}</div>
    <button class="primary" id="again">Explore another place <span>↗</span></button><button class="text-button" id="repeat">${finishedSurvey ? "Repeat depth survey" : "Dive here again"}</button><button class="text-button" id="sequences">Choose a dive sequence</button><p class="small-note">Your Fishdex is saved in this browser.</p></main>`);
  document.querySelector("#again")!.addEventListener("click", home);
  document
    .querySelector("#repeat")!
    .addEventListener("click", () => startDive(data, finishedSurvey?.stops));
  document.querySelector("#sequences")!.addEventListener("click", () => confirmDive(data));
}
function logbook() {
  openModal(
    `<p class="eyebrow">YOUR OCEAN, REMEMBERED</p><h2>Fishdex<span class="period">.</span></h2><p class="small-note">${new Set(logs.map((l) => l.aphia_id)).size} species · Saved in this browser</p><div class="log-list">${
      [...logs]
        .reverse()
        .map(
          (l) =>
            `<article><span class="rarity ${esc(l.rarity)}">${esc(l.rarity)}</span><h3>${esc(l.common)}</h3><i>${esc(l.name)}</i><p>${esc(l.place)} · ${new Date(l.date).toLocaleDateString()}</p></article>`,
        )
        .join("") ||
      "<p>Your collection starts with a little curiosity. Enter the water and click a fish.</p>"
    }</div>`,
  );
}
function credits() {
  openModal(
    `<h2>Sources and licenses</h2>
    <p>Place data: Flanders Marine Institute (2026), <a href="https://www.marineregions.org" target="_blank" rel="noopener noreferrer">MarineRegions.org</a> · <a href="https://www.marineregions.org/disclaimer.php" target="_blank" rel="noopener noreferrer">CC BY and citation terms</a>. Divepoint derives search areas from gazetteer records.</p>
    <p>Occurrence data: <a href="https://obis.org" target="_blank" rel="noopener noreferrer">Ocean Biodiversity Information System, IOC-UNESCO</a> and its data contributors. Species cards link to the original dataset citations and licenses. Divepoint filters the records by place, depth, season, and quality and summarizes them for play.</p>
    <p>Taxonomy: WoRMS Editorial Board (2026), World Register of Marine Species, VLIZ · <a href="https://doi.org/10.14284/170" target="_blank" rel="noopener noreferrer">doi:10.14284/170</a> · <a href="https://www.marinespecies.org/about.php" target="_blank" rel="noopener noreferrer">CC BY and citation terms</a>.</p>
    <p>Fish data: Froese, R. and D. Pauly, editors (2026), <a href="https://www.fishbase.se" target="_blank" rel="noopener noreferrer">FishBase</a>, v26.06, via <a href="https://source.coop/cboettig/fishbase" target="_blank" rel="noopener noreferrer">Source Cooperative</a> · <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC 4.0</a>. Divepoint extracts and formats selected data for this noncommercial demo.</p>
    <p>Terrain: GEBCO Bathymetric Compilation Group (2026), <a href="https://doi.org/10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa" target="_blank" rel="noopener noreferrer">The GEBCO_2026 Grid</a> · <a href="https://www.gebco.net/data-products/gridded-bathymetry/terms-of-use" target="_blank" rel="noopener noreferrer">Terms of use</a>. Divepoint uses extracted and rescaled terrain for the simulation.</p>
    <p>Photo links open the original iNaturalist page, where the photographer and any reuse license are listed.</p>
    <p class="small-note">Game simulation. Depth and terrain are unsuitable for navigation or dive planning.</p>`,
  );
}
home();
