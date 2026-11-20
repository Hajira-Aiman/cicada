import React, { useMemo, useEffect, Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Float, useGLTF, ContactShadows, Environment } from '@react-three/drei';
import * as THREE from 'three';

const MODEL = '/models/laptop.glb';
useGLTF.preload(MODEL);

export interface LaptopModelProps {
  position?: [number, number, number];
  rotation?: [number, number, number];
  risk?: number;        // 0..1, shifts the glow from its base colour to red
  baseColor?: string;   // healthy colour (per tenant)
  connected?: boolean;  // offline = grey, no ring or light
}

export function LaptopModel({ position = [0, 0, 0], rotation = [0, 0, 0], risk = 0.2, baseColor = '#3b82f6', connected = true }: LaptopModelProps) {
  const { scene } = useGLTF(MODEL);
  const clone = useMemo(() => scene.clone(), [scene]);   // own materials per laptop
  const isHighRisk = risk > 0.6;
  const heatColor = useMemo(
    () => new THREE.Color(connected ? baseColor : '#4b5563').lerp(new THREE.Color('#ef4444'), connected ? Math.min(1, Math.max(0, (risk - 0.3) * 1.5)) : 0),
    [baseColor, risk, connected]);

  useEffect(() => {
    clone.traverse((child: any) => {
      if (child.isMesh) {
        child.material = child.material.clone();
        if (child.material.emissive) {
          child.material.emissive.copy(heatColor);
          child.material.emissiveIntensity = isHighRisk ? 0.8 : 0.1;
        }
      }
    });
  }, [clone, heatColor, isHighRisk]);

  return (
    <group position={position} rotation={rotation}>
      <Float speed={2} rotationIntensity={0.02} floatIntensity={0.1} floatingRange={[-0.1, 0.1]}>
        <primitive object={clone} scale={4.0} position={[0, -1.0, 0]} />
        <mesh position={[0, -1.4, 0]}>
          <cylinderGeometry args={[4.2, 4.5, 0.8, 64]} />
          <meshStandardMaterial color="#0a0c10" metalness={0.9} roughness={0.2} />
        </mesh>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.01, 0]}>
          <circleGeometry args={[4.2, 64]} />
          <meshStandardMaterial color="#14171f" metalness={0.7} roughness={0.1} />
        </mesh>
        {connected && (
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.0, 0]}>
            <ringGeometry args={[3.8, 4.2, 64]} />
            <meshBasicMaterial color={heatColor} transparent opacity={isHighRisk ? 1 : 0.8} side={THREE.DoubleSide} />
          </mesh>
        )}
        {connected && <pointLight position={[0, -0.5, 0]} color={heatColor} intensity={isHighRisk ? 4 : 1.5} distance={10} />}
      </Float>
    </group>
  );
}

export interface Machine { id: string; risk: number; connected: boolean; baseColor: string }
export function LaptopViewer({ machines }: { machines: Machine[] }) {
  const gap = 11;
  return (
    <Canvas camera={{ position: [0, 5, 26], fov: 50 }} style={{ background: '#111827' }}>
      <ambientLight intensity={0.4} />
      <directionalLight position={[5, 10, 5]} intensity={2} />
      <directionalLight position={[-5, 10, -5]} intensity={0.5} color="#cbd5e1" />
      <OrbitControls makeDefault minDistance={5} maxDistance={40} />
      <Environment preset="city" />
      <ContactShadows position={[0, -2.5, 0]} opacity={0.5} scale={60} blur={2.5} far={4} />
      <Suspense fallback={null}>
        {machines.map((m, i) => (
          <LaptopModel key={m.id} position={[(i - (machines.length - 1) / 2) * gap, 0, 0]} rotation={[0, 0.3, 0]}
            risk={m.risk} connected={m.connected} baseColor={m.baseColor} />
        ))}
      </Suspense>
    </Canvas>
  );
}
