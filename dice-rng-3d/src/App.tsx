import { Canvas, useFrame } from "@react-three/fiber";
import { OrthographicCamera } from "@react-three/drei";
import * as THREE from "three";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";
import { clamp, coffeeFillGeometry, MAX_WATER, POT_CAPACITY, POT_COLORS, scoreBrew, unlockedColorCount } from "./coffeeScoring";

type BrewPhase = "setup" | "brewing" | "finished";

type Drop = {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  strength: number;
  age: number;
};

type Stain = {
  id: number;
  x: number;
  radius: number;
  strength: number;
};

type Shard = {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  rotation: number;
  spin: number;
};

type BrewStats = {
  brewed: number;
  missed: number;
  points: number;
  fullBonus: boolean;
};

const DROP_LIMIT = 86;

function Pot({
  x,
  fill,
  color,
  ripple,
  broken
}: {
  x: number;
  fill: number;
  color: string;
  ripple: number;
  broken: boolean;
}) {
  const liquid = coffeeFillGeometry(fill);
  const wave = Math.sin(ripple) * Math.min(0.045, ripple * 0.006);
  const coffeeShape = useMemo(
    () =>
      new THREE.Shape()
        .moveTo(-liquid.bottomHalfWidth, liquid.bottom)
        .lineTo(liquid.bottomHalfWidth, liquid.bottom)
        .lineTo(liquid.topHalfWidth, liquid.top + wave)
        .quadraticCurveTo(0, liquid.top + wave + 0.055, -liquid.topHalfWidth, liquid.top + wave)
        .lineTo(-liquid.bottomHalfWidth, liquid.bottom),
    [liquid.bottom, liquid.bottomHalfWidth, liquid.top, liquid.topHalfWidth, wave]
  );

  if (broken) return null;

  return (
    <group position={[x, -1.54, 0]}>
      <mesh position={[0, -0.08, 0.05]}>
        <shapeGeometry
          args={[
            new THREE.Shape()
              .moveTo(-1.05, 0.92)
              .lineTo(1.05, 0.92)
              .lineTo(0.78, -1.2)
              .quadraticCurveTo(0.55, -1.46, -0.55, -1.46)
              .lineTo(-0.78, -1.2)
              .lineTo(-1.05, 0.92)
          ]}
        />
        <meshBasicMaterial color={color} transparent opacity={0.25} />
      </mesh>
      {fill > 0 && (
        <>
          <mesh position={[0, 0, 0.08]}>
            <shapeGeometry args={[coffeeShape]} />
            <meshBasicMaterial color="#4b2516" transparent opacity={0.9} />
          </mesh>
          <mesh position={[0, liquid.top + wave + 0.012, 0.09]} scale={[1, 0.22, 1]}>
            <circleGeometry args={[liquid.topHalfWidth, 40]} />
            <meshBasicMaterial color="#98512e" transparent opacity={0.95} />
          </mesh>
        </>
      )}
      <mesh position={[-0.91, -0.16, 0.12]} rotation={[0, 0, -0.13]}>
        <planeGeometry args={[0.035, 2.25]} />
        <meshBasicMaterial color={color} transparent opacity={0.95} />
      </mesh>
      <mesh position={[0.91, -0.16, 0.12]} rotation={[0, 0, 0.13]}>
        <planeGeometry args={[0.035, 2.25]} />
        <meshBasicMaterial color={color} transparent opacity={0.95} />
      </mesh>
      <mesh position={[0, -1.43, 0.12]}>
        <planeGeometry args={[1.12, 0.035]} />
        <meshBasicMaterial color={color} transparent opacity={0.95} />
      </mesh>
      <mesh position={[1.12, -0.18, 0.11]} scale={[0.78, 1.15, 1]}>
        <torusGeometry args={[0.43, 0.09, 12, 34]} />
        <meshBasicMaterial color="#24313a" />
      </mesh>
      <mesh position={[0, 0.93, 0.14]}>
        <planeGeometry args={[2.28, 0.12]} />
        <meshBasicMaterial color="#24313a" />
      </mesh>
      <mesh position={[-0.64, 0.04, 0.14]} rotation={[0, 0, -0.12]}>
        <planeGeometry args={[0.09, 1.72]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.42} />
      </mesh>
    </group>
  );
}

