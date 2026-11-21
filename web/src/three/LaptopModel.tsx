import React, { useMemo, useEffect, useRef, useState, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Float, useGLTF, ContactShadows, Environment, Grid, Html, Stars } from '@react-three/drei';
import * as THREE from 'three';
import { useLiveStore } from '../stores/liveStore';

const MODEL = '/models/laptop.glb';
useGLTF.preload(MODEL);

export interface Machine {
  id: string; tenant: string; label: string; state: string;
  risk: number;         // 0..1, shifts the glow from baseColor to red
  baseColor: string;    // healthy colour
  connected: boolean;   // offline = grey, no light
  buffer: number; lastSeen: string;
}

const SHOP_X = -9, GATE_X = 0, HQ_X = 10;
const STATE_COLOR: Record<string, string> = { Excellent: '#34d399', Good: '#a3e635', Fair: '#fbbf24', Poor: '#f43f5e', Offline: '#64748b' };

// pointer helpers: a clickable 3D object shows the hand cursor and selects itself
const clickable = (onSelect: () => void) => ({
  onClick: (e: any) => { e.stopPropagation(); onSelect(); },
  onPointerOver: (e: any) => { e.stopPropagation(); document.body.style.cursor = 'pointer'; },
  onPointerOut: () => { document.body.style.cursor = 'auto'; },
});

// just the name and a status dot: all details live in the sidebar that opens on click
function NameTag({ y, text, color }: { y: number; text: string; color: string }) {
  return (
    <Html position={[0, y, 0]} center distanceFactor={22} zIndexRange={[10, 0]}>
      <div style={{ fontFamily: 'ui-monospace,monospace', fontSize: 12, fontWeight: 800, color: '#e2e8f0', whiteSpace: 'nowrap', pointerEvents: 'none',
        textShadow: '0 0 6px #000' }}>
        <span style={{ color }}>●</span> {text}
      </div>
    </Html>
  );
}

function Laptop({ m, z, selected, onSelect }: { m: Machine; z: number; selected: boolean; onSelect: () => void }) {
  const { scene } = useGLTF(MODEL);
  const clone = useMemo(() => scene.clone(), [scene]);
  const hot = m.risk > 0.6;
  const glow = useMemo(
    () => new THREE.Color(m.connected ? m.baseColor : '#4b5563').lerp(new THREE.Color('#ef4444'), m.connected ? Math.min(1, Math.max(0, (m.risk - 0.3) * 1.5)) : 0),
    [m.baseColor, m.risk, m.connected]);
  useEffect(() => {
    clone.traverse((c: any) => {
      if (c.isMesh) {
        c.material = c.material.clone();
        if (c.material.emissive) { c.material.emissive.copy(glow); c.material.emissiveIntensity = hot ? 0.8 : selected ? 0.35 : 0.12; }
      }
    });
  }, [clone, glow, hot, selected]);
  const edge = STATE_COLOR[m.state] || '#38bdf8';
  return (
    <group position={[SHOP_X, 0, z]} rotation={[0, 0.5, 0]} {...clickable(onSelect)}>
      <Float speed={2} rotationIntensity={0.02} floatIntensity={0.1} floatingRange={[-0.08, 0.08]}>
        <primitive object={clone} scale={2.4} position={[0, -0.6, 0]} />
      </Float>
      <mesh position={[0, -1.0, 0]}>
        <cylinderGeometry args={[2.6, 2.8, 0.25, 48]} />
        <meshStandardMaterial color="#0a0c10" metalness={0.9} roughness={0.25} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.86, 0]}>
        <ringGeometry args={[selected ? 2.2 : 2.3, selected ? 3.0 : 2.6, 64]} />
        <meshBasicMaterial color={selected ? '#ffffff' : glow} transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>
      {m.connected && <pointLight position={[0, 0.5, 0]} color={glow} intensity={hot ? 4 : 1.6} distance={9} />}
      <NameTag y={3.2} text={m.label} color={edge} />
    </group>
  );
}

