# ---------------------------------------------------------------------------------------------
#   Unit Converter Module for Power Systems Analysis - Laboratory Activities ⭐
# ---------------------------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Dict

@dataclass
class ConductorUnitConverter:
    """Convert common electrical engineering units for conductors."""
    # Conductor length
    length: Dict[str, float] = field(default_factory=lambda: {
        "m": 1.0,
        "km": 1000.0,
        "cm": 0.01,
        "mm": 0.001,
        "ft": 0.3048,
        "in": 0.0254,
    })

    # For Conductor cross-sectional area
    area: Dict[str, float] = field(default_factory=lambda: {
        "mm2": 1e-6,   # square millimeter
        "cm2": 1e-4,   # square centimeter
        "m2": 1.0,     # square meter
        "kcmil": 5.067e-7,  # thousand circular mils (≈0.5067 mm²)
    })

    #--------------------------------------------------------------------------------------------
    # Bunch of helpful conversions in the future i guess,,,,
    #--------------------------------------------------------------------------------------------


    # ForMass per unit length (conductor weight)
    mass_per_length: Dict[str, float] = field(default_factory=lambda: {
        "kg/m": 1.0,
        "lb/ft": 1.488163943,
    })

    # For Tension / Force
    force: Dict[str, float] = field(default_factory=lambda: {
        "N": 1.0,
        "kN": 1000.0,
        "lbf": 4.4482216152605,
    })

    # FUNCTION FOR THIS CODE
    def convert(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert a value from one unit to another within the same category."""
        categories = [self.length, self.area, self.mass_per_length, self.force]

        for category in categories:
            if from_unit in category and to_unit in category:
                base_value = value * category[from_unit]   # normalize to SI
                return base_value / category[to_unit]      # convert to target
        raise ValueError(f"Incompatible or unknown units: {from_unit} -> {to_unit}")