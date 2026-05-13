Below is a **complete technical + product documentation** for your idea, written so it can be handed to engineers, stakeholders, or used as a foundation for implementation.

---

# 📘 Product & Technical Documentation

## Project: CAD-to-Cutlist Engine for Furniture (DXF/3D → Plywood Optimization)

---

# 1. Overview

## 1.1 Purpose

Build a system that converts **3D furniture models (DXF/CAD)** into:

* Manufacturable plywood parts
* Optimized sheet layouts
* Cutlists
* CNC-ready files

This bridges the gap between **design → manufacturing**.

---

## 1.2 Problem

Furniture production currently involves:

* manual measurement from drawings
* inefficient plywood usage
* high dependency on skilled labor
* lack of cost predictability

DXF/CAD files exist but are **not directly usable for cutting**.

---

## 1.3 Solution

A backend engine that:

```
3D DXF → geometry analysis → panel extraction → 2D flattening → nesting → outputs
```

---

# 2. Scope

## In Scope

* 3D DXF parsing
* panel detection (planar boards)
* thickness detection
* 2D contour extraction
* nesting optimization
* cutlist generation
* plywood estimation

## Out of Scope (v1)

* furniture design
* rendering
* joinery automation
* edge band calculation

---

# 3. Input Specification

## Supported Input

* DXF (3D)

  * 3DFACE
  * POLYFACE MESH
  * MESH

## Assumptions

* model represents furniture assembly
* panels are planar
* thickness is uniform per panel

---

# 4. System Architecture

## 4.1 High-Level Pipeline

```
[DXF Upload]
     ↓
[Geometry Parsing]
     ↓
[Mesh Normalization]
     ↓
[Plane Detection]
     ↓
[Board Extraction]
     ↓
[2D Flattening]
     ↓
[Nesting Engine]
     ↓
[Reports + CNC Output]
```

---

## 4.2 Components

### A. Parser Layer

* reads DXF entities
* converts to mesh representation

### B. Geometry Engine

* detects planes
* clusters faces
* extracts boards

### C. Flattening Engine

* converts 3D panels → 2D contours

### D. Optimization Engine

* nesting algorithm

### E. Output Engine

* cutlist
* reports
* DXF export

---

# 5. Core Algorithms

---

## 5.1 Mesh Normalization

Convert all entities into triangle mesh:

```id="alg-1"
Input: DXF entities
Output: unified triangle mesh
```

Steps:

* triangulate faces
* remove duplicates
* fix normals

---

## 5.2 Plane Detection

Each triangle defines a plane.

Cluster triangles where:

* normals are similar (dot product threshold)
* distance from origin is similar

```id="alg-2"
Group = faces with same plane equation
```

---

## 5.3 Board Detection (Critical)

A board is:

> two parallel planes separated by constant thickness

Algorithm:

```id="alg-3"
For each plane A:
    Find plane B such that:
        normal(A) ≈ -normal(B)
        distance(A,B) ≈ thickness

    Pair A and B → Board
```

---

## 5.4 Boundary Extraction

For each plane cluster:

* collect edges
* remove internal edges
* extract outer boundary

Output:

```id="alg-4"
Closed polygon (board contour)
```

---

## 5.5 Flattening

Project 3D polygon onto 2D plane:

```id="alg-5"
3D vertices → 2D coordinates (local plane basis)
```

---

## 5.6 Deduplication

Group identical boards:

Criteria:

* same area ± tolerance
* same bounding box
* optional: shape hashing

---

## 5.7 Nesting Optimization

Input:

* polygons
* sheet size (8×4 ft)
* kerf (3mm)

Algorithm options:

* MaxRects (fast)
* No-Fit Polygon (accurate)

Goal:

```
minimize(sheet_count)
minimize(waste_area)
```

---

# 6. Data Model

## Board Object

```json
{
  "id": "panel_01",
  "length": 720,
  "width": 450,
  "thickness": 18,
  "area": 0.324,
  "contour": [...],
  "quantity": 2
}
```

---

## Sheet Layout

```json
{
  "sheet_id": 1,
  "dimensions": "2440x1220",
  "parts": [...],
  "waste_percent": 9.3
}
```

---

# 7. Output Specification

---

## 7.1 Cutlist

| Part       | L   | W   | T  | Qty |
| ---------- | --- | --- | -- | --- |
| Side Panel | 720 | 450 | 18 | 2   |
| Shelf      | 450 | 300 | 18 | 4   |

---

## 7.2 Material Report

```id="out-1"
Material: 18mm plywood
Total area: 132 sq ft
Sheets required: 5
Waste: 9.2%
```

---

## 7.3 CNC Output

* DXF per sheet
* labeled parts
* kerf-adjusted paths

---

# 8. System Requirements

---

## Performance

* ≤ 60 sec per model
* handle up to 500 panels

## Accuracy

* ±0.5 mm tolerance

## Reliability

* must detect missing panels
* must validate geometry

---

# 9. Edge Cases

---

## Geometry Issues

* non-manifold meshes
* open surfaces
* overlapping faces

Solution:

* geometry cleaning step

---

## Thickness Variations

* small deviations (17.9 vs 18mm)

Solution:

* tolerance clustering

---

## Complex Shapes

* curved edges
* chamfers

Solution:

* approximate or ignore (v1)

---

# 10. User Workflow

```
1. Upload DXF
2. Configure:
   - sheet size
   - material thickness
   - kerf
3. Process
4. Download:
   - cutlist
   - sheet layout
   - DXF files
```

---

# 11. Tech Stack

## Backend

* Python
* ezdxf
* pythonOCC / trimesh
* shapely

## Optimization

* libnest2d / SVGNest

## Output

* DXF writer
* PDF generator

---

# 12. MVP Plan

---

## Week 1

* DXF parsing
* mesh extraction

## Week 2

* plane detection
* board extraction

## Week 3

* flattening
* cutlist generation

## Week 4

* nesting
* output generation

---

# 13. Risks

| Risk                  | Impact   |
| --------------------- | -------- |
| Dirty DXF             | high     |
| Wrong panel detection | critical |
| Slow nesting          | medium   |
| User trust            | critical |

---

# 14. Success Criteria

* reduces plywood waste by >15%
* outputs usable cutlist without manual correction
* processes file in <60 seconds

---

# 15. Strategic Insight

This is not a feature.

It is:

> **Manufacturing intelligence layer for furniture industry**

If executed well:

* becomes SaaS for workshops
* integrates with CNC pipelines
* scales across interior ecosystem

---

# Final Note

The hardest part is NOT nesting.
It is **correctly extracting panels from messy 3D data**.

If that works reliably → product succeeds.
If not → everything collapses.

