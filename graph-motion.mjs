export const MIN_ZOOM = .08;
export const MAX_ZOOM = 5;

export function clampZoom(k) { return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, k)); }

export function panTransform(base, start, current) {
  return { x: base.x + current.x - start.x, y: base.y + current.y - start.y, k: base.k };
}

export function pinchTransform(start, first, second) {
  const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
  const distance = Math.max(1, Math.hypot(second.x - first.x, second.y - first.y));
  const k = clampZoom(start.k * distance / start.distance);
  return { x: midpoint.x - start.world[0] * k, y: midpoint.y - start.world[1] * k, k };
}

export function tapEligible(moved, multiplePointers, cancelled) {
  return !moved && !multiplePointers && !cancelled;
}

export const STILL_SWAY = Object.freeze({ x: 0, y: 0, vx: 0, vy: 0 });
const SWAY_CAP = 4.1; // sqrt(1.15² + .25²) * 4.1 < 5 screen pixels.

function capSway(x, y, vx, vy) {
  const length = Math.hypot(x, y);
  const factor = length > SWAY_CAP ? SWAY_CAP / length : 1;
  return { x: x * factor, y: y * factor, vx: vx * factor, vy: vy * factor };
}

export function swayImpulse(sway, dx, dy) {
  if (dx === 0 && dy === 0) return sway;
  return capSway(sway.x - dx * .28, sway.y - dy * .28, sway.vx, sway.vy);
}

export function springStep(sway, elapsedMs) {
  const dt = Math.max(0, elapsedMs) / 1000;
  const omega = 18, damping = .6;
  const attenuation = damping * omega, frequency = omega * Math.sqrt(1 - damping * damping);
  const decay = Math.exp(-attenuation * dt), cosine = Math.cos(frequency * dt), sine = Math.sin(frequency * dt);
  const x = decay * (sway.x * cosine + (sway.vx + attenuation * sway.x) / frequency * sine);
  const y = decay * (sway.y * cosine + (sway.vy + attenuation * sway.y) / frequency * sine);
  const vx = decay * (sway.vx * cosine - (attenuation * sway.vx + omega * omega * sway.x) / frequency * sine);
  const vy = decay * (sway.vy * cosine - (attenuation * sway.vy + omega * omega * sway.y) / frequency * sine);
  return Math.abs(x) < .03 && Math.abs(y) < .03 && Math.abs(vx) < .5 && Math.abs(vy) < .5
    ? STILL_SWAY : capSway(x, y, vx, vy);
}

export function displayX(node, sway, k) {
  return node.x + (sway.x * node.swayGain - sway.y * node.swayTwist) / k;
}
export function displayY(node, sway, k) {
  return node.y + (sway.y * node.swayGain + sway.x * node.swayTwist) / k;
}
