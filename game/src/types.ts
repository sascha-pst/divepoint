export type DiveScenery = "open-sea" | "red-sea" | "raja-ampat" | "kelp";

export interface Place {
  name: string;
  mrgid: number;
  latitude: number;
  longitude: number;
  bounds: number[];
  source_url: string;
  area_kind: string;
  geometry_wkt: string;
}
export interface Species {
  aphia_id: number;
  name: string;
  common: string;
  family: string;
  body_shape: string | null;
  zone: string;
  depth_m: [number, number];
  weight: number;
  rarity: "common" | "uncommon" | "rare" | "legendary";
  evidence: {
    obis_records: number;
    latest_year: number;
    record_urls: string[];
    dataset_urls: string[];
    source_url: string;
    scope: string;
  };
}
export interface Manifest {
  id: string;
  type: "dive" | "too_sparse";
  place: Place;
  species: Species[];
  filters: { depth_m: [number, number]; months: number[] };
  source_mode: "recorded" | "live";
  captured_at: string | null;
  message: string;
  notice: string;
  sample_size: number;
}
export interface Card extends Species {
  photo_link: string | null;
  dataset_credits: {
    title: string;
    source_url: string;
    license: string;
    license_url: string;
  }[];
  facts: {
    label: string;
    value: string;
    source_url: string;
    release: string;
  }[];
  taxonomy_url: string;
  place_name: string;
  missing_facts: string[];
}
export interface LogEntry {
  aphia_id: number;
  name: string;
  common: string;
  place: string;
  date: string;
  rarity: string;
}
