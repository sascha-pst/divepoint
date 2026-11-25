import Phaser from "phaser";
import { speciesNearDepth } from "./sequences";
import { drawSeafloor } from "./seafloor";
import type { DiveScenery, Manifest, Species } from "./types";

type Swimmer = {
  image: Phaser.GameObjects.Image;
  species: Species;
  vx: number;
  phase: number;
  heightFraction: number;
};
const palette = [0xe5bb75, 0xa4c8be, 0xb3b5a6, 0xb9aaa4, 0x92aab7, 0xcbd8ab];
const clamp = Phaser.Math.Clamp;

export class Ocean extends Phaser.Scene {
  private swimmers: Swimmer[] = [];
  private kelp?: Phaser.GameObjects.Graphics;
  private scenery!: Phaser.GameObjects.Graphics;
  private particles: Phaser.GameObjects.Arc[] = [];
  private waterEdge: number[] = [];
  private elapsed = 0;
  private seconds = 240;
  private lastSecond = -1;
  private cameraDepth = 15;
  private selectedDepth = 15;
  private stopped = false;
  private frozen = false;
  private clock = 0;
  private reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  constructor(
    private manifest: Manifest,
    private habitat: DiveScenery,
    private initialDepth: number,
    private seafloorDepthsM: number[][] | undefined,
    private encounter: (species: Species) => void,
    private air: (seconds: number) => void,
    private depthChanged: (depth: number) => void,
    private surfaced: () => void,
  ) {
    super("dive");
  }