// Translucent trust gate: only allow-listed metadata crosses it
function Gate() {
  const edges = useMemo(() => new THREE.EdgesGeometry(new THREE.PlaneGeometry(16, 7)), []);
  return (
    <group position={[GATE_X, 2, 0]}>
      <mesh rotation={[0, Math.PI / 2, 0]}>
        <planeGeometry args={[16, 7]} />
        <meshBasicMaterial color="#a855f7" transparent opacity={0.12} side={THREE.DoubleSide} />
      </mesh>
      <lineSegments rotation={[0, Math.PI / 2, 0]} geometry={edges}>
        <lineBasicMaterial color="#c084fc" />
      </lineSegments>
      <Html position={[0, 4.2, 0]} center distanceFactor={22} zIndexRange={[10, 0]}>
        <div style={{ fontFamily: 'ui-monospace,monospace', fontSize: 11, fontWeight: 800, letterSpacing: 2, color: '#d8b4fe', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
          TRUST GATE · METADATA ONLY
        </div>
      </Html>
    </group>
  );
}

function HeadOffice({ selected, onSelect }: { selected: boolean; onSelect: () => void }) {
  return (
    <group position={[HQ_X, 0, 0]} {...clickable(onSelect)}>
      {[0, 1, 2, 3].map((i) => (
        <group key={i} position={[0, -0.4 + i * 1.5, 0]}>
          <mesh><boxGeometry args={[3.2, 1.3, 2.4]} /><meshStandardMaterial color={selected ? '#1b2436' : '#0f131c'} metalness={0.8} roughness={0.35} emissive={selected ? '#38bdf8' : '#000000'} emissiveIntensity={selected ? 0.25 : 0} /></mesh>
          <mesh position={[-1.61, 0, 0]}><boxGeometry args={[0.04, 0.12, 2]} /><meshBasicMaterial color="#38bdf8" /></mesh>
          <mesh position={[-1.61, -0.35, 0.8]}><boxGeometry args={[0.04, 0.1, 0.1]} /><meshBasicMaterial color="#34d399" /></mesh>
        </group>
      ))}
      <pointLight position={[-2, 3, 0]} color="#38bdf8" intensity={2} distance={10} />
      <NameTag y={6.4} text="HEAD OFFICE" color="#38bdf8" />
    </group>
  );
}

interface Packet { id: string; z: number; t: number; dup: boolean }

// One packet per real receipt: leaves the shop, crosses the gate, lands at head office
function Packets({ zs }: { zs: Record<string, number> }) {
  const receipts = useLiveStore((s) => s.receipts);
  const [packets, setPackets] = useState<Packet[]>([]);
  const lastId = useRef<string | null>(null);
  const refs = useRef<Record<string, THREE.Mesh | null>>({});
  useEffect(() => {
    const r = receipts[0];
    if (!r || r.payload_id === lastId.current) return;
    lastId.current = r.payload_id;
    setPackets((p) => [...p.slice(-14), { id: `${r.payload_id}-${Date.now()}`, z: zs[r.guard_id] ?? 0, t: 0, dup: r.status === 'duplicate' }]);
  }, [receipts, zs]);
  useFrame((_, dt) => {
    let done = false;
    for (const p of packets) {
      p.t += dt / 3;
      const m = refs.current[p.id];
      if (m) {
        m.position.set(SHOP_X + 2 + p.t * (HQ_X - SHOP_X - 4), 0.8 + Math.sin(p.t * Math.PI) * 1.2, p.z * (1 - p.t));
        m.visible = p.t < 1;
      }
      if (p.t >= 1) done = true;
    }
    if (done) setPackets((ps) => ps.filter((p) => p.t < 1));
  });
  return (
    <>
      {packets.map((p) => (
        <mesh key={p.id} ref={(el) => { refs.current[p.id] = el; }}>
          <sphereGeometry args={[0.22, 16, 16]} />
          <meshBasicMaterial color={p.dup ? '#fbbf24' : '#22d3ee'} />
        </mesh>
      ))}
    </>
  );
}

export function LaptopViewer({ machines, selected, onSelect }: { machines: Machine[]; selected: string | null; onSelect: (id: string | null) => void }) {
  const zs = useMemo(() => Object.fromEntries(machines.map((m, i) => [m.id, (i - (machines.length - 1) / 2) * 8])), [machines]);
  return (
    <Canvas camera={{ position: [14, 9, 20], fov: 48 }} style={{ background: '#05070c' }} onPointerMissed={() => onSelect(null)}>
      <fog attach="fog" args={['#05070c', 28, 70]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[6, 12, 6]} intensity={1.6} />
      <Stars radius={80} depth={30} count={1200} factor={3} fade speed={0.4} />
      <OrbitControls makeDefault minDistance={8} maxDistance={45} maxPolarAngle={Math.PI / 2.1} target={[0, 1.5, 0]} />
      <Environment preset="city" />
      <Grid position={[0, -1.15, 0]} args={[80, 80]} cellColor="#1e293b" sectionColor="#0e7490" sectionThickness={1.2} cellSize={1.5} sectionSize={7.5}
        fadeDistance={55} infiniteGrid />
      <ContactShadows position={[0, -1.1, 0]} opacity={0.4} scale={60} blur={2.5} far={4} />
      <Gate />
      <HeadOffice selected={selected === 'hq'} onSelect={() => onSelect('hq')} />
      <Suspense fallback={null}>
        {machines.map((m) => <Laptop key={m.id} m={m} z={zs[m.id]} selected={selected === m.id} onSelect={() => onSelect(m.id)} />)}
      </Suspense>
      <Packets zs={zs} />
    </Canvas>
  );
}
