def _calculate_resistance(self, material, area_m2, length_m, temp_celsius):
        """Calculate resistance with temperature correction."""
        mat_props = self.materials[material.lower()]
        rho_20 = mat_props['resistivity']
        alpha = mat_props['temp_coeff']
        
        # Temperature correction formula: R_T = R_20 * (1 + alpha * (T - 20))
        rho_temp = rho_20 * (1 + alpha * (temp_celsius - 20))
        
        # Resistance formula: R = ρ * L / A
        resistance_total = rho_temp * length_m / area_m2
        
        return {
            'per_unit_ohm_per_m': rho_temp / area_m2,
            'total_ohm': resistance_total,
        }