  create() {
    this.cameraDepth = this.selectedDepth = this.initialDepth;
    this.scenery = this.add.graphics();
    if (this.habitat === "kelp") this.kelp = this.add.graphics();
    this.makeScenery();
    this.scale.on("resize", this.makeScenery, this);
    for (let i = 0; i < 38; i++) {
      const bubble = this.add.circle(
        Math.random() * this.scale.width,
        Math.random() * this.scale.height,
        0.8 + Math.random() * 1.5,
        0xb9e8dc,
        0.15 + Math.random() * 0.16,
      );
      this.particles.push(bubble);
    }
    const handleDepthKey = (event: KeyboardEvent) => {
      if (this.frozen || this.stopped || document.hidden) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(target.tagName)
      ) return;
      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        event.preventDefault();
        this.setDepth(this.selectedDepth + (event.key === "ArrowDown" ? 1 : -1));
      }
    };
    window.addEventListener("keydown", handleDepthKey);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () =>
      window.removeEventListener("keydown", handleDepthKey),
    );
    this.spawn();
    this.depthChanged(this.selectedDepth);
  }

  private makeScenery = () => {
    const { width: w, height: h } = this.scale;
    const g = this.scenery;
    g.clear();
    if (w <= 0 || h <= 0) return;
    if (this.habitat === "open-sea") {
      g.fillStyle(0xa2dcf3, 0.045);
      for (let i = 0; i < 7; i++) {
        const x = w * (0.22 + i * 0.09);
        g.fillTriangle(x, 0, x + w * 0.045, 0, x + w * (i - 3) * 0.09, h);
      }
      return;
    }
    if (this.seafloorDepthsM) {
      this.drawReef(w, h, this.seafloorDepthsM);
      return;
    }
    // Decorative habitat, never a species occurrence.
    g.fillStyle(0x0e4c50, 0.55);
    g.fillEllipse(w * 0.12, h + 35, w * 0.8, 250);
    g.fillStyle(0x062d38, 0.75);
    g.fillEllipse(w * 0.8, h + 65, w * 0.95, 260);
    g.fillStyle(0x71c9bb, 0.035);
    for (let i = 0; i < 6; i++) {
      const x = w * (i / 6);
      g.fillTriangle(x, 0, x + w * 0.08, 0, x - w * 0.3, h);
    }
    g.fillStyle(0x123d42, 0.8);
    [0.08, 0.23, 0.7, 0.94].forEach((x, i) =>
      g.fillEllipse(w * x, h - 6 + i * 3, 120, 48),
    );
  };

  private drawReef(w: number, h: number, depthsM: number[][]) {
    const wall = this.habitat === "red-sea";
    const g = this.scenery;
    g.fillStyle(wall ? 0x8bddff : 0x99ffe7, 0.065);
    for (let i = 0; i < 6; i++) {
      const x = w * (0.15 + 0.14 * i);
      g.fillTriangle(x, 0, x + w * 0.05, 0, x - w * 0.25, h);
    }

    const { waterEdge, projected } = drawSeafloor(g, depthsM, w, h, this.selectedDepth, wall);
    this.waterEdge = waterEdge;

    // Illustrative coral is anchored to projected grid cells.
    const coralColors = wall
      ? [0xd69c72, 0xe98f7d, 0xb285a0]
      : [0xf1ad79, 0xdf8eb0, 0x9b8ccc, 0xd97977];
    const count = wall ? 10 : 24;
    const scale = Math.min(w, h);
    for (let i = 0; i < count; i++) {
      const row = Math.floor((0.25 + ((i * 7) % 13) / 24) * (projected.length - 1));
      const col = Math.floor((0.04 + 0.92 * i / count) * (projected[row].length - 1));
      const { x, y } = projected[row][col];
      const height = scale * (0.027 + (i % 4) * 0.009);
      const color = coralColors[i % coralColors.length];
      if (i % 3 === 0) {
        g.fillStyle(color, 0.82);
        g.fillEllipse(x, y - height * 0.25, height * 1.45, height * 0.52);
        g.fillEllipse(x + height * 0.34, y - height * 0.66, height, height * 0.34);
        g.lineStyle(height * 0.12, color, 0.75);
        g.lineBetween(x, y, x + height * 0.2, y - height * 0.68);
      } else {
        g.lineStyle(height * 0.08, color, 0.84);
        for (let branch = -2; branch <= 2; branch++) {
          const tip = x + branch * height * 0.28;
          g.lineBetween(x, y, tip, y - height * (1 - Math.abs(branch) * 0.13));
        }
      }
    }
  }

  private texture(species: Species): string {
    const key = `fish-${species.aphia_id}`;
    if (this.textures.exists(key)) return key;
    const g = this.make.graphics({ x: 0, y: 0 });
    const color = palette[species.aphia_id % palette.length];
    const elongated = /eel|elongat/i.test(species.body_shape || "");
    const tall = /deep|short/i.test(species.body_shape || "");
    const height = elongated ? 20 : tall ? 53 : 38;
    g.fillStyle(color, 0.8);
    g.fillTriangle(15, 42, 0, 18, 0, 66);
    g.fillStyle(color, 0.55);
    g.fillTriangle(37, 32, 51, 7, 73, 28);
    g.fillStyle(color, 0.4);
    g.fillTriangle(43, 53, 56, 70, 72, 51);
    g.fillStyle(color);
    g.fillEllipse(55, 42, 86, height);
    g.fillStyle(0xffffff, 0.16);
    g.fillEllipse(55, 36, 66, height * 0.4);
    g.fillStyle(0x163b3c, 0.2);
    g.fillTriangle(46, 42, 62, 59, 67, 43);
    g.lineStyle(1, 0x12383d, 0.3);
    g.lineBetween(79, 32, 77, 50);
    g.fillStyle(0x102c32);
    g.fillCircle(87, 36, 3);
    g.fillStyle(0xf2f4d9);
    g.fillCircle(88, 35, 1);
    g.lineStyle(1, 0x24494a, 0.5);
    g.lineBetween(92, 44, 98, 44);
    g.generateTexture(key, 104, 82);
    g.destroy();
    return key;
  }

  private spawn() {
    const species = this.manifest.species;
    // Weighted sampling without replacement, so low-weight taxa remain discoverable.
    const sample = [...species]
      .map((s) => ({ s, score: -Math.log(Math.random() || 0.001) / s.weight }))
      .sort((a, b) => a.score - b.score)
      .slice(0, 16)
      .map((x) => x.s);
    sample.forEach((s, index) => {
      const key = this.texture(s);
      const heightFraction = 0.2 + Math.random() * 0.6;
      const image = this.add.image(
        Math.random() * this.scale.width,
        heightFraction * this.scale.height,
        key,
      );
      image.setScale(0.65 + (s.aphia_id % 7) * 0.12);
      image.setInteractive({ useHandCursor: true });
      image.on("pointerover", () => {
        image.setTint(0xffffff);
        image.setAlpha(1);
      });
      image.on("pointerout", () => image.clearTint());
      image.on("pointerdown", () => {
        if (!this.frozen && !this.stopped && image.visible) this.encounter(s);
      });
      const vx = (index % 2 ? 1 : -1) * (12 + (index % 5) * 6);
      image.setFlipX(vx < 0);
      this.swimmers.push({
        image,
        species: s,
        vx,
        phase: index * 0.8,
        heightFraction,
      });
    });
  }

  setDepth(depth: number) {
    this.selectedDepth = clamp(depth, 0, this.manifest.filters.depth_m[1]);
    if (this.seafloorDepthsM) this.makeScenery();
    this.depthChanged(Math.round(this.selectedDepth));
  }
  pauseDive(paused: boolean) {
    this.frozen = paused;
    if (this.input.keyboard) this.input.keyboard.enabled = !paused;
  }
  finish() {
    this.stopped = true;
  }
  availableSpecies() {
    return this.manifest.species.filter((species) => speciesNearDepth(species, this.selectedDepth));
  }

  update(_time: number, delta: number) {
    if (!this.scenery) return;
    const dt = Math.min(delta, 100) / 1000;
    if (document.hidden || this.frozen || this.stopped) return;
    this.elapsed += dt;
    this.clock += dt;
    this.cameraDepth += (this.selectedDepth - this.cameraDepth) * 0.05;
    this.seconds = Math.max(0, 240 - this.elapsed);
    if (Math.ceil(this.seconds) !== this.lastSecond) {
      this.lastSecond = Math.ceil(this.seconds);
      this.air(this.lastSecond);
    }
    if (this.seconds <= 0) {
      this.stopped = true;
      this.surfaced();
      return;
    }
    const w = this.scale.width,
      h = this.scale.height;
    const motion = this.reduceMotion ? 0.1 : 1;
    this.kelp?.clear();
    for (let i = 0; this.kelp && i < 13; i++) {
      const base = (i * 0.083 + 0.01) * w;
      const tall = 100 + ((i * 73) % 210);
      const sway = Math.sin(this.clock * 0.6 * motion + i) * 15;
      this.kelp.lineStyle(3, i % 2 ? 0x638d66 : 0x3c745c, 0.55);
      this.kelp.beginPath();
      this.kelp.moveTo(base, h);
      for (let j = 1; j < 10; j++)
        this.kelp.lineTo(base + (sway * j) / 9, h - (tall * j) / 9);
      this.kelp.strokePath();
      for (let j = 1; j < 7; j++) {
        const x = base + (sway * j) / 7,
          y = h - (tall * j) / 7;
        this.kelp.fillStyle(j % 2 ? 0x477f60 : 0x6c9067, 0.6);
        this.kelp.fillEllipse(x + (j % 2 ? 10 : -10), y, 26, 8);
      }
    }
    for (const bubble of this.particles) {
      bubble.y -= dt * 9 * motion;
      if (bubble.y < 0) {
        bubble.y = h;
        bubble.x = Math.random() * w;
      }
    }
    for (const fish of this.swimmers) {
      fish.image.setVisible(speciesNearDepth(fish.species, this.selectedDepth));
      fish.image.x += fish.vx * dt * motion;
      fish.image.y =
        fish.heightFraction * h +
        Math.sin(this.clock * 0.8 * motion + fish.phase) * 8;
      if (this.waterEdge.length && w > 0) {
        const column = Math.round(clamp(fish.image.x / w, 0, 1) * (this.waterEdge.length - 1));
        fish.image.y = Math.min(fish.image.y, this.waterEdge[column] - fish.image.displayHeight / 2);
      }
      fish.image.setAlpha(0.72 + Math.sin(this.clock + fish.phase) * 0.1);
      if (fish.image.x > w + 100) fish.image.x = -80;
      if (fish.image.x < -100) fish.image.x = w + 80;
    }
    const canvas = this.game.canvas;
    canvas.style.filter = `brightness(${1 - this.cameraDepth / 140})`;
  }
}
