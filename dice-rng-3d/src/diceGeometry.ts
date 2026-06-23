import * as THREE from "three";
import * as CANNON from "cannon-es";

export type DiceModel = {
  sides: number;
  vertices: THREE.Vector3[];
  faces: number[][];
  faceNormals: THREE.Vector3[];
  faceCenters: THREE.Vector3[];
  geometry: THREE.BufferGeometry;
  shape: CANNON.ConvexPolyhedron;
};

const PHI = (1 + Math.sqrt(5)) / 2;

function normalizeVertices(vertices: THREE.Vector3[]): THREE.Vector3[] {
  const max = Math.max(...vertices.map((vertex) => vertex.length()));
  return vertices.map((vertex) => vertex.clone().multiplyScalar(1 / max));
}

function orientFace(face: number[], vertices: THREE.Vector3[]): number[] {
  const center = face.reduce((sum, index) => sum.add(vertices[index]), new THREE.Vector3()).multiplyScalar(1 / face.length);
  const a = vertices[face[0]];
  const b = vertices[face[1]];
  const c = vertices[face[2]];
  const normal = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a));
  return normal.dot(center) < 0 ? [...face].reverse() : face;
}

function buildModel(sides: number, rawVertices: THREE.Vector3[], rawFaces: number[][]): DiceModel {
  const vertices = normalizeVertices(rawVertices);
  const faces = rawFaces.map((face) => orientFace(face, vertices));
  const positions: number[] = [];
  const normals: number[] = [];
  const faceNormals: THREE.Vector3[] = [];
  const faceCenters: THREE.Vector3[] = [];

  for (const face of faces) {
    const center = face.reduce((sum, index) => sum.add(vertices[index]), new THREE.Vector3()).multiplyScalar(1 / face.length);
    const normal = center.clone().normalize();
    faceNormals.push(normal);
    faceCenters.push(center);

    for (let i = 1; i < face.length - 1; i += 1) {
      for (const index of [face[0], face[i], face[i + 1]]) {
        const vertex = vertices[index];
        positions.push(vertex.x, vertex.y, vertex.z);
        normals.push(normal.x, normal.y, normal.z);
      }
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.computeBoundingSphere();

  const shape = new CANNON.ConvexPolyhedron({
    vertices: vertices.map((vertex) => new CANNON.Vec3(vertex.x, vertex.y, vertex.z)),
    faces
  });

  return { sides, vertices, faces, faceNormals, faceCenters, geometry, shape };
}

function cube(): DiceModel {
  return buildModel(
    6,
    [
      new THREE.Vector3(-1, -1, -1),
      new THREE.Vector3(1, -1, -1),
      new THREE.Vector3(1, 1, -1),
      new THREE.Vector3(-1, 1, -1),
      new THREE.Vector3(-1, -1, 1),
      new THREE.Vector3(1, -1, 1),
      new THREE.Vector3(1, 1, 1),
      new THREE.Vector3(-1, 1, 1)
    ],
    [
      [0, 3, 2, 1],
      [4, 5, 6, 7],
      [0, 1, 5, 4],
      [3, 7, 6, 2],
      [1, 2, 6, 5],
      [0, 4, 7, 3]
    ]
  );
}

function tetrahedron(): DiceModel {
  return buildModel(
    4,
    [
      new THREE.Vector3(1, 1, 1),
      new THREE.Vector3(-1, -1, 1),
      new THREE.Vector3(-1, 1, -1),
      new THREE.Vector3(1, -1, -1)
    ],
    [
      [0, 1, 2],
      [0, 3, 1],
      [0, 2, 3],
      [1, 3, 2]
    ]
  );
}

function octahedron(): DiceModel {
  return buildModel(
    8,
    [
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(-1, 0, 0),
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(0, -1, 0),
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(0, 0, -1)
    ],
    [
      [0, 2, 4],
      [2, 1, 4],
      [1, 3, 4],
      [3, 0, 4],
      [2, 0, 5],
      [1, 2, 5],
      [3, 1, 5],
      [0, 3, 5]
    ]
  );
}

function icosahedron(): DiceModel {
  const vertices = [
    new THREE.Vector3(-1, PHI, 0),
    new THREE.Vector3(1, PHI, 0),
    new THREE.Vector3(-1, -PHI, 0),
    new THREE.Vector3(1, -PHI, 0),
    new THREE.Vector3(0, -1, PHI),
    new THREE.Vector3(0, 1, PHI),
    new THREE.Vector3(0, -1, -PHI),
    new THREE.Vector3(0, 1, -PHI),
    new THREE.Vector3(PHI, 0, -1),
    new THREE.Vector3(PHI, 0, 1),
    new THREE.Vector3(-PHI, 0, -1),
    new THREE.Vector3(-PHI, 0, 1)
  ];
  const faces = [
    [0, 11, 5],
    [0, 5, 1],
    [0, 1, 7],
    [0, 7, 10],
    [0, 10, 11],
    [1, 5, 9],
    [5, 11, 4],
    [11, 10, 2],
    [10, 7, 6],
    [7, 1, 8],
    [3, 9, 4],
    [3, 4, 2],
    [3, 2, 6],
    [3, 6, 8],
    [3, 8, 9],
    [4, 9, 5],
    [2, 4, 11],
    [6, 2, 10],
    [8, 6, 7],
    [9, 8, 1]
  ];
  return buildModel(20, vertices, faces);
}

function dodecahedron(): DiceModel {
  const ico = icosahedron();
  const vertices = ico.faceCenters.map((center) => center.clone().normalize());
  const faces: number[][] = [];

  for (let vertexIndex = 0; vertexIndex < ico.vertices.length; vertexIndex += 1) {
    const adjacent = ico.faces
      .map((face, faceIndex) => ({ face, faceIndex }))
      .filter(({ face }) => face.includes(vertexIndex))
      .map(({ faceIndex }) => faceIndex);
    faces.push(adjacent);
  }

  return buildModel(12, vertices, faces);
}

function bipyramid(sides: number): DiceModel {
  const ringCount = sides / 2;
  const vertices = [new THREE.Vector3(0, 1.25, 0), new THREE.Vector3(0, -1.25, 0)];
  for (let i = 0; i < ringCount; i += 1) {
    const angle = (i / ringCount) * Math.PI * 2;
    vertices.push(new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle)));
  }
  const faces: number[][] = [];
  for (let i = 0; i < ringCount; i += 1) {
    const a = 2 + i;
    const b = 2 + ((i + 1) % ringCount);
    faces.push([0, a, b], [1, b, a]);
  }
  return buildModel(sides, vertices, faces);
}