function CoffeeScene({
  water,
  grounds,
  phase,
  color,
  smashToken,
  onStats,
  onFinish,
  onSmash
}: {
  water: number;
  grounds: number;
  phase: BrewPhase;
  color: string;
  smashToken: number;
  onStats: (stats: BrewStats) => void;
  onFinish: (stats: BrewStats) => void;
  onSmash: (stats: BrewStats) => void;
}) {
  const [drops, setDrops] = useState<Drop[]>([]);
  const [stains, setStains] = useState<Stain[]>([]);
  const [shards, setShards] = useState<Shard[]>([]);
  const [potX, setPotX] = useState(0);
  const [broken, setBroken] = useState(false);
  const potRef = useRef({ x: 0, vx: 0, target: 0, dragging: false, fill: 0, missed: 0, lastScore: 0, fullBonus: false });
  const ids = useRef(0);
  const emitted = useRef(0);
  const spawnClock = useRef(0);
  const ripple = useRef(0);
  const lastSmash = useRef(0);
  const finishReported = useRef(false);
  const reportClock = useRef(0);

  const currentStats = useCallback((): BrewStats => {
    const state = potRef.current;
    const points = scoreBrew(state.fill, grounds, water, state.fullBonus);
    state.lastScore = points;
    return { brewed: Math.round(state.fill), missed: Math.round(state.missed), points, fullBonus: state.fullBonus };
  }, [grounds, water]);

  const reportStats = useCallback(() => {
    onStats(currentStats());
  }, [currentStats, onStats]);

  useEffect(() => {
    if (phase !== "setup") return;
    potRef.current = { x: 0, vx: 0, target: 0, dragging: false, fill: 0, missed: 0, lastScore: 0, fullBonus: false };
    emitted.current = 0;
    spawnClock.current = 0;
    ripple.current = 0;
    setPotX(0);
    setBroken(false);
    setDrops([]);
    setStains([]);
    setShards([]);
    finishReported.current = false;
    reportStats();
  }, [phase, reportStats]);

  useEffect(() => {
    if (phase === "brewing") finishReported.current = false;
  }, [phase]);

  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.033);
    const state = potRef.current;

    if (smashToken !== lastSmash.current && !broken) {
      lastSmash.current = smashToken;
      setBroken(true);
      if (!finishReported.current) {
        finishReported.current = true;
        onSmash(currentStats());
      }
      if (state.fill > 0) {
        setStains((old) => [...old, { id: ids.current++, x: state.x, radius: 0.65 + state.fill / 115, strength: 1.2 }]);
      }
      setShards(
        Array.from({ length: 18 }, () => ({
          id: ids.current++,
          x: state.x + (Math.random() - 0.5) * 1.8,
          y: -1.8 + Math.random() * 1.8,
          vx: (Math.random() - 0.5) * 5,
          vy: 2 + Math.random() * 3,
          rotation: Math.random() * Math.PI,
          spin: (Math.random() - 0.5) * 8
        }))
      );
    }

    const stiffness = state.dragging ? 24 : 9;
    state.vx += (state.target - state.x) * stiffness * dt;
    state.vx *= Math.pow(0.08, dt);
    state.x = clamp(state.x + state.vx * dt, -3.2, 3.2);
    setPotX(state.x);

    if (phase === "brewing" && !broken && emitted.current < water) {
      spawnClock.current += dt * (0.8 + grounds / 35);
      while (spawnClock.current > 0.09 && emitted.current < water && drops.length < DROP_LIMIT) {
        spawnClock.current -= 0.09;
        emitted.current += 0.72;
        setDrops((current) => [
          ...current,
          {
            id: ids.current++,
            x: (Math.random() - 0.5) * 0.16,
            y: 1.64,
            vx: (Math.random() - 0.5) * 0.14,
            vy: -0.85 - Math.random() * 0.35,
            strength: clamp(0.32 + grounds / 30, 0.45, 1.35),
            age: 0
          }
        ]);
      }
    }

    setDrops((current) => {
      const next: Drop[] = [];
      const newStains: Stain[] = [];
      for (const drop of current) {
        const nd = { ...drop, age: drop.age + dt, vy: drop.vy - 4.6 * dt };
        nd.x += nd.vx * dt;
        nd.y += nd.vy * dt;
        const inPot = !broken && nd.y < -0.38 && nd.y > -2.95 && Math.abs(nd.x - state.x) < 0.86;
        if (inPot) {
          state.fill = clamp(state.fill + 0.72, 0, POT_CAPACITY);
          ripple.current += 1.7 + Math.abs(nd.x - state.x);
          if (state.fill >= POT_CAPACITY && !state.fullBonus) state.fullBonus = true;
          continue;
        }
        if (nd.y < -3.2) {
          state.missed += 1;
          newStains.push({ id: ids.current++, x: nd.x, radius: 0.12 + Math.random() * 0.16, strength: nd.strength });
          continue;
        }
        next.push(nd);
      }
      if (newStains.length) setStains((old) => [...old.slice(-20), ...newStains]);
      return next;
    });

    setShards((current) =>
      current.map((shard) => ({
        ...shard,
        x: shard.x + shard.vx * dt,
        y: Math.max(-3.1, shard.y + shard.vy * dt),
        vy: shard.y <= -3.1 ? 0 : shard.vy - 7.4 * dt,
        rotation: shard.rotation + shard.spin * dt
      }))
    );

    ripple.current *= Math.pow(0.08, dt);
    reportClock.current += dt;
    if (reportClock.current >= 0.12) {
      reportClock.current = 0;
      reportStats();
    }

    const doneBrewing = state.fullBonus || (emitted.current >= water && drops.length === 0);
    if (phase === "brewing" && doneBrewing && !finishReported.current) {
      finishReported.current = true;
      onFinish(currentStats());
    }
  });

  const pointerX = (event: { point: THREE.Vector3 }) => clamp(event.point.x, -3.2, 3.2);

  return (
    <>
      <OrthographicCamera makeDefault position={[0, 0, 10]} zoom={70} />
      <color attach="background" args={["#f8fbff"]} />
      <ambientLight intensity={2} />
      <mesh position={[-3.52, 0.55, -0.02]}>
        <planeGeometry args={[0.58, 2.45]} />
        <meshBasicMaterial color="#dbe6eb" />
      </mesh>
      <mesh position={[-3.52, -0.67 + (1.92 * water) / MAX_WATER / 2, 0]}>
        <planeGeometry args={[0.44, (1.92 * water) / MAX_WATER]} />
        <meshBasicMaterial color="#87c9e8" transparent opacity={0.84} />
      </mesh>
      <mesh position={[-3.52, 1.88, 0.01]}>
        <boxGeometry args={[0.74, 0.12, 0.1]} />
        <meshBasicMaterial color="#33414b" />
      </mesh>
      <mesh position={[0, -3.12, -0.05]}>
        <planeGeometry args={[9, 0.45]} />
        <meshBasicMaterial color="#d9e1e6" />
      </mesh>
      <mesh position={[0, 2.22, 0]}>
        <boxGeometry args={[2.05, 0.28, 0.1]} />
        <meshBasicMaterial color="#35404a" />
      </mesh>
      <mesh position={[0, 1.96, 0]}>
        <boxGeometry args={[1.36, 0.38, 0.1]} />
        <meshBasicMaterial color="#6f4d34" />
      </mesh>
      <mesh position={[0, 1.98, 0.04]} scale={[1, 0.32 + grounds / 70, 1]}>
        <circleGeometry args={[0.54, 36]} />
        <meshBasicMaterial color="#3c2116" />
      </mesh>
      <mesh position={[0, 1.66, 0]} rotation={[0, 0, Math.PI]}>
        <coneGeometry args={[0.16, 0.36, 28]} />
        <meshBasicMaterial color="#252525" />
      </mesh>
      <mesh position={[0, 1.08, -0.02]}>
        <boxGeometry args={[3.1, 0.16, 0.1]} />
        <meshBasicMaterial color="#7e8a92" />
      </mesh>
      <mesh position={[0, -0.92, -0.03]}>
        <boxGeometry args={[3.6, 3.9, 0.08]} />
        <meshBasicMaterial color="#e9eef2" transparent opacity={0.58} />
      </mesh>
      {stains.map((stain) => (
        <mesh key={stain.id} position={[stain.x, -3.04, 0.04]} scale={[1.6, 0.45, 1]}>
          <circleGeometry args={[stain.radius, 28]} />
          <meshBasicMaterial color="#5b2d18" transparent opacity={0.22 + stain.strength * 0.12} />
        </mesh>
      ))}
      {drops.map((drop) => (
        <mesh key={drop.id} position={[drop.x, drop.y, 0.1]} scale={[0.7, 1.3, 1]}>
          <circleGeometry args={[0.055, 18]} />
          <meshBasicMaterial color="#5a2c17" transparent opacity={0.72} />
        </mesh>
      ))}
      <group
        onPointerDown={(event) => {
          event.stopPropagation();
          potRef.current.dragging = true;
          potRef.current.target = pointerX(event);
        }}
        onPointerMove={(event) => {
          if (potRef.current.dragging) potRef.current.target = pointerX(event);
        }}
        onPointerUp={(event) => {
          event.stopPropagation();
          potRef.current.dragging = false;
        }}
        onPointerLeave={() => {
          potRef.current.dragging = false;
        }}
      >
        <mesh position={[potX, -1.62, 0.01]} visible={false}>
          <planeGeometry args={[2.8, 3.2]} />
          <meshBasicMaterial transparent opacity={0} />
        </mesh>
        <Pot x={potX} fill={potRef.current.fill} color={color} ripple={ripple.current} broken={broken} />
      </group>
      {shards.map((shard) => (
        <mesh key={shard.id} position={[shard.x, shard.y, 0.16]} rotation={[0, 0, shard.rotation]}>
          <circleGeometry args={[0.16, 3]} />
          <meshBasicMaterial color={color} transparent opacity={0.62} />
        </mesh>
      ))}
    </>
  );
}

