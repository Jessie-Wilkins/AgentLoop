from __future__ import annotations

import json
import base64
import mimetypes
import re
import shutil
import subprocess  # nosec B404
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from agentloop.core.engine import DryRunResult, execute_loop
from agentloop.security.redaction import redact_mapping, secret_names
from agentloop.storage.configs import (
    ConfigError,
    copy_template,
    create_template,
    default_template_data,
    find_config,
    list_configs,
    load_loop,
    validate_config_name,
    write_loop_config,
    write_template,
)
from agentloop.storage.runs import find_run, list_runs, read_rerun_request, request_stop
from agentloop.storage.paths import apps_dir, uploads_dir


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
APP_FILE_SUFFIXES = {".html", ".css", ".js", ".mjs", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".txt", ".map", ".wasm"}
URL_PATTERN = re.compile(r"https?://[^\s)'\"<>`]+")
APP_URL_PATTERN = re.compile(r"/apps/[A-Za-z0-9_.-]+/?")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")


DICE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>3D Dice RNG</title>
  <link rel="icon" href="data:,">
  <style>
    :root {
      color-scheme: light;
      --ink:#111827;
      --muted:#5f6877;
      --line:#d7dce4;
      --panel:#ffffff;
      --accent:#0f766e;
      --shadow:0 18px 45px rgba(17, 24, 39, .12);
    }
    * { box-sizing:border-box; }
    html, body { height:100%; }
    body {
      margin:0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      color:var(--ink);
      background:#ffffff;
      overflow:hidden;
    }
    .app {
      min-height:100%;
      display:grid;
      grid-template-rows:auto minmax(0, 1fr);
      background:linear-gradient(#ffffff, #f8fafc);
    }
    .toolbar {
      display:grid;
      grid-template-columns:1fr auto auto;
      align-items:end;
      gap:12px;
      padding:12px;
      border-bottom:1px solid var(--line);
      background:rgba(255, 255, 255, .94);
      backdrop-filter:blur(10px);
      z-index:2;
    }
    .brand { min-width:0; }
    h1 { margin:0; font-size:18px; letter-spacing:0; line-height:1.2; }
    .result { color:var(--muted); font-size:13px; margin-top:3px; min-height:18px; }
    .controls { display:flex; align-items:end; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
    label { display:grid; gap:5px; color:var(--muted); font-size:12px; font-weight:650; }
    .stepper { display:grid; grid-template-columns:34px minmax(62px, 82px) 34px; gap:4px; align-items:center; }
    input {
      min-width:0;
      width:100%;
      height:34px;
      border:1px solid var(--line);
      border-radius:6px;
      padding:6px 8px;
      color:var(--ink);
      background:#ffffff;
      text-align:center;
      font:inherit;
      font-weight:650;
    }
    button {
      height:34px;
      border:1px solid var(--line);
      border-radius:6px;
      background:#ffffff;
      color:var(--ink);
      font:inherit;
      font-weight:700;
      cursor:pointer;
    }
    .stepper button { width:34px; padding:0; font-size:19px; line-height:1; }
    .roll {
      min-width:86px;
      padding:0 14px;
      border-color:var(--accent);
      background:var(--accent);
      color:#ffffff;
    }
    .stage {
      position:relative;
      min-height:0;
      overflow:hidden;
      background:#ffffff;
    }
    canvas { display:block; width:100%; height:100%; touch-action:none; }
    .readout {
      position:absolute;
      right:12px;
      bottom:12px;
      display:flex;
      gap:8px;
      flex-wrap:wrap;
      justify-content:flex-end;
      max-width:min(520px, calc(100% - 24px));
      pointer-events:none;
    }
    .chip {
      min-width:38px;
      height:30px;
      display:grid;
      place-items:center;
      border:1px solid var(--line);
      border-radius:6px;
      background:rgba(255, 255, 255, .92);
      box-shadow:var(--shadow);
      font-weight:800;
    }
    @media (max-width: 720px) {
      body { overflow:auto; }
      .app { min-height:100vh; grid-template-rows:auto minmax(440px, 1fr); }
      .toolbar { grid-template-columns:1fr; align-items:stretch; padding:10px; }
      .controls { justify-content:stretch; display:grid; grid-template-columns:1fr 1fr; }
      .roll { width:100%; grid-column:1 / -1; }
      .stepper { grid-template-columns:36px minmax(0, 1fr) 36px; }
      h1 { font-size:17px; }
    }
  </style>
</head>
<body>
  <main class="app">
    <header class="toolbar">
      <div class="brand">
        <h1>3D Dice RNG</h1>
        <div class="result" id="resultText" aria-live="polite">Ready</div>
      </div>
      <div class="controls" aria-label="Dice controls">
        <label>Sides
          <span class="stepper">
            <button type="button" data-step="sides:-1" aria-label="Decrease sides">-</button>
            <input id="sidesInput" type="number" inputmode="numeric" min="2" max="60" value="6" aria-label="Number of sides">
            <button type="button" data-step="sides:1" aria-label="Increase sides">+</button>
          </span>
        </label>
        <label>Dice
          <span class="stepper">
            <button type="button" data-step="dice:-1" aria-label="Decrease dice">-</button>
            <input id="diceInput" type="number" inputmode="numeric" min="1" max="24" value="2" aria-label="Number of dice">
            <button type="button" data-step="dice:1" aria-label="Increase dice">+</button>
          </span>
        </label>
        <button class="roll" type="button" id="rollButton">Roll</button>
      </div>
    </header>
    <section class="stage" aria-label="White 3D dice space">
      <canvas id="diceCanvas"></canvas>
      <div class="readout" id="readout"></div>
    </section>
  </main>
  <script type="importmap">
    {
      "imports": {
        "three": "https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js"
      }
    }
  </script>
  <script type="module">
    import * as THREE from 'three';
    import { RoundedBoxGeometry } from 'https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/geometries/RoundedBoxGeometry.js';
    import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/controls/OrbitControls.js';
    import * as CANNON from 'https://cdn.jsdelivr.net/npm/cannon-es@0.20.0/dist/cannon-es.js';

    const canvas = document.getElementById('diceCanvas');
    const sidesInput = document.getElementById('sidesInput');
    const diceInput = document.getElementById('diceInput');
    const resultText = document.getElementById('resultText');
    const readout = document.getElementById('readout');
    const rollButton = document.getElementById('rollButton');

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 120);
    const renderer = new THREE.WebGLRenderer({ canvas, antialias:true, alpha:false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = .08;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.minDistance = 3;
    controls.maxDistance = 70;
    controls.target.set(0, .55, 0);

    const hemi = new THREE.HemisphereLight(0xffffff, 0xd8dee8, 2.1);
    scene.add(hemi);
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(-5, 8, 7);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    scene.add(key);
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(90, 90),
      new THREE.ShadowMaterial({ color:0x000000, opacity:.12 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const world = new CANNON.World({
      gravity:new CANNON.Vec3(0, -9.82, 0),
      allowSleep:true,
    });
    world.broadphase = new CANNON.SAPBroadphase(world);
    world.solver.iterations = 14;
    const diceMaterial = new CANNON.Material('dice');
    const floorMaterial = new CANNON.Material('floor');
    world.addContactMaterial(new CANNON.ContactMaterial(diceMaterial, floorMaterial, {
      friction:.42,
      restitution:.35,
      contactEquationStiffness:1e7,
      contactEquationRelaxation:3,
    }));
    world.addContactMaterial(new CANNON.ContactMaterial(diceMaterial, diceMaterial, {
      friction:.34,
      restitution:.28,
    }));
    const floorBody = new CANNON.Body({ type:CANNON.Body.STATIC, material:floorMaterial });
    floorBody.addShape(new CANNON.Plane());
    floorBody.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
    world.addBody(floorBody);
    const wallBodies = [];

    const rng = {
      dice: [],
      sides: 6,
      count: 2,
      bounds: 8,
      rolling: false,
      lastTime: performance.now(),
    };

    const dotCache = new Map();
    const white = new THREE.MeshStandardMaterial({ color:0xffffff, roughness:.46, metalness:0.02 });

    function clamp(value, min, max) {
      value = Number.parseInt(value, 10);
      if (!Number.isFinite(value)) value = min;
      return Math.max(min, Math.min(max, value));
    }

    function pipTexture(value, maxValue) {
      const key = `${value}:${maxValue}`;
      if (dotCache.has(key)) return dotCache.get(key);
      const size = 256;
      const canvas2 = document.createElement('canvas');
      canvas2.width = size;
      canvas2.height = size;
      const ctx = canvas2.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, size, size);
      ctx.fillStyle = '#050505';
      const grid = Math.ceil(Math.sqrt(maxValue));
      const usable = size * .68;
      const start = (size - usable) / 2;
      const step = grid === 1 ? 0 : usable / (grid - 1);
      const radius = Math.max(8, Math.min(18, 66 / grid));
      const classic = {
        1:[[.5,.5]],
        2:[[.28,.28],[.72,.72]],
        3:[[.25,.25],[.5,.5],[.75,.75]],
        4:[[.28,.28],[.72,.28],[.28,.72],[.72,.72]],
        5:[[.25,.25],[.75,.25],[.5,.5],[.25,.75],[.75,.75]],
        6:[[.27,.24],[.73,.24],[.27,.5],[.73,.5],[.27,.76],[.73,.76]],
      };
      const points = classic[value] || Array.from({ length:value }, (_, index) => {
        const row = Math.floor(index / grid);
        const col = index % grid;
        return [(start + col * step) / size, (start + row * step) / size];
      });
      for (const [x, y] of points) {
        ctx.beginPath();
        ctx.arc(x * size, y * size, radius, 0, Math.PI * 2);
        ctx.fill();
      }
      const texture = new THREE.CanvasTexture(canvas2);
      texture.colorSpace = THREE.SRGBColorSpace;
      dotCache.set(key, texture);
      return texture;
    }

    function pipMaterial(value, maxValue) {
      return new THREE.MeshStandardMaterial({
        map:pipTexture(value, maxValue),
        color:0xffffff,
        roughness:.42,
        metalness:0.02,
      });
    }

    function cubeGeometry() {
      return new RoundedBoxGeometry(1.55, 1.55, 1.55, 6, .16);
    }

    function faceNormals(sides) {
      if (sides === 6) {
        return [
          { value:1, normal:new THREE.Vector3(1, 0, 0) },
          { value:6, normal:new THREE.Vector3(-1, 0, 0) },
          { value:2, normal:new THREE.Vector3(0, 1, 0) },
          { value:5, normal:new THREE.Vector3(0, -1, 0) },
          { value:3, normal:new THREE.Vector3(0, 0, 1) },
          { value:4, normal:new THREE.Vector3(0, 0, -1) },
        ];
      }
      if (sides === 2) {
        return [
          { value:1, normal:new THREE.Vector3(0, 1, 0) },
          { value:2, normal:new THREE.Vector3(0, -1, 0) },
        ];
      }
      const golden = Math.PI * (3 - Math.sqrt(5));
      return Array.from({ length:sides }, (_, i) => {
        const y = 1 - (i / Math.max(1, sides - 1)) * 2;
        const radius = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = i * golden;
        return { value:i + 1, normal:new THREE.Vector3(Math.cos(theta) * radius, y, Math.sin(theta) * radius).normalize() };
      });
    }

    function makePippedPanel(face, sides) {
      const panel = new THREE.Mesh(
        new THREE.CircleGeometry(.31, 40),
        pipMaterial(face.value, sides)
      );
      panel.position.copy(face.normal).multiplyScalar(1.265);
      panel.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), face.normal.clone().normalize());
      panel.castShadow = true;
      return panel;
    }

    function convexFromNormals(normals, radius = 1.1) {
      const vertices = [];
      const keyFor = point => `${point.x.toFixed(5)}:${point.y.toFixed(5)}:${point.z.toFixed(5)}`;
      const seen = new Set();
      for (let a = 0; a < normals.length - 2; a += 1) {
        for (let b = a + 1; b < normals.length - 1; b += 1) {
          for (let c = b + 1; c < normals.length; c += 1) {
            const n1 = normals[a].normal;
            const n2 = normals[b].normal;
            const n3 = normals[c].normal;
            const denom = n1.dot(new THREE.Vector3().crossVectors(n2, n3));
            if (Math.abs(denom) < 1e-5) continue;
            const point = new THREE.Vector3()
              .add(new THREE.Vector3().crossVectors(n2, n3).multiplyScalar(radius))
              .add(new THREE.Vector3().crossVectors(n3, n1).multiplyScalar(radius))
              .add(new THREE.Vector3().crossVectors(n1, n2).multiplyScalar(radius))
              .divideScalar(denom);
            if (normals.every(face => face.normal.dot(point) <= radius + 1e-4)) {
              const key = keyFor(point);
              if (!seen.has(key)) {
                seen.add(key);
                vertices.push(point);
              }
            }
          }
        }
      }
      const faces = normals.map((face, faceIndex) => {
        const faceVertices = vertices
          .map((point, index) => ({ point, index }))
          .filter(item => Math.abs(face.normal.dot(item.point) - radius) < 1e-3);
        const center = faceVertices.reduce((sum, item) => sum.add(item.point), new THREE.Vector3()).divideScalar(faceVertices.length || 1);
        const tangent = Math.abs(face.normal.y) > .92 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
        const u = new THREE.Vector3().crossVectors(tangent, face.normal).normalize();
        const v = new THREE.Vector3().crossVectors(face.normal, u).normalize();
        return {
          value:face.value,
          normal:face.normal,
          center,
          faceIndex,
          indices:faceVertices
            .map(item => ({
              index:item.index,
              angle:Math.atan2(item.point.clone().sub(center).dot(v), item.point.clone().sub(center).dot(u)),
            }))
            .sort((left, right) => left.angle - right.angle)
            .map(item => item.index),
        };
      }).filter(face => face.indices.length >= 3);
      const maxVertexLength = Math.max(...vertices.map(point => point.length()), 1);
      const scale = 1.18 / maxVertexLength;
      for (const point of vertices) point.multiplyScalar(scale);
      for (const face of faces) face.center.multiplyScalar(scale);
      return { vertices, faces };
    }

    function geometryFromPolyhedron(polyhedron) {
      const positions = [];
      const normals = [];
      const uvs = [];
      const groups = [];
      for (const face of polyhedron.faces) {
        const start = positions.length / 3;
        const tangent = Math.abs(face.normal.y) > .92 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
        const u = new THREE.Vector3().crossVectors(tangent, face.normal).normalize();
        const v = new THREE.Vector3().crossVectors(face.normal, u).normalize();
        for (let i = 1; i < face.indices.length - 1; i += 1) {
          for (const index of [face.indices[0], face.indices[i], face.indices[i + 1]]) {
            const point = polyhedron.vertices[index];
            const local = point.clone().sub(face.center);
            positions.push(point.x, point.y, point.z);
            normals.push(face.normal.x, face.normal.y, face.normal.z);
            uvs.push(.5 + local.dot(u) * .35, .5 + local.dot(v) * .35);
          }
        }
        const count = positions.length / 3 - start;
        groups.push({ start, count, materialIndex:face.value - 1 });
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
      geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
      for (const group of groups) geometry.addGroup(group.start, group.count, group.materialIndex);
      geometry.computeBoundingSphere();
      return geometry;
    }

    function makeArbitraryDieMesh(normals, sides) {
      if (sides < 4) {
        const group = new THREE.Group();
        const core = new THREE.Mesh(new THREE.CylinderGeometry(1.08, 1.08, .38, sides === 2 ? 56 : 3), white);
        core.castShadow = true;
        core.receiveShadow = true;
        group.add(core);
        for (const face of normals) group.add(makePippedPanel(face, sides));
        return { mesh:group, polyhedron:null };
      }
      const polyhedron = convexFromNormals(normals);
      const mesh = new THREE.Mesh(
        geometryFromPolyhedron(polyhedron),
        Array.from({ length:sides }, (_, i) => pipMaterial(i + 1, sides))
      );
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      return { mesh, polyhedron };
    }

    function bodyFor(sides, polyhedron) {
      const body = new CANNON.Body({
        mass:1,
        material:diceMaterial,
        linearDamping:.36,
        angularDamping:.52,
        allowSleep:true,
        sleepSpeedLimit:.12,
        sleepTimeLimit:.45,
      });
      if (sides === 6) body.addShape(new CANNON.Box(new CANNON.Vec3(.78, .78, .78)));
      else if (polyhedron) {
        body.addShape(new CANNON.ConvexPolyhedron({
          vertices:polyhedron.vertices.map(point => new CANNON.Vec3(point.x, point.y, point.z)),
          faces:polyhedron.faces.map(face => face.indices),
        }));
      } else body.addShape(new CANNON.Cylinder(1.08, 1.08, .38, sides === 2 ? 32 : 3));
      world.addBody(body);
      return body;
    }

    function makeDie(index, sides, count) {
      const materials = sides === 6
        ? [pipMaterial(1, sides), pipMaterial(6, sides), pipMaterial(2, sides), pipMaterial(5, sides), pipMaterial(3, sides), pipMaterial(4, sides)]
        : [...Array.from({ length:sides }, (_, i) => pipMaterial(i + 1, sides)), white];
      const normals = faceNormals(sides);
      const arbitrary = sides === 6 ? null : makeArbitraryDieMesh(normals, sides);
      const mesh = sides === 6 ? new THREE.Mesh(cubeGeometry(), materials) : arbitrary.mesh;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      scene.add(mesh);
      const spread = Math.ceil(Math.sqrt(count));
      const row = Math.floor(index / spread);
      const col = index % spread;
      const x = (col - (spread - 1) / 2) * 2.05;
      const z = (row - (Math.ceil(count / spread) - 1) / 2) * 2.05;
      return {
        mesh,
        body:bodyFor(sides, arbitrary && arbitrary.polyhedron),
        sides,
        count,
        radius:sides === 6 ? 1.35 : sides < 4 ? 1.08 : 1.22,
        pos:new THREE.Vector3(x, 1.8 + index * .05, z),
        quat:new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.random() * 4, Math.random() * 4, Math.random() * 4)),
        normals,
        value:1,
        settled:false,
      };
    }

    function syncInputs() {
      rng.sides = clamp(sidesInput.value, 2, 60);
      rng.count = clamp(diceInput.value, 1, 24);
      sidesInput.value = String(rng.sides);
      diceInput.value = String(rng.count);
    }

    function buildDice() {
      syncInputs();
      for (const die of rng.dice) {
        scene.remove(die.mesh);
        world.removeBody(die.body);
      }
      rng.dice = Array.from({ length:rng.count }, (_, index) => makeDie(index, rng.sides, rng.count));
      rng.rolling = false;
      for (const die of rng.dice) {
        die.body.position.copy(die.pos);
        die.body.quaternion.copy(die.quat);
        die.mesh.position.copy(die.pos);
        die.mesh.quaternion.copy(die.quat);
      }
      resultText.textContent = 'Ready';
      updateReadout();
      frameCamera();
      renderNow();
    }

    function roll() {
      for (const [index, die] of rng.dice.entries()) {
        die.pos.set((Math.random() - .5) * 3.6, 3.2 + index * .12, (Math.random() - .5) * 3.0);
        die.quat.setFromEuler(new THREE.Euler(Math.random() * 6, Math.random() * 6, Math.random() * 6));
        die.body.wakeUp();
        die.body.position.set(die.pos.x, die.pos.y, die.pos.z);
        die.body.velocity.set((Math.random() - .5) * 8, 2.5 + Math.random() * 4.5, (Math.random() - .5) * 8);
        die.body.quaternion.set(die.quat.x, die.quat.y, die.quat.z, die.quat.w);
        die.body.angularVelocity.set((Math.random() - .5) * 15, (Math.random() - .5) * 15, (Math.random() - .5) * 15);
        die.settled = false;
      }
      rng.rolling = true;
      resultText.textContent = 'Rolling';
    }

    function valueFor(die) {
      let best = die.normals[0];
      let bestY = -Infinity;
      for (const face of die.normals) {
        const y = face.normal.clone().applyQuaternion(die.quat).y;
        if (y > bestY) {
          bestY = y;
          best = face;
        }
      }
      return best.value;
    }

    function updateReadout() {
      let total = 0;
      const values = [];
      readout.innerHTML = '';
      for (const die of rng.dice) {
        die.value = valueFor(die);
        values.push(die.value);
        total += die.value;
        const chip = document.createElement('div');
        chip.className = 'chip';
        chip.textContent = die.value;
        readout.appendChild(chip);
      }
      if (!rng.rolling) resultText.textContent = `Total ${total}`;
      document.body.dataset.diceCount = String(rng.count);
      document.body.dataset.diceSides = String(rng.sides);
      document.body.dataset.modelSideCount = String(rng.count * rng.sides);
      document.body.dataset.total = String(total);
      document.body.dataset.values = values.join(',');
      document.body.dataset.rolling = String(rng.rolling);
      document.body.dataset.probability100 = JSON.stringify(expectedCounts(rng.sides, rng.count, 100));
    }

    function expectedDistribution(sides, count) {
      let distribution = new Map([[0, 1]]);
      for (let die = 0; die < count; die += 1) {
        const next = new Map();
        for (const [subtotal, ways] of distribution.entries()) {
          for (let face = 1; face <= sides; face += 1) {
            next.set(subtotal + face, (next.get(subtotal + face) || 0) + ways);
          }
        }
        distribution = next;
      }
      const totalWays = sides ** count;
      return [...distribution.entries()]
        .sort((left, right) => left[0] - right[0])
        .map(([total, ways]) => ({ total, probability:ways / totalWays }));
    }

    function expectedCounts(sides, count, rolls = 100) {
      return expectedDistribution(sides, count).map(item => ({
        total:item.total,
        expected:Number((item.probability * rolls).toFixed(6)),
        probability:Number(item.probability.toFixed(8)),
      }));
    }

    function step(dt) {
      world.step(1 / 60, dt, 5);
      let active = false;
      for (const die of rng.dice) {
        const speed = die.body.velocity.length();
        const spin = die.body.angularVelocity.length();
        if (speed < .45 && spin < .55 && die.body.position.y <= die.radius + .08) {
          die.body.velocity.set(0, 0, 0);
          die.body.angularVelocity.set(0, 0, 0);
          die.body.sleep();
        }
        die.pos.set(die.body.position.x, die.body.position.y, die.body.position.z);
        die.quat.set(die.body.quaternion.x, die.body.quaternion.y, die.body.quaternion.z, die.body.quaternion.w);
        die.mesh.position.copy(die.pos);
        die.mesh.quaternion.copy(die.quat);
        die.settled = die.body.sleepState === CANNON.Body.SLEEPING;
        active = active || !die.settled;
      }
      if (rng.rolling && !active) {
        rng.rolling = false;
        updateReadout();
        document.dispatchEvent(new CustomEvent('dice:settled', { detail:{ values:rng.dice.map(die => die.value) } }));
      }
    }

    function rebuildWalls() {
      while (wallBodies.length) world.removeBody(wallBodies.pop());
      const size = rng.bounds + .25;
      const wallDefs = [
        { position:[size, 1.5, 0], size:[.2, 3, size * 2] },
        { position:[-size, 1.5, 0], size:[.2, 3, size * 2] },
        { position:[0, 1.5, size], size:[size * 2, 3, .2] },
        { position:[0, 1.5, -size], size:[size * 2, 3, .2] },
      ];
      for (const def of wallDefs) {
        const body = new CANNON.Body({ type:CANNON.Body.STATIC, material:floorMaterial });
        body.addShape(new CANNON.Box(new CANNON.Vec3(def.size[0] / 2, def.size[1] / 2, def.size[2] / 2)));
        body.position.set(def.position[0], def.position[1], def.position[2]);
        world.addBody(body);
        wallBodies.push(body);
      }
    }

    function frameCamera() {
      const size = Math.max(9, Math.ceil(Math.sqrt(rng.count)) * 3.5);
      rng.bounds = Math.max(7, size);
      rebuildWalls();
      camera.position.set(size * .65, size * .7, size * 1.05);
      controls.target.set(0, .75, 0);
      controls.update();
    }

    function resize() {
      const rect = canvas.parentElement.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderNow();
    }

    function renderNow() {
      renderer.render(scene, camera);
    }

    function animate(now) {
      const dt = Math.min(.04, (now - rng.lastTime) / 1000);
      rng.lastTime = now;
      if (rng.rolling) step(dt);
      controls.update();
      renderNow();
      requestAnimationFrame(animate);
    }

    document.querySelectorAll('[data-step]').forEach(button => {
      button.addEventListener('click', () => {
        const [target, delta] = button.dataset.step.split(':');
        const input = target === 'sides' ? sidesInput : diceInput;
        input.value = String(Number(input.value || 0) + Number(delta));
        buildDice();
      });
    });
    sidesInput.addEventListener('input', buildDice);
    diceInput.addEventListener('input', buildDice);
    rollButton.addEventListener('click', roll);
    window.addEventListener('resize', resize);

    buildDice();
    resize();
    requestAnimationFrame(animate);
    window.diceRng = { buildDice, roll, state:rng, camera, controls, expectedDistribution, expectedCounts };
  </script>
</body>
</html>
"""


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLoop</title>
  <style>
    :root {
      color-scheme: light;
      --bg:#ffffff;
      --surface:#ffffff;
      --panel:#f7f9fc;
      --ink:#17202a;
      --muted:#667085;
      --line:#d8dee8;
      --accent:#176b87;
      --accent-ink:#ffffff;
      --ok:#1d7f45;
      --bad:#b42318;
      --code-bg:#101828;
      --code-ink:#f2f4f7;
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg:#111418;
      --surface:#191e24;
      --panel:#151a20;
      --ink:#eef2f6;
      --muted:#aab4c0;
      --line:#313945;
      --accent:#59a6c0;
      --accent-ink:#071116;
      --ok:#6fcf97;
      --bad:#ff8a80;
      --code-bg:#090c10;
      --code-ink:#eef2f6;
    }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; color:var(--ink); background:var(--bg); }
    header { border-bottom:1px solid var(--line); padding:12px 18px; display:grid; grid-template-columns:auto minmax(0, 1fr) auto; align-items:center; gap:12px; background:var(--surface); position:sticky; top:0; z-index:10; }
    h1 { font-size:20px; margin:0; letter-spacing:0; }
    h2 { font-size:18px; margin:0 0 12px; }
    h3 { font-size:15px; margin:16px 0 8px; }
    main { min-height:calc(100vh - 57px); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    .workspace { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .menu-button { width:38px; height:34px; display:grid; place-content:center; gap:4px; padding:0; }
    .menu-button span { display:block; width:18px; height:2px; background:currentColor; border-radius:2px; }
    .shell { display:grid; grid-template-columns: 260px 1fr; min-height:calc(100vh - 57px); }
    .shell.menu-collapsed { grid-template-columns: 0 1fr; }
    nav { overflow:hidden; border-right:1px solid var(--line); background:var(--panel); transition:width .15s ease; }
    .nav-inner { width:260px; padding:14px; }
    .nav-item { width:100%; display:flex; justify-content:space-between; align-items:center; border:1px solid transparent; background:transparent; color:var(--ink); text-align:left; text-decoration:none; border-radius:6px; padding:8px 10px; cursor:pointer; }
    .nav-item.active { background:var(--surface); border-color:var(--line); }
    .page { display:none; padding:20px 24px; min-width:0; }
    .page.active { display:grid; gap:16px; }
    button, input, select, textarea { font:inherit; }
    button { border:1px solid var(--line); background:var(--surface); color:var(--ink); border-radius:6px; padding:8px 10px; cursor:pointer; }
    button.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
    button.danger { color:var(--bad); }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .stack { display:grid; gap:10px; }
    .chat-shell { max-width:920px; min-height:calc(100vh - 150px); display:grid; grid-template-rows:minmax(320px, 1fr) auto; gap:12px; }
    .chat-transcript { align-content:end; max-height:calc(100vh - 285px); overflow:auto; padding:14px; background:var(--panel); border:1px solid var(--line); border-radius:8px; }
    .chat-message { display:grid; gap:5px; max-width:min(720px, 92%); }
    .chat-message.user { justify-self:end; }
    .chat-message.agent { justify-self:start; }
    .chat-bubble { padding:11px 13px; border:1px solid var(--line); border-radius:8px; background:var(--surface); white-space:pre-wrap; line-height:1.45; }
    .chat-message.user .chat-bubble { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
    .chat-composer { display:grid; gap:10px; }
    .chat-composer textarea { min-height:76px; }
    .chat-actions { display:flex; gap:8px; flex-wrap:wrap; }
    .chat-actions[hidden] { display:none; }
    .chat-edit-controls { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; }
    .chat-edit-controls[hidden] { display:none; }
    .chat-attachments { display:flex; gap:8px; flex-wrap:wrap; }
    .chat-attachment { display:flex; align-items:center; gap:6px; border:1px solid var(--line); border-radius:6px; padding:6px 8px; background:var(--panel); max-width:100%; }
    .chat-attachment span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:220px; }
    .chat-attachment button { padding:2px 6px; }
    .list button { width:100%; text-align:left; margin:3px 0; overflow:hidden; text-overflow:ellipsis; }
    .loop-card { border:1px solid var(--line); border-radius:6px; margin:6px 0; overflow:hidden; }
    .loop-card > button { border:0; border-radius:0; margin:0; }
    .loop-actions { display:none; grid-template-columns:1fr 1fr; gap:8px; padding:8px; border-top:1px solid var(--line); background:var(--panel); }
    .loop-card.expanded .loop-actions { display:grid; }
    .run-row { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:8px; align-items:center; }
    .run-row.active { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) inset; }
    .run-row span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .run-detail-grid { display:grid; grid-template-columns:1fr; gap:12px; }
    .run-log { max-height:320px; overflow:auto; }
    .artifact-list { display:grid; gap:6px; margin-top:8px; }
    .artifact-row { display:flex; gap:8px; align-items:center; justify-content:space-between; border:1px solid var(--line); border-radius:6px; padding:8px; }
    .artifact-row a { color:var(--accent); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    details.artifact { border:1px solid var(--line); border-radius:6px; padding:8px; }
    details.artifact summary { cursor:pointer; font-weight:600; }
    .grid { display:grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap:12px; }
    label { display:grid; gap:4px; color:var(--muted); font-size:13px; }
    input, textarea, select { width:100%; border:1px solid var(--line); border-radius:6px; padding:8px; background:var(--surface); color:var(--ink); }
    textarea { min-height:92px; resize:vertical; }
    pre { background:var(--code-bg); color:var(--code-ink); padding:12px; border-radius:6px; overflow:auto; white-space:pre-wrap; }
    .split { display:grid; grid-template-columns: minmax(260px, 380px) 1fr; gap:16px; align-items:start; }
    .panel { border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--surface); }
    .muted { color:var(--muted); }
    .status { font-weight:600; }
    .theme-toggle { min-width:92px; }
    .theme-toggle { justify-self:end; }
    @media (max-width: 900px) {
      .shell, .shell.menu-collapsed { grid-template-columns:1fr; }
      nav { border-right:0; border-bottom:1px solid var(--line); }
      .shell.menu-collapsed nav { display:none; }
      .nav-inner { width:100%; }
      .split, .grid { grid-template-columns:1fr; }
      .chat-edit-controls { grid-template-columns:1fr; }
      .loop-actions { grid-template-columns:1fr; }
      .page { padding:16px; }
    }
    @media (max-width: 520px) {
      header { grid-template-columns:minmax(0, 1fr) auto; }
      .workspace { grid-column:1 / -1; margin-left:48px; }
      h1 { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <button class="menu-button" id="menuToggle" aria-label="Menu" aria-expanded="true"><span></span><span></span><span></span></button>
      <h1>AgentLoop</h1>
    </div>
    <div class="muted workspace" id="workspace"></div>
    <button class="theme-toggle" id="themeToggle" title="Toggle theme">System</button>
  </header>
  <main class="shell" id="shell">
    <nav>
      <div class="nav-inner stack">
        <button class="nav-item active" data-page-target="dashboardPage">Home Dashboard</button>
        <button class="nav-item" data-page-target="runPage">Run</button>
        <button class="nav-item" data-page-target="chatPage">Chat</button>
        <button class="nav-item" data-page-target="appsPage">Apps</button>
        <button class="nav-item" data-page-target="loopsPage">Loops</button>
        <button class="nav-item" data-page-target="templatesPage">Templates</button>
        <button class="nav-item" data-page-target="settingsPage">Settings</button>
      </div>
    </nav>
    <section>
      <div class="page active" id="dashboardPage">
        <h2>Home Dashboard</h2>
        <div class="grid">
          <div class="panel"><strong id="loopCount">0</strong><div class="muted">loops</div></div>
          <div class="panel"><strong id="templateCount">0</strong><div class="muted">templates</div></div>
          <div class="panel"><strong id="runCount">0</strong><div class="muted">runs</div></div>
        </div>
        <div class="panel">
          <strong>Recent Runs</strong>
          <div class="list" id="dashboardRuns"></div>
        </div>
      </div>
      <div class="page" id="runPage">
        <h2>Run</h2>
        <div class="split">
          <div class="panel stack">
            <label>Loop or template<select id="runConfigSelect"></select></label>
            <div><strong id="selectedName">Select a loop or template</strong><div class="muted" id="selectedKind"></div></div>
            <div id="variables" class="stack"></div>
            <label>Max iterations<input id="maxIterations" type="number" min="1" placeholder="config default"></label>
            <div class="row">
              <button class="primary" id="dryRun">Dry-run</button>
              <button id="startRun">Start</button>
            </div>
            <div class="status" id="message"></div>
          </div>
          <div class="panel">
            <strong>Rendered Output</strong>
            <pre id="output">No dry-run yet.</pre>
          </div>
        </div>
      </div>
      <div class="page" id="chatPage">
        <h2>Chat</h2>
        <div class="chat-shell">
          <div class="chat-transcript stack" id="chatTranscript"></div>
          <div class="panel chat-composer">
            <div class="chat-actions" id="chatDraftActions" hidden>
              <button id="createChatTemplate">Create template</button>
              <button id="createChatLoop">Create loop</button>
              <button class="primary" id="startChatRun">Start run</button>
              <button id="resetChatDraft">New idea</button>
            </div>
            <label>Chat mode
              <select id="chatMode">
                <option value="new">New app idea</option>
                <option value="edit">Edit existing</option>
              </select>
            </label>
            <div class="chat-edit-controls" id="chatEditControls" hidden>
              <label>Type
                <select id="chatTargetKind">
                  <option value="templates">Template</option>
                  <option value="loops">Loop</option>
                  <option value="runs">Run</option>
                </select>
              </label>
              <label>Target<select id="chatTarget"></select></label>
              <label>Action
                <select id="chatAction">
                  <option value="auto">Auto</option>
                  <option value="update">Add requirement</option>
                  <option value="rerun">Rerun with requirement</option>
                </select>
              </label>
            </div>
            <textarea id="chatMessage" placeholder="Tell AgentLoop what you want to build."></textarea>
            <div class="chat-attachments" id="chatAttachments"></div>
            <div class="row">
              <input id="chatFileInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden>
              <button id="attachChatFile" type="button">Attach image</button>
              <button class="primary" id="sendChat">Send</button>
            </div>
          </div>
        </div>
      </div>
      <div class="page" id="loopsPage">
        <h2>Loops</h2>
        <div class="panel list" id="loops"></div>
      </div>
      <div class="page" id="appsPage">
        <h2>Apps</h2>
        <div class="panel list" id="apps"></div>
      </div>
      <div class="page" id="loopRunsPage">
        <h2 id="loopRunsTitle">Loop Runs</h2>
        <div class="split">
          <div class="panel stack">
            <strong id="loopRunsName">Select a loop.</strong>
            <div class="list" id="loopRuns"></div>
          </div>
          <div class="stack">
            <div class="panel">
              <strong>Run Details</strong>
              <pre id="runDetails">No run selected.</pre>
              <div class="row">
                <button class="danger" id="stopRun">Stop selected run</button>
                <button id="rerunRun">Rerun selected run</button>
              </div>
            </div>
            <div class="panel">
              <strong>Final Output</strong>
              <div class="artifact-list" id="runFinalArtifacts"></div>
            </div>
            <div class="panel run-detail-grid">
              <div class="row">
                <strong>Rolling Log</strong>
                <a id="downloadRunLog" href="#" download hidden>Download run.log</a>
              </div>
              <pre class="run-log" id="runLog">Select a run.</pre>
              <details open>
                <summary>Log files</summary>
                <div class="artifact-list" id="runLogArtifacts"></div>
              </details>
              <details>
                <summary>Screenshots and attachments</summary>
                <div class="artifact-list" id="runAttachments"></div>
              </details>
            </div>
          </div>
        </div>
      </div>
      <div class="page" id="loopConfigPage">
        <h2>Loop Configuration</h2>
        <div class="panel stack">
          <div class="row">
            <button id="editLoopConfig">Edit</button>
            <button class="primary" id="saveLoopConfig" hidden>Save</button>
            <button id="cancelLoopConfig" hidden>Cancel</button>
          </div>
          <pre id="loopConfigDetails">Select a loop.</pre>
          <textarea id="loopConfigYaml" spellcheck="false" hidden style="min-height:420px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;"></textarea>
        </div>
      </div>
      <div class="page" id="templatesPage">
        <h2>Templates</h2>
        <div class="split">
          <div class="panel">
            <div class="list" id="templates"></div>
          </div>
          <div class="panel stack">
            <div class="row">
              <input id="templateName" placeholder="template-name">
              <button id="newTemplate">New</button>
              <button id="copyTemplate">Copy</button>
              <button class="primary" id="saveTemplate">Save</button>
            </div>
            <textarea id="templateYaml" spellcheck="false" style="min-height:420px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;"></textarea>
          </div>
        </div>
      </div>
      <div class="page" id="settingsPage">
        <h2>Settings</h2>
        <div class="split">
          <div class="panel stack">
            <label>Theme
              <select id="themeMode">
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <label>Workspace<input id="workspaceSetting" readonly></label>
            <label>Run storage<input value=".agentloop-runs/" readonly></label>
            <label>Config directory<input value=".agentloop/" readonly></label>
          </div>
        </div>
      </div>
    </section>
  </main>
<script>
const state = { selected: null, selectedLoop: null, selectedRun: null, loopConfigYaml: '', chatDraft: null, chatAttachments: [], configs: { loops: [], templates: [] }, runs: [], apps: [] };
const $ = id => document.getElementById(id);
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
function storedTheme() { return localStorage.getItem('agentloop-theme') || 'system'; }
function effectiveTheme(mode) { return mode === 'system' ? (prefersDark.matches ? 'dark' : 'light') : mode; }
function applyTheme(mode=storedTheme()) {
  const theme = effectiveTheme(mode);
  document.documentElement.dataset.theme = theme;
  $('themeToggle').textContent = mode[0].toUpperCase() + mode.slice(1);
  $('themeMode').value = mode;
}
async function api(path, options={}) {
  const response = await fetch(path, { headers: {'content-type':'application/json'}, ...options });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
function setMessage(text) { $('message').textContent = text; }
function showPage(pageId) {
  document.querySelectorAll('.page').forEach(page => page.classList.toggle('active', page.id === pageId));
  document.querySelectorAll('[data-page-target]').forEach(button => button.classList.toggle('active', button.dataset.pageTarget === pageId));
}
function collectValues() {
  const values = {};
  document.querySelectorAll('[data-var]').forEach(input => { if (input.value) values[input.dataset.var] = input.value; });
  return values;
}
function renderVariables(item) {
  $('variables').innerHTML = '';
  (item.variables || []).forEach(variable => {
    const label = document.createElement('label');
    label.textContent = variable.name + (variable.required ? ' *' : '');
    const input = document.createElement(variable.secret ? 'input' : 'textarea');
    if (variable.secret) input.type = 'password';
    input.dataset.var = variable.name;
    if (variable.default !== null && variable.default !== undefined) input.value = variable.default;
    label.appendChild(input);
    $('variables').appendChild(label);
  });
}
function appendChat(role, text) {
  const panel = document.createElement('div');
  panel.className = `chat-message ${role === 'You' ? 'user' : 'agent'}`;
  const label = document.createElement('strong');
  label.textContent = role;
  label.className = 'muted';
  const body = document.createElement('div');
  body.className = 'chat-bubble';
  body.textContent = text;
  panel.append(label, body);
  $('chatTranscript').appendChild(panel);
  $('chatTranscript').scrollTop = $('chatTranscript').scrollHeight;
}
function populateChatTargets() {
  if (!$('chatTargetKind') || !$('chatTarget')) return;
  const kind = $('chatTargetKind').value;
  const select = $('chatTarget');
  select.innerHTML = '';
  const items = kind === 'runs' ? state.runs : state.configs[kind] || [];
  items.forEach(item => {
    const option = document.createElement('option');
    option.value = kind === 'runs' ? item.run_id : item.name;
    option.textContent = kind === 'runs' ? `${item.run_id} ${item.status || ''}` : item.name;
    select.appendChild(option);
  });
}
function setChatDraft(draft) {
  state.chatDraft = draft || null;
  $('chatDraftActions').hidden = $('chatMode').value === 'edit' || !state.chatDraft;
}
function updateChatMode() {
  const editing = $('chatMode').value === 'edit';
  $('chatEditControls').hidden = !editing;
  $('chatDraftActions').hidden = editing || !state.chatDraft;
  $('chatMessage').placeholder = editing ? 'Describe the requirement or rerun change.' : 'Tell AgentLoop what you want to build.';
  if (editing) populateChatTargets();
}
function renderChatAttachments() {
  $('chatAttachments').innerHTML = '';
  state.chatAttachments.forEach((file, index) => {
    const chip = document.createElement('div');
    chip.className = 'chat-attachment';
    const name = document.createElement('span');
    name.textContent = file.name;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Remove';
    remove.onclick = () => {
      state.chatAttachments.splice(index, 1);
      renderChatAttachments();
    };
    chip.append(name, remove);
    $('chatAttachments').appendChild(chip);
  });
}
function fileToAttachment(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || '');
      const marker = ';base64,';
      const markerIndex = dataUrl.indexOf(marker);
      resolve({
        name: file.name,
        type: file.type,
        data: markerIndex >= 0 ? dataUrl.slice(markerIndex + marker.length) : dataUrl,
      });
    };
    reader.onerror = () => reject(reader.error || new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}
async function collectChatAttachments() {
  return Promise.all(state.chatAttachments.map(fileToAttachment));
}
function clearChatAttachments() {
  state.chatAttachments = [];
  $('chatFileInput').value = '';
  renderChatAttachments();
}
function selectConfig(item) {
  state.selected = item;
  $('selectedName').textContent = item.name;
  $('selectedKind').textContent = item.kind;
  $('runConfigSelect').value = `${item.kind}:${item.name}`;
  renderVariables(item);
  if (item.kind === 'templates') loadTemplateYaml(item.name);
}
function setLoopConfigEditing(editing) {
  $('loopConfigDetails').hidden = editing;
  $('loopConfigYaml').hidden = !editing;
  $('editLoopConfig').hidden = editing || !state.selectedLoop;
  $('saveLoopConfig').hidden = !editing;
  $('cancelLoopConfig').hidden = !editing;
}
async function showLoopConfig(item) {
  state.selectedLoop = item.name;
  selectConfig(item);
  const data = await api(`/api/loops/${encodeURIComponent(item.name)}`);
  state.loopConfigYaml = data.yaml;
  $('loopConfigDetails').textContent = data.yaml;
  $('loopConfigYaml').value = data.yaml;
  setLoopConfigEditing(false);
  showPage('loopConfigPage');
}
function editLoopConfig() {
  if (!state.selectedLoop) return;
  $('loopConfigYaml').value = state.loopConfigYaml;
  setLoopConfigEditing(true);
}
async function saveLoopConfig() {
  if (!state.selectedLoop) return;
  const data = await api(`/api/loops/${encodeURIComponent(state.selectedLoop)}`, { method:'PUT', body: JSON.stringify({ yaml: $('loopConfigYaml').value }) });
  state.loopConfigYaml = data.yaml;
  $('loopConfigDetails').textContent = data.yaml;
  $('loopConfigYaml').value = data.yaml;
  await loadConfigs();
  const loop = state.configs.loops.find(item => item.name === data.name);
  if (loop) selectConfig(loop);
  setLoopConfigEditing(false);
  setMessage(`Saved ${data.name}.`);
}
function cancelLoopConfig() {
  $('loopConfigYaml').value = state.loopConfigYaml;
  setLoopConfigEditing(false);
}
function formatRunDetail(detail) {
  const parts = [
    `run_id: ${detail.run_id}`,
    `loop: ${detail.loop || ''}`,
    `status: ${detail.status || ''}`,
    `reason: ${detail.reason || ''}`,
    `files:\\n${(detail.files || []).map(name => `  - ${name}`).join('\\n') || '  none'}`
  ];
  if (detail.summary) parts.push(`summary:\\n${JSON.stringify(detail.summary, null, 2)}`);
  if (detail.report) parts.push(`report:\\n${detail.report}`);
  return parts.join('\\n\\n');
}
function renderArtifactList(container, items, emptyText) {
  container.innerHTML = '';
  if (!items || !items.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'artifact-row';
    const open = document.createElement('a');
    open.href = item.url;
    open.target = '_blank';
    open.rel = 'noopener';
    open.textContent = item.name;
    const download = document.createElement('a');
    if (item.download_url) {
      download.href = item.download_url;
      download.download = item.name;
      download.textContent = 'Download';
      row.append(open, download);
    } else {
      row.append(open);
    }
    container.appendChild(row);
  });
}
function renderLogArtifacts(logs) {
  $('runLogArtifacts').innerHTML = '';
  if (!logs || !logs.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.textContent = 'No log files yet.';
    $('runLogArtifacts').appendChild(empty);
    return;
  }
  logs.forEach(log => {
    const detail = document.createElement('details');
    detail.className = 'artifact';
    const summary = document.createElement('summary');
    const open = document.createElement('a');
    open.href = log.url;
    open.target = '_blank';
    open.rel = 'noopener';
    open.textContent = log.name;
    const download = document.createElement('a');
    download.href = log.download_url || log.url;
    download.download = log.name;
    download.textContent = 'Download';
    summary.append(open, ' ', download);
    const pre = document.createElement('pre');
    pre.textContent = log.content || '';
    detail.append(summary, pre);
    $('runLogArtifacts').appendChild(detail);
  });
}
function renderRunDetail(detail) {
  $('runDetails').textContent = formatRunDetail(detail);
  const log = $('runLog');
  const wasNearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 32;
  const shouldFollow = detail.status === 'running' && wasNearBottom;
  $('runLog').textContent = detail.event_log || 'No run log yet.';
  if (shouldFollow) log.scrollTop = log.scrollHeight;
  const logUrl = detail.run_log_url;
  $('downloadRunLog').hidden = !logUrl;
  if (logUrl) {
    $('downloadRunLog').href = `${logUrl}?download=1`;
  }
  renderArtifactList($('runFinalArtifacts'), detail.final_artifacts || [], 'No final output link recorded yet.');
  renderLogArtifacts(detail.logs || []);
  renderArtifactList($('runAttachments'), detail.attachments || [], 'No screenshots or attachments yet.');
}
async function showRunDetail(runId) {
  state.selectedRun = runId;
  const detail = await api(`/api/runs/${encodeURIComponent(runId)}`);
  renderRunDetail(detail);
  document.querySelectorAll('#loopRuns .run-row').forEach(button => {
    button.classList.toggle('active', button.dataset.runId === runId);
  });
}
async function showLoopRuns(loopName, runId=null) {
  state.selectedLoop = loopName;
  $('loopRunsTitle').textContent = `${loopName} Runs`;
  $('loopRunsName').textContent = loopName;
  $('loopRuns').innerHTML = '';
  const data = await api(`/api/loops/${encodeURIComponent(loopName)}/runs`);
  if (!data.runs.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.textContent = 'No runs for this loop.';
    $('loopRuns').appendChild(empty);
  }
  data.runs.forEach(run => {
    const button = document.createElement('button');
    button.className = 'run-row';
    button.dataset.runId = run.run_id;
    const name = document.createElement('span');
    name.textContent = run.run_id;
    const status = document.createElement('span');
    status.className = 'muted';
    status.textContent = run.status || '';
    button.append(name, status);
    button.onclick = () => showRunDetail(run.run_id);
    $('loopRuns').appendChild(button);
  });
  showPage('loopRunsPage');
  if (runId) await showRunDetail(runId);
  else {
    state.selectedRun = null;
    $('runDetails').textContent = 'Select a run.';
    $('runLog').textContent = 'Select a run.';
    $('downloadRunLog').hidden = true;
    renderLogArtifacts([]);
    renderArtifactList($('runAttachments'), [], 'No screenshots or attachments yet.');
  }
}
function configByKey(key) {
  const [kind, name] = key.split(':');
  return (state.configs[kind] || []).find(item => item.name === name);
}
async function loadConfigs() {
  const data = await api('/api/configs');
  state.configs = { loops: data.loops, templates: data.templates };
  $('workspace').textContent = data.workspace;
  $('workspaceSetting').value = data.workspace;
  $('loopCount').textContent = data.loops.length;
  $('templateCount').textContent = data.templates.length;
  $('runConfigSelect').innerHTML = '';
  for (const kind of ['loops','templates']) {
    $(kind).innerHTML = '';
    data[kind].forEach(item => {
      if (kind === 'loops') {
        const card = document.createElement('div');
        card.className = 'loop-card';
        const toggle = document.createElement('button');
        toggle.textContent = item.name;
        toggle.onclick = () => card.classList.toggle('expanded');
        const actions = document.createElement('div');
        actions.className = 'loop-actions';
        const configButton = document.createElement('button');
        configButton.textContent = 'Loop Configuration';
        configButton.onclick = () => showLoopConfig(item);
        const runsButton = document.createElement('button');
        runsButton.textContent = 'Loop Runs';
        runsButton.onclick = () => showLoopRuns(item.name);
        actions.append(configButton, runsButton);
        card.append(toggle, actions);
        $('loops').appendChild(card);
      } else {
        const button = document.createElement('button');
        button.textContent = item.name;
        button.onclick = () => { selectConfig(item); showPage('templatesPage'); };
        $('templates').appendChild(button);
      }
      const option = document.createElement('option');
      option.value = `${kind}:${item.name}`;
      option.textContent = `${item.name} (${kind.slice(0, -1)})`;
      $('runConfigSelect').appendChild(option);
    });
  }
  if (!state.selected && $('runConfigSelect').value) selectConfig(configByKey($('runConfigSelect').value));
  populateChatTargets();
}
async function loadRuns() {
  const data = await api('/api/runs');
  state.runs = data.runs;
  $('runCount').textContent = data.runs.length;
  $('dashboardRuns').innerHTML = '';
  data.runs.slice(0, 8).forEach(run => {
    const button = document.createElement('button');
    button.textContent = `${run.run_id} ${run.status || ''}`;
    button.onclick = async () => {
      if (run.loop) await showLoopRuns(run.loop, run.run_id);
      else {
        showPage('loopRunsPage');
        await showRunDetail(run.run_id);
      }
    };
    $('dashboardRuns').appendChild(button);
  });
  if (state.selectedRun) {
    const selected = data.runs.find(run => run.run_id === state.selectedRun);
    if (selected && ['running', 'stopping'].includes(selected.status || '')) {
      await showRunDetail(state.selectedRun);
    }
  }
  if ($('chatTargetKind') && $('chatTargetKind').value === 'runs') populateChatTargets();
}
async function loadApps() {
  const data = await api('/api/apps');
  state.apps = data.apps || [];
  $('apps').innerHTML = '';
  if (!state.apps.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.textContent = 'No apps have been deployed yet.';
    $('apps').appendChild(empty);
    return;
  }
  state.apps.forEach(app => {
    const row = document.createElement('div');
    row.className = 'artifact-row';
    const open = document.createElement('a');
    open.href = app.url;
    open.target = '_blank';
    open.rel = 'noopener';
    open.textContent = app.name;
    const path = document.createElement('span');
    path.className = 'muted';
    path.textContent = app.url;
    row.append(open, path);
    $('apps').appendChild(row);
  });
}
async function refreshSelectedRun() {
  if (!state.selectedRun) return;
  try {
    await showRunDetail(state.selectedRun);
  } catch (err) {
    setMessage(err.message);
  }
}
async function dryRun() {
  if (!state.selected) return setMessage('Select a loop or template.');
  try {
    const data = await api('/api/dry-run', { method:'POST', body: JSON.stringify({ ...state.selected, values: collectValues() }) });
    $('output').textContent = '# Rendered Prompt\\n' + data.prompt + '\\n\\n# Commands\\n' + data.commands.join('\\n');
    setMessage('Dry-run complete.');
  } catch (err) {
    setMessage(err.message);
    $('output').textContent = `Dry-run failed:\\n${err.message}`;
  }
}
async function startRun() {
  if (!state.selected) return setMessage('Select a loop or template.');
  const max = $('maxIterations').value;
  const payload = { ...state.selected, values: collectValues(), max_iterations: max ? Number(max) : null };
  const data = await api('/api/run', { method:'POST', body: JSON.stringify(payload) });
  setMessage(`Started ${data.run_id}`);
  await loadConfigs();
  if (data.loop) {
    const loop = state.configs.loops.find(item => item.name === data.loop);
    if (loop) selectConfig(loop);
    await showLoopRuns(data.loop, data.run_id === 'pending' ? null : data.run_id);
  }
  setTimeout(loadRuns, 1000);
}
async function stopRun() {
  if (!state.selectedRun) return setMessage('Select a run.');
  await api(`/api/runs/${state.selectedRun}/stop`, { method:'POST', body:'{}' });
  setMessage('Stop requested.');
  await showRunDetail(state.selectedRun);
  await loadRuns();
}
async function rerunRun() {
  if (!state.selectedRun) return setMessage('Select a run.');
  const data = await api(`/api/runs/${state.selectedRun}/rerun`, { method:'POST', body:'{}' });
  setMessage(`Rerun started ${data.run_id}`);
  await loadRuns();
  if (data.loop) await showLoopRuns(data.loop, data.run_id === 'pending' ? null : data.run_id);
}
async function sendChat() {
  const message = $('chatMessage').value.trim();
  if (!message) return setMessage('Enter a chat message.');
  if ($('chatMode').value === 'edit') {
    const attachments = await collectChatAttachments();
    const payload = {
      message,
      action: $('chatAction').value,
      target: { kind: $('chatTargetKind').value, name: $('chatTarget').value },
      attachments,
    };
    appendChat('You', message);
    const data = await api('/api/chat', { method:'POST', body: JSON.stringify(payload) });
    appendChat('AgentLoop', data.message || JSON.stringify(data, null, 2));
    $('chatMessage').value = '';
    clearChatAttachments();
    setMessage(data.message || 'Chat action complete.');
    await loadConfigs();
    await loadRuns();
    await loadApps();
    if (data.target?.kind && data.target?.name) {
      const item = (state.configs[data.target.kind] || []).find(config => config.name === data.target.name);
      if (item) selectConfig(item);
    }
    if (data.run_id && data.loop) await showLoopRuns(data.loop, data.run_id);
    return;
  }
  const payload = {
    message,
    action: 'conversation',
    draft: state.chatDraft,
    attachments: await collectChatAttachments(),
  };
  appendChat('You', message);
  const data = await api('/api/chat', { method:'POST', body: JSON.stringify(payload) });
  setChatDraft(data.draft || state.chatDraft);
  appendChat('AgentLoop', data.message || JSON.stringify(data, null, 2));
  $('chatMessage').value = '';
  clearChatAttachments();
  setMessage(data.message || 'Chat action complete.');
}
async function createFromChat(kind) {
  if (!state.chatDraft) return setMessage('Start a chat first.');
  const data = await api('/api/chat', { method:'POST', body: JSON.stringify({ action:'conversation_create', create:kind, draft:state.chatDraft, message:'create' }) });
  setChatDraft(data.draft || state.chatDraft);
  appendChat('AgentLoop', data.message || JSON.stringify(data, null, 2));
  await loadConfigs();
  await loadRuns();
  await loadApps();
  if (data.target?.kind && data.target?.name) {
    const item = (state.configs[data.target.kind] || []).find(config => config.name === data.target.name);
    if (item) selectConfig(item);
  }
  if (data.run_id && data.loop) await showLoopRuns(data.loop, data.run_id);
}
function resetChatDraft() {
  setChatDraft(null);
  $('chatTranscript').innerHTML = '';
  $('chatMessage').value = '';
  clearChatAttachments();
  setMessage('Started a new chat draft.');
}
async function loadTemplateYaml(name) {
  const data = await api(`/api/templates/${encodeURIComponent(name)}`);
  $('templateName').value = data.name;
  $('templateYaml').value = data.yaml;
}
async function newTemplate() {
  const name = $('templateName').value.trim();
  if (!name) return setMessage('Enter a template name.');
  const data = await api('/api/templates', { method:'POST', body: JSON.stringify({ name }) });
  $('templateName').value = data.name;
  $('templateYaml').value = data.yaml;
  await loadConfigs();
  setMessage(`Created ${data.name}.`);
}
async function copyTemplate() {
  if (!state.selected || state.selected.kind !== 'templates') return setMessage('Select a template to copy.');
  const name = $('templateName').value.trim();
  if (!name) return setMessage('Enter the new template name.');
  const data = await api(`/api/templates/${encodeURIComponent(state.selected.name)}/copy`, { method:'POST', body: JSON.stringify({ name }) });
  $('templateName').value = data.name;
  $('templateYaml').value = data.yaml;
  await loadConfigs();
  setMessage(`Copied to ${data.name}.`);
}
async function saveTemplate() {
  const name = $('templateName').value.trim();
  if (!name) return setMessage('Enter a template name.');
  const data = await api(`/api/templates/${encodeURIComponent(name)}`, { method:'PUT', body: JSON.stringify({ yaml: $('templateYaml').value }) });
  $('templateYaml').value = data.yaml;
  await loadConfigs();
  setMessage(`Saved ${data.name}.`);
}
$('dryRun').onclick = dryRun;
$('startRun').onclick = startRun;
$('stopRun').onclick = stopRun;
$('rerunRun').onclick = rerunRun;
$('sendChat').onclick = sendChat;
$('attachChatFile').onclick = () => $('chatFileInput').click();
$('chatFileInput').onchange = event => {
  const files = Array.from(event.target.files || []).filter(file => file.type.startsWith('image/'));
  state.chatAttachments.push(...files);
  renderChatAttachments();
};
$('createChatTemplate').onclick = () => createFromChat('template');
$('createChatLoop').onclick = () => createFromChat('loop');
$('startChatRun').onclick = () => createFromChat('run');
$('resetChatDraft').onclick = resetChatDraft;
$('editLoopConfig').onclick = editLoopConfig;
$('saveLoopConfig').onclick = saveLoopConfig;
$('cancelLoopConfig').onclick = cancelLoopConfig;
$('newTemplate').onclick = newTemplate;
$('copyTemplate').onclick = copyTemplate;
$('saveTemplate').onclick = saveTemplate;
$('runConfigSelect').onchange = event => {
  const item = configByKey(event.target.value);
  if (item) selectConfig(item);
};
if ($('chatTargetKind')) $('chatTargetKind').onchange = populateChatTargets;
$('chatMode').onchange = updateChatMode;
$('menuToggle').onclick = () => {
  const shell = $('shell');
  shell.classList.toggle('menu-collapsed');
  $('menuToggle').setAttribute('aria-expanded', String(!shell.classList.contains('menu-collapsed')));
};
document.querySelectorAll('[data-page-target]').forEach(button => {
  button.onclick = () => showPage(button.dataset.pageTarget);
});
$('themeToggle').onclick = () => {
  const modes = ['system', 'light', 'dark'];
  const next = modes[(modes.indexOf(storedTheme()) + 1) % modes.length];
  localStorage.setItem('agentloop-theme', next);
  applyTheme(next);
};
$('themeMode').onchange = event => {
  localStorage.setItem('agentloop-theme', event.target.value);
  applyTheme(event.target.value);
};
prefersDark.addEventListener('change', () => { if (storedTheme() === 'system') applyTheme('system'); });
applyTheme();
updateChatMode();
loadConfigs().then(loadRuns).then(loadApps).catch(err => setMessage(err.message));
setInterval(loadRuns, 5000);
setInterval(refreshSelectedRun, 2000);
</script>
</body>
</html>
"""


class AgentLoopHandler(BaseHTTPRequestHandler):
    workspace: Path = Path.cwd()

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: Exception, status: int = 400) -> None:
        self._json({"error": str(exc)}, status)

    def _serve_run_file(self, run_id: str, filename: str, *, download: bool = False) -> None:
        if Path(filename).name != filename or filename.startswith("."):
            raise FileNotFoundError(f"Run file not found: {filename}")
        path = find_run(run_id, self.workspace) / filename
        if not path.is_file():
            raise FileNotFoundError(f"Run file not found: {filename}")
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        if download:
            self.send_header("content-disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(body)

    def _serve_app_file(self, app_name: str, filename: str = "index.html") -> None:
        safe_app = validate_config_name(app_name)
        relative = Path(filename or "index.html")
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise FileNotFoundError(f"App file not found: {filename}")
        if relative.suffix.lower() not in APP_FILE_SUFFIXES:
            raise FileNotFoundError(f"App file not found: {filename}")
        root = apps_dir(self.workspace) / safe_app
        path = (root / relative).resolve()
        if root.resolve() not in path.parents and path != root.resolve():
            raise FileNotFoundError(f"App file not found: {filename}")
        if path.is_dir():
            path = path / "index.html"
        if not path.is_file():
            raise FileNotFoundError(f"App file not found: {filename}")
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = INDEX_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/dice":
                body = DICE_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/api/configs":
                self._json(self._configs())
            elif parsed.path == "/api/apps":
                self._json({"apps": self._apps()})
            elif parsed.path == "/api/runs":
                self._json({"runs": self._runs()})
            elif parsed.path.startswith("/apps/"):
                parts = parsed.path.removeprefix("/apps/").split("/", 1)
                app_name = unquote(parts[0])
                filename = unquote(parts[1]) if len(parts) > 1 and parts[1] else "index.html"
                self._serve_app_file(app_name, filename)
            elif parsed.path.startswith("/api/loops/") and parsed.path.endswith("/runs"):
                loop_name = unquote(parsed.path.split("/")[3])
                self._json({"runs": self._runs(loop_name=loop_name)})
            elif parsed.path.startswith("/api/loops/"):
                loop_name = unquote(parsed.path.split("/")[3])
                self._json(self._loop_detail(loop_name))
            elif parsed.path.startswith("/api/templates/"):
                template_name = unquote(parsed.path.split("/")[3])
                self._json(self._template_detail(template_name))
            elif parsed.path.startswith("/api/runs/") and "/files/" in parsed.path:
                parts = parsed.path.split("/")
                run_id = unquote(parts[3])
                filename = unquote(parts[5])
                download = parse_qs(parsed.query).get("download") == ["1"]
                self._serve_run_file(run_id, filename, download=download)
            elif parsed.path.startswith("/api/runs/"):
                run_id = parsed.path.split("/")[3]
                self._json(self._run_detail(run_id))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._body()
            if parsed.path == "/api/dry-run":
                self._json(self._dry_run(payload))
            elif parsed.path == "/api/run":
                self._json(self._start_run(payload))
            elif parsed.path == "/api/chat":
                self._json(self._chat(payload))
            elif parsed.path == "/api/templates":
                self._json(self._create_template(payload))
            elif parsed.path.startswith("/api/templates/") and parsed.path.endswith("/copy"):
                template_name = unquote(parsed.path.split("/")[3])
                self._json(self._copy_template(template_name, payload))
            elif parsed.path.startswith("/api/runs/") and parsed.path.endswith("/stop"):
                run_id = parsed.path.split("/")[3]
                request_stop(run_id, self.workspace)
                self._json({"ok": True})
            elif parsed.path.startswith("/api/runs/") and parsed.path.endswith("/rerun"):
                run_id = parsed.path.split("/")[3]
                self._json(self._rerun(run_id, payload))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def do_PUT(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._body()
            if parsed.path.startswith("/api/loops/"):
                loop_name = unquote(parsed.path.split("/")[3])
                self._json(self._save_loop(loop_name, payload))
            elif parsed.path.startswith("/api/templates/"):
                template_name = unquote(parsed.path.split("/")[3])
                self._json(self._save_template(template_name, payload))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def _config_item(self, path: Path, kind: str) -> dict:
        try:
            loop = load_loop(path, self.workspace)
            return {
                "name": loop.name,
                "kind": kind,
                "path": str(path),
                "description": loop.description,
                "variables": [
                    {
                        "name": variable.name,
                        "required": variable.required,
                        "default": None if variable.secret else variable.default,
                        "secret": variable.secret,
                        "description": variable.description,
                    }
                    for variable in loop.variables
                ],
            }
        except ConfigError as exc:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            name = data.get("name") if isinstance(data, dict) else None
            return {
                "name": str(name or path.stem),
                "kind": kind,
                "path": str(path),
                "description": "",
                "variables": [],
                "error": str(exc),
            }

    def _configs(self) -> dict:
        return {
            "workspace": str(self.workspace),
            "loops": [self._config_item(path, "loops") for path in list_configs("loops", self.workspace)],
            "templates": [self._config_item(path, "templates") for path in list_configs("templates", self.workspace)],
        }

    def _apps(self) -> list[dict]:
        root = apps_dir(self.workspace)
        if not root.exists():
            return []
        apps = []
        for path in sorted(item for item in root.iterdir() if item.is_dir()):
            try:
                name = validate_config_name(path.name)
            except ConfigError:
                continue
            if (path / "index.html").is_file():
                apps.append({"name": name, "path": str(path), "url": f"/apps/{name}/"})
        return apps

    def _template_payload(self, path: Path) -> dict:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {"name": data.get("name") or path.stem, "path": str(path), "yaml": path.read_text(encoding="utf-8")}

    def _loop_payload(self, path: Path) -> dict:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {"name": data.get("name") or path.stem, "path": str(path), "yaml": path.read_text(encoding="utf-8")}

    def _loop_detail(self, loop_name: str) -> dict:
        return self._loop_payload(find_config(loop_name, "loops", self.workspace))

    def _template_detail(self, template_name: str) -> dict:
        return self._template_payload(find_config(template_name, "templates", self.workspace))

    def _create_template(self, payload: dict) -> dict:
        name = str(payload.get("name") or "")
        data = payload.get("data") or default_template_data(name)
        path = create_template(name, self.workspace, data=data, overwrite=bool(payload.get("force", False)))
        return self._template_payload(path)

    def _copy_template(self, template_name: str, payload: dict) -> dict:
        target_name = str(payload.get("name") or "")
        path = copy_template(template_name, target_name, self.workspace, overwrite=bool(payload.get("force", False)))
        return self._template_payload(path)

    def _save_template(self, template_name: str, payload: dict) -> dict:
        if "yaml" not in payload:
            raise ConfigError("Missing yaml")
        data = yaml.safe_load(str(payload["yaml"])) or {}
        data["name"] = template_name
        path = write_template(template_name, data, self.workspace, overwrite=True)
        return self._template_payload(path)

    def _save_loop(self, loop_name: str, payload: dict) -> dict:
        if "yaml" not in payload:
            raise ConfigError("Missing yaml")
        data = yaml.safe_load(str(payload["yaml"])) or {}
        data["name"] = loop_name
        path = write_loop_config(loop_name, data, self.workspace, overwrite=True)
        return self._loop_payload(path)

    def _merge_requirement_text(self, existing: object, requirement: str) -> str:
        current = str(existing or "").strip()
        line = requirement.strip()
        if not line:
            raise ConfigError("Chat message is empty")
        if line in current:
            return current
        return "\n".join(item for item in [current, f"- {line}"] if item)

    def _ensure_acceptance_variable(self, data: dict) -> None:
        variables = data.setdefault("variables", [])
        if not isinstance(variables, list):
            raise ConfigError("variables must be a list")
        for variable in variables:
            if isinstance(variable, dict) and variable.get("name") == "acceptance_criteria":
                variable["required"] = False
                return
        variables.append({"name": "acceptance_criteria", "required": False, "default": ""})

    def _slug_from_text(self, text: str, fallback: str = "app-idea") -> str:
        words = [word.lower() for word in WORD_PATTERN.findall(text)]
        stop_words = {
            "a",
            "an",
            "and",
            "app",
            "application",
            "build",
            "create",
            "for",
            "i",
            "idea",
            "make",
            "me",
            "of",
            "the",
            "to",
            "want",
            "with",
        }
        useful = [word for word in words if word not in stop_words]
        slug = "-".join(useful[:5]) or fallback
        slug = re.sub(r"[^a-z0-9_.-]+", "-", slug).strip("-._")
        return validate_config_name(slug or fallback)

    def _unique_config_name(self, kind: str, base_name: str) -> str:
        validate_config_name(base_name)
        for index in range(1, 100):
            name = base_name if index == 1 else f"{base_name}-{index}"
            try:
                find_config(name, kind, self.workspace)
            except ConfigError:
                return name
        raise ConfigError(f"Could not find an available {kind[:-1]} name for {base_name}")

    def _unique_app_name(self, base_name: str) -> str:
        validate_config_name(base_name)
        existing = {app["name"] for app in self._apps()}
        for index in range(1, 100):
            name = base_name if index == 1 else f"{base_name}-{index}"
            if name not in existing and not (apps_dir(self.workspace) / name).exists():
                return name
        raise ConfigError(f"Could not find an available app name for {base_name}")

    def _sentences_from_message(self, message: str) -> list[str]:
        lines = [line.strip(" -\t") for line in message.splitlines() if line.strip(" -\t")]
        if len(lines) > 1:
            return lines
        parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", message) if part.strip()]
        return parts or [message.strip()]

    def _question_planner_prompt(self, message: str, data: dict | None = None) -> str:
        context = ""
        if data:
            values = self._draft_values(data)
            context = "\nCurrent draft values:\n" + yaml.safe_dump(values, sort_keys=False)
        return (
            "You are helping AgentLoop turn a user's app idea into precise build requirements.\n"
            "Generate follow-up questions that are specific to this exact app idea.\n\n"
            "Guidance, not wording to copy:\n"
            "- Ask about concrete features, screens, states, and user interactions.\n"
            "- Ask how testing or validation should work, including commands when relevant.\n"
            "- Ask about library, framework, data, and styling preferences only when not already clear.\n"
            "- Ask about performance, accessibility, mobile, offline, or animation polish only when useful.\n\n"
            "Rules:\n"
            "- Do not use generic boilerplate questions.\n"
            "- Do not concatenate extracted keywords into awkward phrases.\n"
            "- Each question must sound natural and be grounded in the app idea.\n"
            "- Return only JSON: an array of 1 to 4 objects.\n"
            "- Each object must have field and question keys.\n"
            "- field must be one of: feature_details, testing_plan, library_preferences, performance_priority, acceptance_criteria.\n\n"
            f"User app idea:\n{message}\n"
            f"{context}"
        )

    def _run_question_planner(self, prompt: str) -> str:
        from agentloop.adapters.codex.adapter import CodexAdapter

        command = [
            *CodexAdapter()._codex_command_prefix(),
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "danger-full-access",
            "-c",
            'approval_policy="never"',
            prompt,
        ]
        completed = subprocess.run(  # nosec B603
            command,
            cwd=self.workspace,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=45,
            check=False,
        )
        if completed.returncode != 0:
            raise ConfigError(f"Question planner failed: {completed.stdout.strip()}")
        return completed.stdout

    def _extract_json_array(self, text: str) -> list:
        stripped = text.strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("[")
            end = stripped.rfind("]")
            if start < 0 or end <= start:
                raise ConfigError("Question planner did not return a JSON array")
            data = json.loads(stripped[start : end + 1])
        if not isinstance(data, list):
            raise ConfigError("Question planner must return a JSON array")
        return data

    def _idea_followup_plan(self, message: str, data: dict | None = None) -> list[dict[str, str]]:
        raw = self._run_question_planner(self._question_planner_prompt(message, data))
        allowed_fields = {"feature_details", "testing_plan", "library_preferences", "performance_priority", "acceptance_criteria"}
        plan: list[dict[str, str]] = []
        for item in self._extract_json_array(raw):
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            question = str(item.get("question") or "").strip()
            if field not in allowed_fields or not question:
                continue
            plan.append({"field": field, "question": question})
            if len(plan) >= 4:
                break
        if not plan:
            raise ConfigError("Question planner returned no usable questions")
        return plan

    def _idea_followup_questions(self, message: str, data: dict | None = None) -> list[str]:
        return [item["question"] for item in self._idea_followup_plan(message, data)]

    def _extract_check_command(self, message: str) -> str:
        for line in message.splitlines():
            lower = line.lower()
            if "check" in lower or "test" in lower or "command" in lower:
                candidate = line.split(":", 1)[-1].strip()
                if self._looks_like_shell_command(candidate):
                    return candidate
        return "true"

    def _app_idea_config(self, message: str) -> tuple[str, dict, dict]:
        name = self._slug_from_text(message)
        app_slug = self._unique_app_name(name)
        sentences = self._sentences_from_message(message)
        features = "\n".join(f"- {sentence}" for sentence in sentences[:8])
        lower = message.lower()
        library_preferences = "Use the existing project stack and conventions."
        mentioned_libraries = [
            token
            for token in ("React", "Vue", "Svelte", "FastAPI", "Django", "Flask", "SQLite", "Postgres", "Tailwind", "Playwright")
            if token.lower() in lower
        ]
        if mentioned_libraries:
            library_preferences = "Prefer " + ", ".join(mentioned_libraries) + " where they fit the existing project."
        performance_priority = "Normal priority unless the user specifies scale, latency, mobile, or offline constraints."
        if any(word in lower for word in ("performance", "fast", "latency", "scale", "mobile", "offline")):
            performance_priority = "High priority. Preserve responsive interactions and call out performance tradeoffs."
        testing_plan = "Run the repository's relevant tests. If no tests exist, add focused tests or document a manual verification path."
        check_command = self._extract_check_command(message)
        followup_plan = self._idea_followup_plan(message)
        followup_questions = [item["question"] for item in followup_plan]
        data = {
            "name": name,
            "description": f"Generated from free-form chat: {sentences[0][:140]}",
            "adapter": "codex",
            "prompt": (
                "Build or update the app from this idea.\n\n"
                "Deployment target:\n"
                "- Build the app under .agentloop/apps/{{ app_slug }}/.\n"
                "- The app must be usable at {{ app_endpoint }} inside AgentLoop.\n"
                "- Put a working index.html at .agentloop/apps/{{ app_slug }}/index.html.\n"
                "- Do not reuse /dice, Dice RNG, dice-rng-3d, or another app's directory unless explicitly requested.\n\n"
                "App idea:\n{{ app_idea }}\n\n"
                "Features and behavior:\n{{ feature_details }}\n\n"
                "Testing plan:\n{{ testing_plan }}\n\n"
                "Library preferences:\n{{ library_preferences }}\n\n"
                "Performance and quality priorities:\n{{ performance_priority }}\n\n"
                "Acceptance criteria:\n{{ acceptance_criteria }}\n\n"
                "Open questions to resolve before or during implementation:\n{{ followup_questions }}\n\n"
                "If a required product decision cannot be inferred, ask a focused question or respond with BLOCKED: and explain what is missing."
            ),
            "max_iterations": 3,
            "variables": [
                {"name": "app_idea", "required": True, "default": message},
                {"name": "app_slug", "required": True, "default": app_slug},
                {"name": "app_endpoint", "required": True, "default": f"/apps/{app_slug}/"},
                {"name": "feature_details", "required": False, "default": features},
                {"name": "testing_plan", "required": False, "default": testing_plan},
                {"name": "library_preferences", "required": False, "default": library_preferences},
                {"name": "performance_priority", "required": False, "default": performance_priority},
                {"name": "acceptance_criteria", "required": False, "default": "Implement the app idea, keep the UX coherent, and verify the result."},
                {"name": "followup_questions", "required": False, "default": "\n".join(f"- {question}" for question in followup_questions)},
                {"name": "followup_question_plan", "required": False, "default": json.dumps(followup_plan)},
                {"name": "check_command", "required": False, "default": check_command},
            ],
            "checks": [{"name": "objective check", "command": "{{ check_command }}"}],
        }
        values = {item["name"]: item.get("default", "") for item in data["variables"] if isinstance(item, dict)}
        return name, data, values

    def _variable_default(self, data: dict, name: str) -> str:
        for variable in data.get("variables", []):
            if isinstance(variable, dict) and variable.get("name") == name:
                return str(variable.get("default") or "")
        return ""

    def _set_variable_default(self, data: dict, name: str, value: str) -> None:
        variables = data.setdefault("variables", [])
        if not isinstance(variables, list):
            raise ConfigError("variables must be a list")
        for variable in variables:
            if isinstance(variable, dict) and variable.get("name") == name:
                variable["default"] = value
                return
        variables.append({"name": name, "required": False, "default": value})

    def _draft_values(self, data: dict) -> dict:
        return {item["name"]: item.get("default", "") for item in data.get("variables", []) if isinstance(item, dict)}

    def _question_fields_from_plan(self, plan: list[dict[str, str]]) -> dict[str, str]:
        return {item["question"]: item["field"] for item in plan if item.get("question") and item.get("field")}

    def _followup_plan_from_data(self, data: dict) -> list[dict[str, str]]:
        raw = self._variable_default(data, "followup_question_plan")
        if not raw:
            return []
        loaded = json.loads(raw)
        if not isinstance(loaded, list):
            return []
        return [
            {"field": str(item.get("field") or ""), "question": str(item.get("question") or "")}
            for item in loaded
            if isinstance(item, dict) and item.get("field") and item.get("question")
        ]

    def _draft_payload(
        self,
        data: dict,
        questions: list[str],
        current_question: str | None = None,
        answered: list[str] | None = None,
        question_fields: dict[str, str] | None = None,
    ) -> dict:
        return {
            "name": str(data.get("name") or "app-idea"),
            "data": data,
            "questions": questions,
            "current_question": current_question,
            "answered": answered or [],
            "question_fields": question_fields or {},
        }

    def _question_variable(self, question: str) -> str:
        lower = question.lower()
        if "feature" in lower or "screen" in lower or "users directly do" in lower or "states should be visible" in lower:
            return "feature_details"
        if "testing" in lower or "test command" in lower or "objective check" in lower or "prove" in lower or "manual checks" in lower:
            return "testing_plan"
        if "library" in lower or "framework" in lower or "database" in lower or "styling" in lower:
            return "library_preferences"
        if "performance" in lower or "accessibility" in lower or "mobile" in lower or "offline" in lower or "polished" in lower or "load speed" in lower:
            return "performance_priority"
        return "acceptance_criteria"

    def _append_answer_to_draft(self, draft: dict, answer: str) -> dict:
        data = dict(draft.get("data") or {})
        current_question = str(draft.get("current_question") or "")
        answered = list(draft.get("answered") or [])
        questions = [str(question) for question in draft.get("questions") or []]
        question_fields = {str(key): str(value) for key, value in dict(draft.get("question_fields") or {}).items()}
        if current_question:
            variable_name = question_fields.get(current_question) or self._question_variable(current_question)
            current = self._variable_default(data, variable_name).strip()
            line = answer.strip()
            if variable_name == "testing_plan":
                check_command = self._extract_check_command(answer)
                if check_command != "true":
                    self._set_variable_default(data, "check_command", check_command)
            merged = "\n".join(item for item in [current, f"- {line}"] if item)
            self._set_variable_default(data, variable_name, merged)
            if current_question not in answered:
                answered.append(current_question)
        remaining = [question for question in questions if question not in answered]
        next_question = remaining[0] if remaining else None
        return self._draft_payload(data, questions, next_question, answered, question_fields)

    def _chat_conversation(self, payload: dict) -> dict:
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ConfigError("Chat message is required")
        draft = payload.get("draft")
        if not draft:
            base_name, data, _values = self._app_idea_config(message)
            plan = self._followup_plan_from_data(data)
            questions = [item["question"] for item in plan]
            question_fields = self._question_fields_from_plan(plan)
            current_question = questions[0] if questions else None
            draft_payload = self._draft_payload(data, questions, current_question, [], question_fields)
            if current_question:
                response = (
                    f"I'll shape this into a build loop named {base_name}.\n\n"
                    f"{current_question}"
                )
            else:
                response = (
                    f"I have enough to draft {base_name}. You can keep adding details, "
                    "or create a template, loop, or run when ready."
                )
            return {
                "message": response,
                "draft": draft_payload,
                "ready": current_question is None,
                "yaml": yaml.safe_dump(data, sort_keys=False),
            }

        draft_payload = self._append_answer_to_draft(draft, message)
        current_question = draft_payload.get("current_question")
        name = draft_payload["name"]
        if current_question:
            response = str(current_question)
        else:
            response = (
                f"I have enough requirements for {name}. You can keep adding refinements, "
                "or use the create buttons below."
            )
        return {
            "message": response,
            "draft": draft_payload,
            "ready": current_question is None,
            "yaml": yaml.safe_dump(draft_payload["data"], sort_keys=False),
        }

    def _chat_conversation_create(self, payload: dict) -> dict:
        draft = payload.get("draft") or {}
        data = dict(draft.get("data") or {})
        if not data:
            raise ConfigError("Start a chat draft before creating a template, loop, or run")
        create = str(payload.get("create") or "template")
        base_name = validate_config_name(str(data.get("name") or draft.get("name") or "app-idea"))
        values = self._draft_values(data)
        if create == "template":
            name = self._unique_config_name("templates", base_name)
            data["name"] = name
            path = write_template(name, data, self.workspace)
            draft["data"] = data
            return {
                "message": f"Created template {name}.",
                "draft": draft,
                "target": {"kind": "templates", "name": name},
                **self._template_payload(path),
            }
        if create in {"loop", "run"}:
            name = self._unique_config_name("loops", base_name)
            data["name"] = name
            path = write_loop_config(name, data, self.workspace)
            draft["data"] = data
            result = {
                "message": f"Created loop {name}.",
                "draft": draft,
                "target": {"kind": "loops", "name": name},
                "kind": "loops",
                **self._loop_payload(path),
            }
            if create == "run":
                loop = load_loop(path, self.workspace)
                started = self._start_loaded_loop(loop, self._normalize_run_values(values))
                result.update(started)
                result["message"] = f"Created loop {name} and started {started['run_id']}."
            return result
        raise ConfigError(f"Unknown create option: {create}")

    def _chat_app_idea(self, payload: dict) -> dict:
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ConfigError("Chat message is required")
        create = str(payload.get("create") or "draft")
        base_name, data, values = self._app_idea_config(message)
        plan = self._followup_plan_from_data(data)
        questions = [item["question"] for item in plan]
        question_text = "\n".join(f"- {question}" for question in questions) or "- No obvious gaps. You can refine features, tests, libraries, or performance goals any time."
        response: dict[str, object] = {
            "message": (
                f"Drafted {base_name} from the app idea.\n\n"
                f"Follow-up questions:\n{question_text}"
            ),
            "name": base_name,
            "data": data,
            "questions": questions,
            "yaml": yaml.safe_dump(data, sort_keys=False),
        }
        if create == "draft":
            return response
        if create == "template":
            name = self._unique_config_name("templates", base_name)
            data["name"] = name
            path = write_template(name, data, self.workspace)
            return {
                **response,
                "message": f"Created template {name}.\n\nFollow-up questions:\n{question_text}",
                "target": {"kind": "templates", "name": name},
                **self._template_payload(path),
            }
        if create in {"loop", "run"}:
            name = self._unique_config_name("loops", base_name)
            data["name"] = name
            path = write_loop_config(name, data, self.workspace)
            loop_payload = self._loop_payload(path)
            result = {
                **response,
                "message": f"Created loop {name}.\n\nFollow-up questions:\n{question_text}",
                "target": {"kind": "loops", "name": name},
                "kind": "loops",
                **loop_payload,
            }
            if create == "run":
                loop = load_loop(path, self.workspace)
                started = self._start_loaded_loop(loop, self._normalize_run_values(values))
                result.update(started)
                result["message"] = f"Created loop {name} and started {started['run_id']}.\n\nFollow-up questions:\n{question_text}"
            return result
        raise ConfigError(f"Unknown app idea create option: {create}")

    def _append_requirement_to_config(self, kind: str, name: str, requirement: str) -> dict:
        if kind not in {"loops", "templates"}:
            raise ConfigError("Config updates require a loop or template target")
        path = find_config(name, kind, self.workspace)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._ensure_acceptance_variable(data)
        for variable in data["variables"]:
            if isinstance(variable, dict) and variable.get("name") == "acceptance_criteria":
                variable["default"] = self._merge_requirement_text(variable.get("default"), requirement)
                break
        prompt = str(data.get("prompt") or data.get("prompt_file") or "")
        if data.get("prompt") and "{{ acceptance_criteria }}" not in prompt:
            data["prompt"] = f"{prompt.rstrip()}\n\nAdditional requirements:\n{{{{ acceptance_criteria }}}}\n"
        if kind == "loops":
            saved = write_loop_config(name, data, self.workspace, overwrite=True)
            return {"kind": "loops", **self._loop_payload(saved)}
        saved = write_template(name, data, self.workspace, overwrite=True)
        return {"kind": "templates", **self._template_payload(saved)}

    def _save_chat_attachments(self, payload: dict) -> list[Path]:
        saved: list[Path] = []
        attachments = payload.get("attachments") or []
        if not isinstance(attachments, list):
            raise ConfigError("attachments must be a list")
        root = uploads_dir(self.workspace)
        root.mkdir(parents=True, exist_ok=True)
        for item in attachments:
            if not isinstance(item, dict):
                raise ConfigError("attachment entries must be objects")
            media_type = str(item.get("type") or "")
            if not media_type.startswith("image/"):
                raise ConfigError("Only image attachments are supported")
            original_name = Path(str(item.get("name") or "image")).name
            suffix = Path(original_name).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                extension = mimetypes.guess_extension(media_type) or ".png"
                suffix = ".jpg" if extension == ".jpe" else extension
            if suffix not in IMAGE_SUFFIXES:
                raise ConfigError("Unsupported image type")
            try:
                content = base64.b64decode(str(item.get("data") or ""), validate=True)
            except (ValueError, TypeError) as exc:
                raise ConfigError("Invalid image attachment data") from exc
            if not content:
                raise ConfigError("Image attachment is empty")
            if len(content) > 10 * 1024 * 1024:
                raise ConfigError("Image attachment exceeds 10 MB")
            safe_stem = self._slug_from_text(Path(original_name).stem, "image")
            path = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe_stem}-{uuid.uuid4().hex[:8]}{suffix}"
            path.write_bytes(content)
            saved.append(path)
        return saved

    def _message_with_attachments(self, payload: dict) -> str:
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ConfigError("Chat message is required")
        paths = self._save_chat_attachments(payload)
        if not paths:
            return message
        lines = ["", "Attached images for the AI to inspect:"]
        lines.extend(f"- {path}" for path in paths)
        return message + "\n" + "\n".join(lines)

    def _chat(self, payload: dict) -> dict:
        message = self._message_with_attachments(payload)
        payload = {**payload, "message": message}
        target = payload.get("target") or {}
        kind = str(target.get("kind") or "")
        name = str(target.get("name") or "")
        action = str(payload.get("action") or "auto")
        if action == "conversation":
            return self._chat_conversation(payload)
        if action == "conversation_create":
            return self._chat_conversation_create(payload)
        if action == "idea" or kind == "new":
            return self._chat_app_idea(payload)
        if not kind or not name:
            raise ConfigError("Select a run, loop, or template for chat")

        if action == "auto":
            action = "rerun" if kind == "runs" else "update"

        if action == "update":
            updated = self._append_requirement_to_config(kind, name, message)
            return {
                "message": f"Added requirement to {kind[:-1]} {name}.",
                "target": {"kind": updated["kind"], "name": updated["name"]},
                "yaml": updated["yaml"],
            }

        if action == "rerun":
            if kind == "runs":
                source_path, values = read_rerun_request(name, self.workspace)
                loop = load_loop(source_path, self.workspace)
            elif kind in {"loops", "templates"}:
                loop = self._load_run_loop({"kind": kind, "name": name})
                values = {"task_description": message}
            else:
                raise ConfigError("Rerun requires a run, loop, or template target")
            values = dict(values)
            values["acceptance_criteria"] = self._merge_requirement_text(values.get("acceptance_criteria"), message)
            response = self._start_loaded_loop(loop, self._normalize_run_values(values))
            return {
                "message": f"Started {response['run_id']} with the added requirement.",
                **response,
            }

        raise ConfigError(f"Unknown chat action: {action}")

    def _load_payload_loop(self, payload: dict):
        kind = payload.get("kind") or "loops"
        name = payload.get("name")
        path = payload.get("path")
        if path:
            return load_loop(Path(path), self.workspace)
        return load_loop(find_config(name, kind, self.workspace), self.workspace)

    def _materialized_template_loop(self, payload: dict):
        template_name = validate_config_name(str(payload.get("name") or ""))
        template_path = Path(payload["path"]) if payload.get("path") else find_config(template_name, "templates", self.workspace)
        data = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
        data["template_source"] = template_name

        candidate_name = validate_config_name(str(data.get("name") or template_name))
        for index in range(1, 100):
            loop_name = candidate_name if index == 1 else f"{candidate_name}-{index}"
            try:
                existing_path = find_config(loop_name, "loops", self.workspace)
            except ConfigError:
                data["name"] = loop_name
                return load_loop(write_loop_config(loop_name, data, self.workspace), self.workspace)

            existing_data = yaml.safe_load(existing_path.read_text(encoding="utf-8")) or {}
            if existing_data.get("template_source") == template_name:
                data["name"] = loop_name
                return load_loop(write_loop_config(loop_name, data, self.workspace, overwrite=True), self.workspace)

        raise ConfigError(f"Could not create loop from template: {template_name}")

    def _load_run_loop(self, payload: dict):
        if payload.get("kind") == "templates":
            return self._materialized_template_loop(payload)
        return self._load_payload_loop(payload)

    def _looks_like_shell_command(self, value: str) -> bool:
        command = value.strip()
        if not command:
            return False
        if any(token in command for token in ("&&", "||", ";", "|", "$", ">", "<", "=", "(", ")")):
            return True
        first = command.split()[0]
        if first.startswith(("./", "../", "/")):
            return Path(first).exists()
        return shutil.which(first) is not None

    def _normalize_run_values(self, values: dict) -> dict:
        normalized = dict(values)
        check_command = str(normalized.get("check_command") or "").strip()
        if check_command and not self._looks_like_shell_command(check_command):
            acceptance = str(normalized.get("acceptance_criteria") or "").strip()
            normalized["acceptance_criteria"] = "\n".join(item for item in [acceptance, check_command] if item)
            normalized["check_command"] = "true"
        return normalized

    def _dry_run(self, payload: dict) -> dict:
        loop = self._load_payload_loop(payload)
        result = execute_loop(loop, self._normalize_run_values(payload.get("values") or {}), dry=True)
        if not isinstance(result, DryRunResult):
            raise ConfigError("Expected dry-run result")
        safe_values = redact_mapping(result.values, secret_names(loop.variables))
        return {"prompt": result.prompt, "commands": result.commands, "values": safe_values}

    def _start_run(self, payload: dict) -> dict:
        loop = self._load_run_loop(payload)
        values = self._normalize_run_values(payload.get("values") or {})
        max_iterations = payload.get("max_iterations")
        return self._start_loaded_loop(loop, values, max_iterations=max_iterations)

    def _start_loaded_loop(self, loop, values: dict, max_iterations: int | None = None) -> dict:
        holder: dict[str, str] = {}

        def target() -> None:
            result = execute_loop(
                loop,
                values,
                max_iterations=max_iterations,
                on_run_started=lambda run_id, _run_dir: holder.setdefault("run_id", run_id),
            )
            if not isinstance(result, DryRunResult):
                holder["run_id"] = result.run_id

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        deadline = time.time() + 2
        while "run_id" not in holder and thread.is_alive() and time.time() < deadline:
            thread.join(0.02)
        return {"started": True, "run_id": holder.get("run_id", "pending"), "loop": loop.name}

    def _rerun(self, run_id: str, payload: dict) -> dict:
        source_path, values = read_rerun_request(run_id, self.workspace)
        loop = load_loop(source_path, self.workspace)
        max_iterations = payload.get("max_iterations")
        return self._start_loaded_loop(loop, self._normalize_run_values(values), max_iterations=max_iterations)

    def _run_metadata(self, path: Path) -> dict:
        run_yaml = path / "run.yaml"
        run_data = yaml.safe_load(run_yaml.read_text(encoding="utf-8")) if run_yaml.exists() else {}
        summary = path / "summary.json"
        summary_data = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
        status = summary_data.get("status") or run_data.get("status")
        reason = summary_data.get("reason") or run_data.get("reason")
        if status == "running" and (path / "STOP").exists():
            status = "stopped"
            reason = reason or "stop requested"
        return {
            "run_id": path.name,
            "loop": run_data.get("loop"),
            "status": status,
            "reason": reason,
        }

    def _runs(self, loop_name: str | None = None) -> list[dict]:
        runs = []
        for path in list_runs(self.workspace):
            metadata = self._run_metadata(path)
            if loop_name is None or metadata.get("loop") == loop_name:
                runs.append(metadata)
        return runs

    def _final_artifacts(self, run_id: str, path: Path, detail: dict) -> list[dict]:
        artifacts: list[dict] = []
        seen: set[str] = set()
        app_endpoint_added = False

        def add(name: str, url: str, download_url: str | None = None) -> None:
            key = f"{name}:{url}"
            if key in seen:
                return
            seen.add(key)
            artifact = {"name": name, "url": url}
            if download_url:
                artifact["download_url"] = download_url
            artifacts.append(artifact)

        if (path / "final_report.md").exists():
            add(
                "Final report",
                f"/api/runs/{run_id}/files/final_report.md",
                f"/api/runs/{run_id}/files/final_report.md?download=1",
            )
        variables_path = path / "variables.yaml"
        if variables_path.exists():
            values = yaml.safe_load(variables_path.read_text(encoding="utf-8")) or {}
            if isinstance(values, dict):
                app_slug = str(values.get("app_slug") or "").strip()
                app_endpoint = str(values.get("app_endpoint") or "").strip()
                if app_slug:
                    endpoint = app_endpoint if app_endpoint.startswith("/apps/") else f"/apps/{app_slug}/"
                    add(app_slug, endpoint)
                    app_endpoint_added = True
        loop_app = str(detail.get("loop") or "").strip()
        if loop_app and (apps_dir(self.workspace) / loop_app / "index.html").is_file():
            add(loop_app, f"/apps/{loop_app}/")
            app_endpoint_added = True
        searchable = "\n".join(
            [
                str(detail.get("report") or ""),
                str(detail.get("event_log") or ""),
                *[str(log.get("content") or "") for log in detail.get("logs", [])],
            ]
        )
        for app_url in APP_URL_PATTERN.findall(searchable):
            name = app_url.removeprefix("/apps/").strip("/") or app_url
            add(name, app_url if app_url.endswith("/") else f"{app_url}/")
        recent_text = "\n".join(
            [
                str(detail.get("report") or ""),
                str(detail.get("event_log") or ""),
                *[str(log.get("content") or "")[-4000:] for log in detail.get("logs", [])],
            ]
        )
        for url in URL_PATTERN.findall(recent_text):
            clean_url = url.rstrip(".,")
            parsed_url = urlparse(clean_url)
            if app_endpoint_added and parsed_url.hostname in {"127.0.0.1", "localhost"} and not parsed_url.path.startswith("/apps/"):
                continue
            add(clean_url, clean_url)
        return artifacts

    def _run_detail(self, run_id: str) -> dict:
        path = find_run(run_id, self.workspace)
        metadata = self._run_metadata(path)
        run_log = path / "run.log"
        run_log_url = f"/api/runs/{run_id}/files/run.log" if run_log.exists() else None
        event_log = run_log.read_text(encoding="utf-8") if run_log.exists() else ""
        detail = {
            **metadata,
            "files": sorted(item.name for item in path.iterdir() if not item.name.startswith(".")),
            "logs": [],
            "attachments": [],
            "final_artifacts": [],
            "event_log": event_log,
            "run_log_url": run_log_url,
        }
        summary = path / "summary.json"
        if summary.exists():
            detail["summary"] = json.loads(summary.read_text(encoding="utf-8"))
        report = path / "final_report.md"
        if report.exists():
            detail["report"] = report.read_text(encoding="utf-8")
        seen_logs: set[str] = set()

        def add_log(log: Path) -> None:
            if log.name in seen_logs:
                return
            seen_logs.add(log.name)
            detail["logs"].append(
                {
                    "name": log.name,
                    "content": log.read_text(encoding="utf-8"),
                    "url": f"/api/runs/{run_id}/files/{log.name}",
                    "download_url": f"/api/runs/{run_id}/files/{log.name}?download=1",
                }
            )

        for log in sorted([run_log] if run_log.exists() else []):
            add_log(log)
        for log in sorted(
            [*path.glob("adapter_iteration_*.live.log"), *path.glob("adapter_iteration_*.log"), *path.glob("checks_iteration_*.log")]
        ):
            add_log(log)

        live_logs = sorted(path.glob("adapter_iteration_*.live.log"))
        if live_logs:
            latest = live_logs[-1]
            live_text = latest.read_text(encoding="utf-8")
            if live_text.strip():
                detail["event_log"] = (
                    f"{event_log.rstrip()}\n\n--- latest adapter output: {latest.name} ---\n{live_text[-6000:].lstrip()}"
                ).strip()
        for attachment in sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES):
            detail["attachments"].append(
                {
                    "name": attachment.name,
                    "url": f"/api/runs/{run_id}/files/{attachment.name}",
                    "download_url": f"/api/runs/{run_id}/files/{attachment.name}?download=1",
                }
            )
        detail["final_artifacts"] = self._final_artifacts(run_id, path, detail)
        return detail


def serve(host: str = "127.0.0.1", port: int = 8765, workspace: str | Path | None = None) -> None:
    handler = type("ConfiguredAgentLoopHandler", (AgentLoopHandler,), {"workspace": Path(workspace or Path.cwd()).resolve()})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentLoop serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
