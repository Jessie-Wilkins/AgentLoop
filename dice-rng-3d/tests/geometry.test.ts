import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { createDiceModel, topFaceValue } from "../src/diceGeometry";

describe("dice geometry", () => {
  it("generates one flat face for every configured side count", () => {
    for (let sides = 4; sides <= 30; sides += 1) {
      const model = createDiceModel(sides);
      expect(model.sides).toBe(sides);
      expect(model.faces).toHaveLength(sides);
      expect(model.faceNormals).toHaveLength(sides);
      expect(model.shape.faces).toHaveLength(sides);
    }
  });

  it("keeps common role-playing dice as matching convex solids", () => {
    for (const sides of [4, 6, 8, 10, 12, 20]) {
      const model = createDiceModel(sides);
      expect(model.geometry.getAttribute("position").count).toBeGreaterThanOrEqual(sides * 3);
      for (const normal of model.faceNormals) {
        expect(normal.length()).toBeCloseTo(1, 6);
      }
    }
  });

  it("reads the upward-facing face as the result", () => {
    const model = createDiceModel(6);
    const quaternion = new THREE.Quaternion();
    const value = topFaceValue(model, quaternion);
    expect(value).toBeGreaterThanOrEqual(1);
    expect(value).toBeLessThanOrEqual(6);
  });
});
