"""Damped springs, described as the spec does: stiffness and damping ratio."""

import math
from dataclasses import dataclass

# Stiff springs (stiffness 900 for the gaze) stay stable with small integration steps.
MAX_STEP = 1 / 240


@dataclass
class Spring:
    """x'' = -k (x - target) - 2 ζ √k x' + force. ζ < 1 overshoots; ζ = 1 is critical."""

    stiffness: float
    damping: float
    value: float = 0.0
    velocity: float = 0.0
    target: float = 0.0

    def step(self, dt: float, force: float = 0.0) -> float:
        steps = max(1, math.ceil(dt / MAX_STEP))
        h = dt / steps
        friction = 2 * self.damping * math.sqrt(self.stiffness)
        for _ in range(steps):
            accel = -self.stiffness * (self.value - self.target) - friction * self.velocity + force
            self.velocity += accel * h  # semi-implicit Euler: velocity first
            self.value += self.velocity * h
        return self.value

    def kick(self, velocity: float) -> None:
        self.velocity += velocity

    def settle(self, value: float) -> None:
        self.value = self.target = value
        self.velocity = 0.0