function prism(sides: number): DiceModel {
  const ringCount = Math.max(3, sides - 2);
  const vertices: THREE.Vector3[] = [];
  for (const y of [-0.72, 0.72]) {
    for (let i = 0; i < ringCount; i += 1) {
      const angle = (i / ringCount) * Math.PI * 2 + Math.PI / ringCount;
      vertices.push(new THREE.Vector3(Math.cos(angle), y, Math.sin(angle)));
    }
  }

  const bottom = [...Array(ringCount).keys()].reverse();
  const top = [...Array(ringCount).keys()].map((index) => ringCount + index);
  const faces: number[][] = [bottom, top];
  for (let i = 0; i < ringCount; i += 1) {
    const next = (i + 1) % ringCount;
    faces.push([i, next, ringCount + next, ringCount + i]);
  }
  return buildModel(sides, vertices, faces);
}

export function createDiceModel(sides: number): DiceModel {
  const normalized = Math.max(4, Math.min(100, Math.round(sides)));
  if (normalized === 4) return tetrahedron();
  if (normalized === 6) return cube();
  if (normalized === 8) return octahedron();
  if (normalized === 12) return dodecahedron();
  if (normalized === 20) return icosahedron();
  if (normalized % 2 === 0) return bipyramid(normalized);
  return prism(normalized);
}

export function topFaceValue(model: DiceModel, quaternion: THREE.Quaternion): number {
  let bestFace = 0;
  let bestDot = -Infinity;
  const up = new THREE.Vector3(0, 1, 0);

  model.faceNormals.forEach((normal, index) => {
    const worldNormal = normal.clone().applyQuaternion(quaternion);
    const dot = worldNormal.dot(up);
    if (dot > bestDot) {
      bestDot = dot;
      bestFace = index;
    }
  });

  return bestFace + 1;
}
