# Power Line Parameter Calculator

## Overview
The **Power Line Parameter Calculator** is a Python-based tool designed to calculate electrical parameters of overhead transmission lines. It computes **resistance (R)**, **inductance (L)**, and **capacitance (C)** for both single-phase and three-phase lines, considering conductor specifications, line geometry, and temperature effects.  

This tool was developed as part of a laboratory activity following **CDIO principles**, providing a user-friendly interface for students and engineers to automate calculations and validate results.

---

## Features
- Compute **line resistance** with temperature correction.
- Calculate **inductance** using conductor spacing, GMR, and mutual coupling.
- Determine **capacitance** for line-to-neutral and line-to-line configurations.
- Supports **single-phase and three-phase lines**, including asymmetric configurations.
- Accepts input for conductor material, arrangement, line length, voltage level, and operating frequency.
- Includes sample data and validation against standard reference values.
- Optional graphical visualization of results.

---

## Getting Started

### Requirements
- Python 3.9+  
- Libraries: `numpy`, `matplotlib` (for optional plotting)  

Install dependencies with:

```bash
pip install numpy matplotlib
