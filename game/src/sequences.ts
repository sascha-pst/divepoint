import type { Manifest, Species } from "./types";

export function speciesNearDepth(species: Species, depth: number): boolean {
  return species.depth_m[0] <= depth + 5 && species.depth_m[1] >= depth - 5;
}

export function surveyStops(manifest: Manifest): number[] {
  const [min, max] = manifest.filters.depth_m;
  const supportedDepths: number[] = [];
  for (let depth = Math.ceil(min); depth <= Math.floor(max); depth++) {
    if (manifest.species.some((species) => speciesNearDepth(species, depth))) {
      supportedDepths.push(depth);
    }
  }

  const shallow = supportedDepths[0];
  const deep = supportedDepths.at(-1);
  if (shallow === undefined || deep === undefined || deep - shallow < 10) {
    return [];
  }

  const middle = supportedDepths
    .filter((depth) => depth >= shallow + 10 && depth <= deep - 10)
    .reduce<number | undefined>((closest, depth) => {
      const midpoint = (shallow + deep) / 2;
      return closest === undefined || Math.abs(depth - midpoint) < Math.abs(closest - midpoint)
        ? depth
        : closest;
    }, undefined);
  return middle === undefined ? [shallow, deep] : [shallow, middle, deep];
}

export class DepthSurvey {
  completed = 0;

  constructor(readonly stops: readonly number[]) {}

  get target(): number | undefined {
    return this.stops[this.completed];
  }

  record(depth: number, species: Species) {
    if (depth === this.target && speciesNearDepth(species, depth)) {
      this.completed++;
    }
  }
}
