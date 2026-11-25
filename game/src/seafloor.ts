import Phaser from "phaser";

type Vertex = { x: number; y: number; elevation: number };
const EDGE_SAMPLES = 65;

export function drawSeafloor(
  graphics: Phaser.GameObjects.Graphics,
  depthsM: number[][],
  width: number,
  height: number,
  depth: number,
  redSea: boolean,
) {
  const rowCount = depthsM.length;
  const columnCount = depthsM[0].length;
  const depths = depthsM.flat();
  const shallowest = Math.min(...depths);
  const relief = Math.max(1, Math.max(...depths) - shallowest);
  const cameraHeight = 0.40 - 0.16 * (depth / 60);

  // West-to-east grid columns are x; north-to-south rows approach the camera.
  const projected = depthsM.map((row, y) => {
    const forward = 1 - y / (rowCount - 1);
    const perspective = 1.5 / (1.1 + forward * 1.8);
    return row.map((meters, x) => {
      const elevation = -(meters - shallowest) / relief;
      return {
        x: width * (0.5 + (x / (columnCount - 1) - 0.5) * 1.52 * perspective),
        y: height * (0.36 + (cameraHeight - elevation * 0.34) * perspective),
        elevation,
      };
    });
  });

  const near = projected[rowCount - 1];
  graphics.fillStyle(redSea ? 0x132e41 : 0x103239);
  graphics.fillPoints([
    ...near,
    { x: near[columnCount - 1].x, y: height * 2 },
    { x: near[0].x, y: height * 2 },
  ], true);

  const color = redSea ? [94, 155, 164] : [81, 169, 149];
  function face(a: Vertex, b: Vertex, c: Vertex, distance: number, lower: boolean) {
    const direction = lower ? -1 : 1;
    const eastSlope = (b.elevation - a.elevation) * (columnCount - 1) * direction;
    const southSlope = (c.elevation - a.elevation) * (rowCount - 1) * direction;
    const light = Phaser.Math.Clamp(0.68 - eastSlope * 0.045 - southSlope * 0.045, 0.35, 1.12);
    const shade = light * (1 - 0.40 * distance);
    graphics.fillStyle(Phaser.Display.Color.GetColor(
      Math.round(color[0] * shade),
      Math.round(color[1] * shade),
      Math.round(color[2] * shade),
    ));
    graphics.fillTriangle(a.x, a.y, b.x, b.y, c.x, c.y);
  }

  // Paint the distant rows first so nearby relief overlaps them.
  for (let row = 0; row < rowCount - 1; row++) {
    const distance = 1 - row / (rowCount - 1);
    for (let col = 0; col < columnCount - 1; col++) {
      const nw = projected[row][col];
      const ne = projected[row][col + 1];
      const sw = projected[row + 1][col];
      const se = projected[row + 1][col + 1];
      face(nw, ne, sw, distance, false);
      face(se, sw, ne, distance, true);
    }
  }
  graphics.lineStyle(1, redSea ? 0x95bdc2 : 0x9bcec0, 0.38);
  graphics.strokePoints(near);

  // The topmost projected edge keeps foreground fish in the water above the mesh.
  const waterEdge = Array.from({ length: EDGE_SAMPLES }, (_, i) => {
    const x = width * i / (EDGE_SAMPLES - 1);
    let top = height;
    for (const row of projected) {
      const left = row[0].x;
      const right = row[columnCount - 1].x;
      if (x < left || x > right) continue;
      const col = (x - left) / (right - left) * (columnCount - 1);
      const index = Math.floor(col);
      const y = Phaser.Math.Linear(
        row[index].y,
        row[Math.min(index + 1, columnCount - 1)].y,
        col - index,
      );
      top = Math.min(top, y);
    }
    return top;
  });

  return { waterEdge, projected };
}
