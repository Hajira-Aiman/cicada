import React, { useMemo, useEffect, useRef, useState, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Float, useGLTF, ContactShadows, Environment, Grid, Html, Stars } from '@react-three/drei';
import * as THREE from 'three';
import { useLiveStore } from '../stores/liveStore';

const MODEL = '/models/laptop.glb';
useGLTF.preload(MODEL);

export interface Machine {
  id: string; label: string; state: string; region: string;
  risk: number;         // 0..1, shifts the glow from baseColor to red
  baseColor: string;    // healthy colour
  connected: boolean;   // offline = grey, no light
  cpu: number; buffer: number; lastSeen: string;
}

const SHOP_X = -9, GATE_X = 0, HQ_X = 10;
const STATE_COLOR: Record<string, string> = { Excellent: '#34d399', Good: '#a3e635', Fair: '#fbbf24', Poor: '#f43f5e', Offline: '#64748b' };

function Laptop({ m, z }: { m: Machine; z: number }) {
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
        if (c.material.emissive) { c.material.emissive.copy(glow); c.material.emissiveIntensity = hot ? 0.8 : 0.12; }
      }
    });
  }, [clone, glow, hot]);
  const ago = Math.max(0, Math.round((Date.now() - new Date(m.lastSeen).getTime()) / 1000));
  const edge = STATE_COLOR[m.state] || '#38bdf8';
  return (
    <group position={[SHOP_X, 0, z]} rotation={[0, 0.5, 0]}>
      <Float speed={2} rotationIntensity={0.02} floatIntensity={0.1} floatingRange={[-0.08, 0.08]}>
        <primitive object={clone} scale={2.4} position={[0, -0.6, 0]} />
      </Float>
      <mesh position={[0, -1.0, 0]}>
        <cylinderGeometry args={[2.6, 2.8, 0.25, 48]} />
        <meshStandardMaterial color="#0a0c10" metalness={0.9} roughness={0.25} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.86, 0]}>
        <ringGeometry args={[2.3, 2.6, 64]} />
        <meshBasicMaterial color={glow} transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>
      {m.connected && <pointLight position={[0, 0.5, 0]} color={glow} intensity={hot ? 4 : 1.6} distance={9} />}
      <Html position={[0, 3.4, 0]} center distanceFactor={22} zIndexRange={[10, 0]}>
        <div style={{ background: 'rgba(8,11,18,.88)', border: `1px solid ${edge}66`, borderRadius: 8, padding: '8px 10px',
          fontFamily: 'ui-monospace,monospace', fontSize: 11, color: '#e2e8f0', minWidth: 170, pointerEvents: 'none', boxShadow: `0 0 18px ${edge}33` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontWeight: 800 }}>
            <span>{m.label}</span>
            <span style={{ color: edge }}>● {m.state.toUpperCase()}</span>
          </div>
          <div style={{ color: '#94a3b8', marginTop: 4, lineHeight: 1.5 }}>
            {m.region === 'eu' ? 'EUROPE' : 'INDIA'} · data stays in region<br />
            CPU {m.cpu.toFixed(0)}% · buffer {m.buffer}<br />
            last seen {m.connected ? `${ago}s ago` : 'offline'}
          </div>
        </div>
      </Html>
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

function HeadOffice() {
  return (
    <group position={[HQ_X, 0, 0]}>
      {[0, 1, 2, 3].map((i) => (
        <group key={i} position={[0, -0.4 + i * 1.5, 0]}>
          <mesh><boxGeometry args={[3.2, 1.3, 2.4]} /><meshStandardMaterial color="#0f131c" metalness={0.8} roughness={0.35} /></mesh>
          <mesh position={[-1.61, 0, 0]}><boxGeometry args={[0.04, 0.12, 2]} /><meshBasicMaterial color="#38bdf8" /></mesh>
          <mesh position={[-1.61, -0.35, 0.8]}><boxGeometry args={[0.04, 0.1, 0.1]} /><meshBasicMaterial color="#34d399" /></mesh>
        </group>
      ))}
      <pointLight position={[-2, 3, 0]} color="#38bdf8" intensity={2} distance={10} />
      <Html position={[0, 6.4, 0]} center distanceFactor={22} zIndexRange={[10, 0]}>
        <div style={{ fontFamily: 'ui-monospace,monospace', fontSize: 11, fontWeight: 800, color: '#7dd3fc', textAlign: 'center', pointerEvents: 'none', whiteSpace: 'nowrap' }}>
          HEAD OFFICE<br /><span style={{ color: '#94a3b8', fontWeight: 400 }}>AIOps · ledger · AI</span>
        </div>
      </Html>
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

export function LaptopViewer({ machines }: { machines: Machine[] }) {
  const zs = useMemo(() => Object.fromEntries(machines.map((m, i) => [m.id, (i - (machines.length - 1) / 2) * 8])), [machines]);
  return (
    <Canvas camera={{ position: [14, 9, 20], fov: 48 }} style={{ background: '#05070c' }}>
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
      <HeadOffice />
      <Suspense fallback={null}>
        {machines.map((m) => <Laptop key={m.id} m={m} z={zs[m.id]} />)}
      </Suspense>
      <Packets zs={zs} />
    </Canvas>
  );
}