function App() {
  const [water, setWater] = useState(70);
  const [grounds, setGrounds] = useState(12);
  const [phase, setPhase] = useState<BrewPhase>("setup");
  const [smashToken, setSmashToken] = useState(0);
  const [stats, setStats] = useState<BrewStats>({ brewed: 0, missed: 0, points: 0, fullBonus: false });
  const [totalPoints, setTotalPoints] = useState(() => Number(localStorage.getItem("coffee-points") ?? 0));
  const [colorIndex, setColorIndex] = useState(() => Number(localStorage.getItem("coffee-pot-color") ?? 0));
  const [resetVersion, setResetVersion] = useState(0);
  const unlockedColors = useMemo(() => unlockedColorCount(totalPoints), [totalPoints]);

  useEffect(() => {
    localStorage.setItem("coffee-points", String(totalPoints));
  }, [totalPoints]);

  useEffect(() => {
    localStorage.setItem("coffee-pot-color", String(colorIndex));
  }, [colorIndex]);

  const finishBrew = useCallback((finalStats: BrewStats) => {
    setPhase("finished");
    setStats(finalStats);
    setTotalPoints((points) => points + finalStats.points);
  }, []);

  const startBrew = () => {
    setPhase("brewing");
    setSmashToken(0);
    setResetVersion((version) => version + 1);
    setStats({ brewed: 0, missed: 0, points: 0, fullBonus: false });
  };

  const tasteNote = phase !== "finished"
    ? "Your recipe is yours to discover"
    : stats.points >= 500
      ? "Silky, balanced, and worth repeating"
      : grounds / water < 0.11
        ? "Light-bodied with a quick finish"
        : grounds / water > 0.27
          ? "Bold, intense, and lingering"
          : "A promising cup — adjust and try again";

  return (
    <main>
      <section className="toolbar" aria-label="Coffee controls">
        <div className="brand">
          <span className="eyebrow">BREW LAB · 01</span>
          <h1 aria-label="2D Coffee Simulator">Drip Theory</h1>
          <p>A tiny physics experiment in pursuit of the perfect cup.</p>
        </div>
        <div className="controls">
          <label className="range-control">
            <span>Water</span>
            <input
              aria-label="water"
              type="range"
              min="0"
              max={MAX_WATER}
              value={water}
              disabled={phase === "brewing"}
              onChange={(event) => setWater(Number(event.target.value))}
            />
            <b>{water} ml</b>
          </label>
          <label className="range-control">
            <span>Grounds</span>
            <input
              aria-label="grounds"
              type="range"
              min="0"
              max="34"
              value={grounds}
              disabled={phase === "brewing"}
              onChange={(event) => setGrounds(Number(event.target.value))}
            />
            <b>{grounds} g</b>
          </label>
          <button aria-label="Brew" className="primary" type="button" disabled={phase === "brewing"} onClick={startBrew}>
            {phase === "finished" ? "Brew again" : "Start brew"}
          </button>
          <button type="button" onClick={() => setSmashToken((token) => token + 1)}>
            Smash
          </button>
          <button
            type="button"
            onClick={() => {
              setPhase("setup");
              setSmashToken(0);
              setResetVersion((version) => version + 1);
              setStats({ brewed: 0, missed: 0, points: 0, fullBonus: false });
            }}
          >
            Reset
          </button>
        </div>
        <div className="score-card"><span>THIS BREW</span><output aria-live="polite" className="result">{stats.points}</output><small>POINTS</small></div>
      </section>

      <section className="stage" aria-label="Interactive 2D coffee brewing scene">
        <div className="stage-note" aria-hidden="true"><span>☝</span> Hold + drag the carafe</div>
        <div className={`status-pill ${phase}`}>{phase === "brewing" ? "● Brewing" : phase === "finished" ? "Brew complete" : "Ready to brew"}</div>
        <Canvas dpr={[1, 2]} gl={{ antialias: true, alpha: false }} orthographic>
          <CoffeeScene
            key={resetVersion}
            water={water}
            grounds={grounds}
            phase={phase}
            color={POT_COLORS[colorIndex]}
            smashToken={smashToken}
            onStats={setStats}
            onFinish={finishBrew}
            onSmash={finishBrew}
          />
        </Canvas>
      </section>

      <section className="stats" aria-label="Brew score">
        <article>
          <span className="stat-number">{stats.brewed}<small>%</small></span>
          <h2>Captured</h2>
          <p>{stats.missed} drops missed the carafe</p>
        </article>
        <article>
          <h2>Carafe collection</h2>
          <div className="swatches" aria-label="pot colors">
            {POT_COLORS.map((color, index) => (
              <button
                key={color}
                type="button"
                aria-label={`select pot color ${index + 1}`}
                className={index === colorIndex ? "selected" : ""}
                disabled={index >= unlockedColors}
                onClick={() => setColorIndex(index)}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
          <p>{totalPoints} lifetime points · {unlockedColors}/{POT_COLORS.length} unlocked</p>
        </article>
        <article>
          <h2>Tasting note</h2>
          <p className="taste">{tasteNote}</p>
          <p>{stats.fullBonus ? "Full pot bonus earned" : "A complete pot pays extra"}</p>
          <p className="visually-hidden">{phase === "brewing" ? "Brewing" : phase === "finished" ? "Round finished" : "Ready"}</p>
        </article>
      </section>
    </main>
  );
}

export default App;
