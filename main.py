# main.py

import webview
import json
import math

# ===================================================================================
# 1. BACKEND LOGIC: All calculation, conversion, and LaTeX generation code.
# ===================================================================================

class UnitConverter:
    """Handles conversions from various engineering units to SI base units."""
    def to_meters(self, value, unit):
        conversions = {'km': 1000, 'ft': 0.3048, 'mi': 1609.34, 'in': 0.0254, 'cm': 0.01, 'm': 1}
        return value * conversions.get(unit, 1)

    def to_square_meters(self, value, unit):
        conversions = {'mm2': 1e-6, 'kcmil': 5.067e-7}
        return value * conversions.get(unit, 1)

    ## NEW: Add converters for weight and tension
    def to_kg_per_meter(self, value, unit):
        conversions = {'lb/ft': 1.48816, 'kg/m': 1}
        return value * conversions.get(unit, 1)

    def to_newtons(self, value, unit):
        conversions = {'lbf': 4.44822, 'N': 1}
        return value * conversions.get(unit, 1)

class PowerLineCalculatorAPI:
    """
    Encapsulates all core calculations and report generation.
    Exposed to the JavaScript frontend.
    """
    def __init__(self):
        self.materials = {
            'copper': {'resistivity': 1.72e-8, 'temp_coeff': 0.00393},
            'aluminum': {'resistivity': 2.82e-8, 'temp_coeff': 0.00403}
        }
        self.MU_0 = 4 * math.pi * 1e-7
        self.EPSILON_0 = 8.854e-12
        self.GRAVITY = 9.80665 # m/s^2
        self.converter = UnitConverter()

    def _calculate_gmr(self, area_m2, num_conductors, bundle_spacing_m):
        radius = math.sqrt(area_m2 / math.pi)
        gmr_single = 0.7788 * radius
        if num_conductors == 1: return gmr_single, radius
        if num_conductors == 2: return math.sqrt(gmr_single * bundle_spacing_m), math.sqrt(radius * bundle_spacing_m)
        if num_conductors == 3: return (gmr_single * bundle_spacing_m**2)**(1/3), (radius * bundle_spacing_m**2)**(1/3)
        if num_conductors == 4: return (gmr_single * bundle_spacing_m**3 * math.sqrt(2))**(1/4), (radius * bundle_spacing_m**3 * math.sqrt(2))**(1/4)
        raise ValueError(f"Bundling with {num_conductors} conductors not supported.")
    
    ## NEW: Calculate AC resistance including skin effect
    def _calculate_ac_resistance(self, dc_resistance_per_m, frequency, rho_temp, area_m2):
        # Simplified calculation for skin effect using a common approximation
        radius = math.sqrt(area_m2 / math.pi)
        if rho_temp == 0: return dc_resistance_per_m # Avoid division by zero
        x = radius * math.sqrt((2 * math.pi * frequency * self.MU_0) / rho_temp)
        # For x < 2.8, R_ac ≈ R_dc * (1 + x^4 / 192)
        if x < 2.8:
            skin_effect_factor = 1 + (x**4 / 192)
        else: # For larger conductors/frequencies, use a different approximation or a fixed factor
            skin_effect_factor = 1.02 + (x - 2.8) * 0.05 # Simple linear extrapolation for this tool
        return dc_resistance_per_m * skin_effect_factor

    ## MODIFIED: Major update to the main calculation logic
    def calculate_parameters(self, inputs):
        try:
            p = {k: float(v) for k, v in inputs.items() if v and isinstance(v, (str, int, float)) and k not in ['phase_arrangement', 'material', 'length_unit', 'area_unit', 'spacing_unit', 'bundle_spacing_unit', 'weight_unit', 'tension_unit', 'span_unit']}
            
            # --- Unit Conversions ---
            phase = inputs['phase_arrangement']
            area_m2 = self.converter.to_square_meters(p['conductor_area'], inputs['area_unit'])
            total_horizontal_length_m = self.converter.to_meters(p['length'], inputs['length_unit'])
            span_length_m = self.converter.to_meters(p['span_length'], inputs['span_unit'])
            bundle_spacing_m = self.converter.to_meters(p.get('bundle_spacing', 0), inputs.get('bundle_spacing_unit'))
            num_conductors = int(p.get('num_conductors', 1))
            weight_kg_m = self.converter.to_kg_per_meter(p['conductor_weight'], inputs['weight_unit'])
            tension_n = self.converter.to_newtons(p['tension'], inputs['tension_unit'])
            
            # --- Sag and Actual Conductor Length Calculation ---
            weight_per_meter_n = weight_kg_m * self.GRAVITY
            sag_m = (weight_per_meter_n * span_length_m**2) / (8 * tension_n)
            # Catenary curve length approximation: L_actual = L_span + 8*S^2 / (3*L_span)
            actual_length_per_span_m = span_length_m + (8 * sag_m**2) / (3 * span_length_m)
            num_spans = total_horizontal_length_m / span_length_m
            total_actual_length_m = actual_length_per_span_m * num_spans
            physical_props = {'sag_m': sag_m, 'actual_length_m': total_actual_length_m}

            # --- Resistance Calculation (DC and AC) ---
            mat_props = self.materials[inputs['material'].lower()]
            rho_temp = mat_props['resistivity'] * (1 + mat_props['temp_coeff'] * (p['temperature'] - 20))
            r_dc_per_m = rho_temp / area_m2
            r_ac_per_m = self._calculate_ac_resistance(r_dc_per_m, p['frequency'], rho_temp, area_m2)
            resistance = {
                'total_dc_ohm': r_dc_per_m * total_actual_length_m,
                'total_ac_ohm': r_ac_per_m * total_actual_length_m
            }
            
            # --- GMR and GMD Calculation ---
            gmr_m, r_equiv_c = self._calculate_gmr(area_m2, num_conductors, bundle_spacing_m)

            if phase == 'three_phase':
                spacing_ab_m = self.converter.to_meters(p['spacing_ab'], inputs['spacing_unit'])
                spacing_bc_m = self.converter.to_meters(p['spacing_bc'], inputs['spacing_unit'])
                spacing_ca_m = self.converter.to_meters(p['spacing_ca'], inputs['spacing_unit'])
                # GMD for asymmetrical spacing (assuming transposition)
                gmd_m = (spacing_ab_m * spacing_bc_m * spacing_ca_m)**(1/3)
            else: # single_phase
                spacing_m = self.converter.to_meters(p['spacing'], inputs['spacing_unit'])
                gmd_m = spacing_m

            # --- Inductance and Capacitance ---
            if gmd_m <= gmr_m: raise ValueError("GMD must be > GMR. Check spacing and bundling.")
            L_factor = self.MU_0 / (math.pi if phase == 'single_phase' else 2 * math.pi)
            L_total = L_factor * math.log(gmd_m / gmr_m) * total_actual_length_m
            inductance = {'total_h': L_total, 'reactance_total_ohm': 2 * math.pi * p['frequency'] * L_total}

            if gmd_m <= r_equiv_c: raise ValueError("GMD must be > equivalent radius for capacitance.")
            C_factor = (math.pi * self.EPSILON_0) if phase == 'single_phase' else (2 * math.pi * self.EPSILON_0)
            C_total = C_factor / math.log(gmd_m / r_equiv_c) * total_actual_length_m
            capacitance = {'total_f': C_total, 'susceptance_total_s': 2 * math.pi * p['frequency'] * C_total}
            
            # --- Generate Report ---
            latex_solution = self._generate_latex_solution(inputs, p, area_m2, total_actual_length_m, gmd_m, gmr_m, r_equiv_c, resistance, inductance, capacitance, physical_props)

            return {
                'success': True, 'inputs': inputs,
                'resistance': resistance, 'inductance': inductance, 'capacitance': capacitance,
                'physical': physical_props, 'latex_solution': latex_solution
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    ## MODIFIED: Major update to LaTeX report generation
    def _generate_latex_solution(self, i, p, area_m2, length_m, gmd_m, gmr_m, r_equiv_c, r, l, c, phys):
        phase = i['phase_arrangement']
        
        section1 = r"""
            \section{{1. Physical Properties}}
            The actual conductor length is longer than the horizontal distance due to sag.
            $$ \text{{Sag}}, S \approx \frac{{w L_{{span}}^2}}{{8T}} = \frac{{({weight_kg_m:.3f} \times 9.81) \times {span_m:.2f}^2}}{{8 \times {tension_n:.2f}}} = {sag_m:.3f} \text{{ m}} $$
            $$ L_{{actual\_span}} \approx L_{{span}} + \frac{{8S^2}}{{3L_{{span}}}} = {span_m:.2f} + \frac{{8({sag_m:.3f})^2}}{{3({span_m:.2f})}} = {actual_span_m:.3f} \text{{ m}} $$
            $$ L_{{total\_actual}} = L_{{actual\_span}} \times \frac{{L_{{total\_horizontal}}}}{{L_{{span}}}} = {actual_span_m:.3f} \times \frac{{{total_horiz_m:.2f}}}{{{span_m:.2f}}} = {length_m:.2f} \text{{ m}} $$
        """.format(
            weight_kg_m=self.converter.to_kg_per_meter(p['conductor_weight'], i['weight_unit']),
            span_m=self.converter.to_meters(p['span_length'], i['span_unit']),
            tension_n=self.converter.to_newtons(p['tension'], i['tension_unit']),
            sag_m=phys['sag_m'],
            actual_span_m=length_m / (p['length']/p['span_length']),
            total_horiz_m=self.converter.to_meters(p['length'], i['length_unit']),
            length_m=length_m
        )

        section2 = r"""
            \section{{2. Resistance Calculation}}
            First, DC resistance is found. Then, AC resistance is estimated by including skin effect.
            $$ R_{{DC}} = \rho_{{20}} (1 + \alpha (T - 20)) \frac{{L_{{actual}}}}{{A}} $$
            $$ R_{{DC}} = \left( {rho_20:.2e} \times (1 + {alpha:.5f} ({temp:.1f} - 20)) \right) \times \frac{{{length_m:.2f}}}{{{area_m2:.2e}}} = {r_dc_total:.4f} \ \Omega $$
            $$ \mathbf{{R_{{AC}} \approx R_{{DC}} \times k_{{skin}} = {r_ac_total:.4f} \ \Omega}} $$
        """.format(
            rho_20=self.materials[i['material']]['resistivity'], alpha=self.materials[i['material']]['temp_coeff'],
            temp=p['temperature'], length_m=length_m, area_m2=area_m2,
            r_dc_total=r['total_dc_ohm'], r_ac_total=r['total_ac_ohm']
        )
        
        gmd_formula = r'GMD = \sqrt[3]{{D_{{ab}} D_{{bc}} D_{{ca}}}}' if phase == 'three_phase' else 'GMD = D'
        l_formula = r'\frac{{\mu_0}}{{2\pi}}' if phase == 'three_phase' else r'\frac{{\mu_0}}{{\pi}}'
        mu_factor = r'\frac{{4\pi \times 10^{{-7}}}}{{2\pi}}' if phase == 'three_phase' else r'\frac{{4\pi \times 10^{{-7}}}}{{\pi}}'

        section3 = r"""
            \section{{3. Inductance Calculation}}
            Inductance depends on the line's geometry: Geometric Mean Radius (GMR) and Geometric Mean Distance (GMD).
            $$ {gmd_formula} = {gmd_m:.3f} \text{{ m}} $$
            $$ L_{{total}} = {l_formula} \ln{{\left(\frac{{GMD}}{{GMR}}\right)}} \times L_{{actual}} $$
            Calculated GMR = \( {gmr_m:.4e} \text{{ m}} \).
            $$ L_{{total}} = {mu_factor} \times \ln{{\left(\frac{{{gmd_m:.3f}}}{{{gmr_m:.4e}}}\right)}} \times {length_m:.2f} = {l_total_h:.4e} \text{{ H}} $$
            $$ X_L = 2 \pi f L = 2 \pi ({freq:.1f})({l_total_h:.4e}) = \mathbf{{{xl_total:.4f} \ \Omega}} $$
        """.format(
            gmd_formula=gmd_formula, gmd_m=gmd_m, l_formula=l_formula, gmr_m=gmr_m, mu_factor=mu_factor,
            length_m=length_m, l_total_h=l['total_h'], freq=p['frequency'], xl_total=l['reactance_total_ohm']
        )
        
        c_formula_simple = r'2 \pi \epsilon_0' if phase == 'three_phase' else r'\pi \epsilon_0'
        section4 = r"""
            \section{{4. Capacitance Calculation}}
            Capacitance depends on the conductor's equivalent radius and the GMD.
            $$ C_{{total}} = \frac{{{c_formula_simple}}}{{\ln{{\left(\frac{{GMD}}{{r'_{{eq}}}}\right)}}}} \times L_{{actual}} $$
            Calculated equivalent radius \( r'_{{eq}} = {r_equiv_c:.4e} \text{{ m}} \).
            $$ C_{{total}} = \frac{{{c_formula_simple}}}{{\ln{{\left(\frac{{{gmd_m:.3f}}}{{{r_equiv_c:.4e}}}\right)}}}} \times {length_m:.2f} = {c_total_f:.4e} \text{{ F}} $$
            $$ B_C = 2 \pi f C = 2 \pi ({freq:.1f})({c_total_f:.4e}) = \mathbf{{{bc_total_us:.4f} \ \mu S}} $$
        """.format(
            c_formula_simple=c_formula_simple, r_equiv_c=r_equiv_c, gmd_m=gmd_m, length_m=length_m,
            c_total_f=c['total_f'], freq=p['frequency'], bc_total_us=c['susceptance_total_s'] * 1e6
        )
        
        return section1 + section2 + section3 + section4
        
# ===================================================================================
# 2. FRONTEND UI: The complete HTML, CSS, and JavaScript for the interface.
# ===================================================================================

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en" class="dark-theme">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Power Line Calculator</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
    <style>
        :root { --font-family: 'Inter', sans-serif; --radius: 8px; }
        .light-theme { --bg-primary: #f4f4f5; --bg-secondary: #ffffff; --text-primary: #18181b; --text-secondary: #71717a; --border-color: #e4e4e7; --accent-color: #4f46e5; --accent-text-color: #ffffff; --input-bg: #ffffff; --error-text: #b91c1c; --input-error-border: #ef4444; }
        .dark-theme { --bg-primary: #18181b; --bg-secondary: #27272a; --text-primary: #f4f4f5; --text-secondary: #a1a1aa; --border-color: #3f3f46; --accent-color: #6366f1; --accent-text-color: #ffffff; --input-bg: #3f3f46; --error-text: #fca5a5; --input-error-border: #f87171; }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: var(--font-family); background-color: var(--bg-primary); color: var(--text-primary); font-size: 14px; overflow: hidden; }
        
        .screen { display: none; height: 100vh; width: 100vw; }
        .screen.active { display: flex; flex-direction: column; }
        .centered-screen { justify-content: center; align-items: center; text-align: center; padding: 2rem; }
        .selection-card { background-color: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 2rem; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; min-width: 250px; }
        .selection-card:hover { transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
        .selection-card h2 { font-size: 2rem; margin-bottom: 0.5rem; color: var(--accent-color); }
        .container { display: grid; grid-template-columns: 420px 1fr; grid-template-rows: auto 1fr; grid-template-areas: "header header" "sidebar main"; height: 100%; gap: 16px; padding: 16px; }
        .header { grid-area: header; display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background-color: var(--bg-secondary); border-radius: var(--radius); border: 1px solid var(--border-color); }
        main { grid-area: main; background-color: var(--bg-secondary); border-radius: var(--radius); border: 1px solid var(--border-color); padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
        aside { grid-area: sidebar; background-color: var(--bg-secondary); border-radius: var(--radius); border: 1px solid var(--border-color); padding: 24px; overflow-y: auto; }
        .panel-title { font-size: 1.25rem; font-weight: 600; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; }
        .form-grid { display: grid; gap: 18px; }
        .form-group label { display: block; font-weight: 500; margin-bottom: 6px; }
        .input-group { display: flex; }
        input, select { width: 100%; padding: 10px 12px; background-color: var(--input-bg); border: 1px solid var(--border-color); border-radius: var(--radius); color: var(--text-primary); transition: border-color 0.2s; }
        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 16px; border-radius: var(--radius); border: 1px solid var(--accent-color); background-color: transparent; color: var(--accent-color); font-weight: 500; cursor: pointer; transition: all 0.2s; }
        .btn svg { width: 16px; height: 16px; }
        .btn:hover:not(:disabled) { background-color: var(--accent-color); color: var(--accent-text-color); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background-color: var(--accent-color); color: var(--accent-text-color); }
        details { border: 1px solid var(--border-color); border-radius: var(--radius); margin-bottom: 1rem; }
        summary { font-weight: 600; padding: 12px; cursor: pointer; }
        .details-content { padding: 0 12px 12px; }
        .validation-message { color: var(--error-text); font-size: 0.8rem; margin-top: 4px; height: 1em; }
        input.input-error { border-color: var(--input-error-border); }
        #tower-visualization { border: 1px solid var(--border-color); border-radius: var(--radius); padding: 1rem; min-height: 250px; }
        
        .results-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .result-card { background-color: var(--bg-primary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 20px; }
        .card-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
        .card-header h3 { font-size: 1.1rem; font-weight: 600; }
        .card-item { display: flex; justify-content: space-between; padding: 10px 0; font-size: 1rem; border-top: 1px solid var(--border-color); }
        #latex-solution { background-color: var(--bg-primary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 20px; margin-top: 16px; }

        @media print { /* Styles for printing report */ }
    </style>
</head>
<body>
    <svg width="0" height="0" style="position:absolute">
        <symbol id="icon-calc" viewBox="0 0 20 20" fill="currentColor"><path d="M4 2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H4Zm1 9h10V4H5v7Z"/></symbol><symbol id="icon-reset" viewBox="0 0 20 20" fill="currentColor"><path d="M10 2a8 8 0 1 0 5.657 13.657A8 8 0 0 0 10 2Zm-3.121 4.879a.75.75 0 0 1 1.06 0L10 8.94l2.121-2.06a.75.75 0 1 1 1.06 1.06L11.06 10l2.06 2.121a.75.75 0 1 1-1.06 1.06L10 11.06l-2.121 2.06a.75.75 0 1 1-1.06-1.06L8.94 10 6.879 7.94a.75.75 0 0 1 0-1.06Z"/></symbol><symbol id="icon-sun" viewBox="0 0 20 20" fill="currentColor"><path d="M10 3a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0V3.75A.75.75 0 0 1 10 3Zm-3.95 2.55a.75.75 0 0 1 1.06-1.06l1.06 1.06a.75.75 0 0 1-1.06 1.06l-1.06-1.06ZM10 7a3 3 0 1 0 0 6a3 3 0 0 0 0-6Z"/></symbol><symbol id="icon-moon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M7.455 2.164A8.969 8.969 0 0 0 6 2c-4.97 0-9 4.03-9 9s4.03 9 9 9a8.969 8.969 0 0 0 1.455-.164A6.974 6.974 0 0 1 10.5 13a6.5 6.5 0 0 1-3.045-10.836Z" clip-rule="evenodd"/></symbol><symbol id="icon-pdf" viewBox="0 0 20 20" fill="currentColor"><path d="M5.5 1A1.5 1.5 0 0 0 4 2.5v15A1.5 1.5 0 0 0 5.5 19h9a1.5 1.5 0 0 0 1.5-1.5V6.828a1.5 1.5 0 0 0-.44-1.06l-4.292-4.294A1.5 1.5 0 0 0 10.172 1H5.5Z"/></symbol><symbol id="icon-resistance" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12h2l2.5-5 3 10 3-10 2.5 5h2.5"/></symbol><symbol id="icon-inductance" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12h3m14 0h3m-11 0a2.5 2.5 0 0 1-5 0 2.5 2.5 0 0 1-5 0m15 0a2.5 2.5 0 0 1-5 0 2.5 2.5 0 0 1-5 0"/></symbol><symbol id="icon-capacitance" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12h5m10 0h5M7 7v10m5-10v10"/></symbol>
    </svg>

    <div id="home-screen" class="screen active centered-screen"><div><h1>Welcome to the Power Line Calculator</h1><p>Please select the system configuration to begin.</p><div style="display: flex; gap: 2rem; justify-content: center; margin-top: 1rem;"><div class="selection-card" onclick="selectPhase('single_phase')"><h2>1Φ</h2><p>Single-Phase</p></div><div class="selection-card" onclick="selectPhase('three_phase')"><h2>3Φ</h2><p>Three-Phase</p></div></div></div></div>

    <div id="calculator-screen" class="screen">
        <div class="container">
            <header class="header"><h1 id="calculator-title"></h1><button class="btn" id="theme-switcher"><svg id="theme-icon"><use href="#icon-moon"></use></svg></button></header>
            <aside>
                <form id="calculatorForm" class="form-grid" novalidate>
                    <input type="hidden" name="phase_arrangement" id="phase_arrangement_input">
                    <details open>
                        <summary>Conductor Properties</summary>
                        <div class="details-content form-grid">
                            <div class="form-group"><label>Presets</label><select id="conductor_preset"><option value="">Custom</option><option value="drake">ACSR "Drake"</option><option value="lapwing">ACSR "Lapwing"</option></select></div>
                            <div class="form-group"><label>Material</label><select name="material"><option value="aluminum">Aluminum (ACSR)</option><option value="copper">Copper</option></select></div>
                            <div class="form-group"><label>Area</label><div class="input-group"><input type="text" name="conductor_area" value="795" data-validate="number"><select name="area_unit"><option value="kcmil">kcmil</option><option value="mm2">mm²</option></select></div><div class="validation-message"></div></div>
                        </div>
                    </details>
                    <details open>
                        <summary>Line Geometry</summary>
                        <div class="details-content form-grid">
                            <div class="form-group"><label>Total Horizontal Length</label><div class="input-group"><input type="text" name="length" value="100" data-validate="number"><select name="length_unit"><option value="km">km</option><option value="mi">mi</option></select></div><div class="validation-message"></div></div>
                            <div class="form-group" id="single_phase_spacing_field"><label>Distance Between Conductors</label><div class="input-group"><input type="text" name="spacing" value="5" data-validate="number"><select name="spacing_unit"><option value="m">m</option><option value="ft">ft</option></select></div><div class="validation-message"></div></div>
                            <div id="three_phase_spacing_fields" style="display:none;" class="form-grid">
                                <div class="form-group"><label>Spacing D_ab</label><div class="input-group"><input type="text" name="spacing_ab" value="5" data-validate="number"><select name="spacing_unit"><option value="m">m</option><option value="ft">ft</option></select></div><div class="validation-message"></div></div>
                                <div class="form-group"><label>Spacing D_bc</label><div class="input-group"><input type="text" name="spacing_bc" value="5" data-validate="number"><select name="spacing_unit"><option value="m">m</option><option value="ft">ft</option></select></div><div class="validation-message"></div></div>
                                <div class="form-group"><label>Spacing D_ca</label><div class="input-group"><input type="text" name="spacing_ca" value="5" data-validate="number"><select name="spacing_unit"><option value="m">m</option><option value="ft">ft</option></select></div><div class="validation-message"></div></div>
                            </div>
                            <div id="bundling-section" class="form-group"><label>Bundled Conductors</label><select name="num_conductors" id="num_conductors"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></div>
                            <div id="bundle_spacing_field" class="form-group" style="display:none;"><label>Bundle Spacing</label><div class="input-group"><input type="text" name="bundle_spacing" value="45" data-validate="number"><select name="bundle_spacing_unit"><option value="cm">cm</option><option value="in">in</option></select></div><div class="validation-message"></div></div>
                        </div>
                    </details>
                    <details>
                        <summary>Physical & Electrical Properties</summary>
                        <div class="details-content form-grid">
                            <div class="form-group"><label>Avg. Span Length</label><div class="input-group"><input type="text" name="span_length" value="300" data-validate="number"><select name="span_unit"><option value="m">m</option><option value="ft">ft</option></select></div><div class="validation-message"></div></div>
                            <div class="form-group"><label>Conductor Weight</label><div class="input-group"><input type="text" name="conductor_weight" value="1.627" data-validate="number"><select name="weight_unit"><option value="kg/m">kg/m</option><option value="lb/ft">lb/ft</option></select></div><div class="validation-message"></div></div>
                            <div class="form-group"><label>Line Tension</label><div class="input-group"><input type="text" name="tension" value="25000" data-validate="number"><select name="tension_unit"><option value="N">N</option><option value="lbf">lbf</option></select></div><div class="validation-message"></div></div>
                            <div class="form-group"><label>Temperature</label><div class="input-group"><input type="text" name="temperature" value="25" data-validate="number"><select><option>°C</option></select></div><div class="validation-message"></div></div>
                            <div class="form-group"><label>Frequency</label><div class="input-group"><input type="text" name="frequency" value="60" data-validate="number"><select><option>Hz</option></select></div><div class="validation-message"></div></div>
                        </div>
                    </details>
                    <div class="button-group"><button type="submit" class="btn btn-primary" id="calculate-btn"><svg><use href="#icon-calc"></use></svg>Calculate</button><button type="button" class="btn" onclick="resetForm()"><svg><use href="#icon-reset"></use></svg>Reset</button></div>
                </form>
            </aside>
            <main id="main-content">
                <div id="results-container"></div>
                <div id="tower-visualization-container" style="display:none;">
                    <h2 class="panel-title">Tower Configuration</h2>
                    <div id="tower-visualization"></div>
                </div>
            </main>
        </div>
    </div>
    
    <script>
        let resultChart = null; let currentPhase = 'three_phase';

        const conductorPresets = {
            'drake': { area: 795, area_unit: 'kcmil', weight: 1.627, weight_unit: 'kg/m', material: 'aluminum' },
            'lapwing': { area: 477, area_unit: 'kcmil', weight: 0.744, weight_unit: 'kg/m', material: 'aluminum' }
        };

        function navigate(screenId) {
            document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
            document.getElementById(screenId).classList.add('active');
        }

        function selectPhase(phase) {
            currentPhase = phase;
            showCalculator();
        }

        function showCalculator() {
            document.getElementById('phase_arrangement_input').value = currentPhase;
            document.getElementById('calculator-title').textContent = `⚡ ${currentPhase.replace('_', ' ')} Calculator`;
            
            const isThreePhase = currentPhase === 'three_phase';
            document.getElementById('single_phase_spacing_field').style.display = isThreePhase ? 'none' : 'block';
            document.getElementById('three_phase_spacing_fields').style.display = isThreePhase ? 'grid' : 'none';
            document.getElementById('bundling-section').style.display = isThreePhase ? 'block' : 'none';
            
            resetForm(); 
            navigate('calculator-screen');
        }
        
        document.addEventListener('DOMContentLoaded', () => {
            const form = document.getElementById('calculatorForm');
            form.addEventListener('submit', handleFormSubmit);
            document.getElementById('num_conductors').addEventListener('change', updateDynamicFields);
            document.getElementById('theme-switcher').addEventListener('click', toggleTheme);
            document.getElementById('conductor_preset').addEventListener('change', applyPreset);
            
            // Real-time validation
            form.querySelectorAll('input[data-validate="number"]').forEach(input => {
                input.addEventListener('input', () => validateInput(input));
            });

            updateTheme(true);
            updateDynamicFields();
            checkFormValidity();
        });

        function validateInput(input) {
            const value = input.value;
            const messageDiv = input.closest('.form-group').querySelector('.validation-message');
            const isValid = value.trim() !== '' && !isNaN(value) && parseFloat(value) >= 0;

            if (isValid) {
                input.classList.remove('input-error');
                messageDiv.textContent = '';
            } else {
                input.classList.add('input-error');
                messageDiv.textContent = 'Please enter a valid, non-negative number.';
            }
            checkFormValidity();
            if(document.getElementById('tower-visualization-container').style.display !== 'none') updateVisualization();
        }

        function checkFormValidity() {
            const form = document.getElementById('calculatorForm');
            const inputs = form.querySelectorAll('input[data-validate="number"]');
            let isFormValid = true;
            inputs.forEach(input => {
                if (input.closest('.form-group').style.display !== 'none' && input.closest('.details-content').parentElement.open) {
                    if (input.classList.contains('input-error') || input.value.trim() === '') {
                        isFormValid = false;
                    }
                }
            });
            document.getElementById('calculate-btn').disabled = !isFormValid;
        }

        function applyPreset() {
            const form = document.getElementById('calculatorForm');
            const selected = document.getElementById('conductor_preset').value;
            if (!selected) return;
            const preset = conductorPresets[selected];
            form.elements['conductor_area'].value = preset.area;
            form.elements['area_unit'].value = preset.area_unit;
            form.elements['conductor_weight'].value = preset.weight;
            form.elements['weight_unit'].value = preset.weight_unit;
            form.elements['material'].value = preset.material;

            // Re-validate all changed fields
            form.querySelectorAll('input[data-validate="number"]').forEach(input => validateInput(input));
        }

        async function handleFormSubmit(e) {
            e.preventDefault();
            const resultsContainer = document.getElementById('results-container');
            resultsContainer.innerHTML = 'Calculating...';
            const formData = new FormData(document.getElementById('calculatorForm'));
            let inputs = Object.fromEntries(formData.entries());
            if (currentPhase === 'single_phase') {
                inputs.num_conductors = '1';
                inputs.spacing_ab = inputs.spacing_bc = inputs.spacing_ca = inputs.spacing;
            }
            const results = await pywebview.api.calculate_parameters(inputs);
            if (results.success) displayResults(results);
            else resultsContainer.innerHTML = `<div class="message-box">${results.error}</div>`;
        }
        
        function updateDynamicFields() {
            const isBundled = document.getElementById('num_conductors').value > 1;
            document.getElementById('bundle_spacing_field').style.display = isBundled ? 'block' : 'none';
        }

        function resetForm() {
            document.getElementById('calculatorForm').reset();
            updateDynamicFields();
            document.getElementById('phase_arrangement_input').value = currentPhase;
            document.getElementById('results-container').innerHTML = '<p style="text-align:center;color:var(--text-secondary)">📊 Results will appear here.</p>';
            document.getElementById('tower-visualization-container').style.display = 'none';
            document.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
            document.querySelectorAll('.validation-message').forEach(el => el.textContent = '');
            checkFormValidity();
        }
        
        function toggleTheme() {
            document.documentElement.classList.toggle('dark-theme');
            document.documentElement.classList.toggle('light-theme');
            updateTheme();
        }

        function updateTheme(initial=false) {
            const isDark = document.documentElement.classList.contains('dark-theme');
            document.getElementById('theme-icon').querySelector('use').setAttribute('href', isDark ? '#icon-sun' : '#icon-moon');
            if(resultChart) {
                const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary');
                resultChart.options.scales.x.ticks.color = textColor;
                resultChart.options.scales.y.ticks.color = textColor;
                resultChart.options.plugins.title.color = textColor;
                resultChart.update();
            }
             if(!initial) updateVisualization();
        }

        function displayResults(data) {
            const { resistance: r, inductance: l, capacitance: c, physical: p, latex_solution } = data;
            const resultsContainer = document.getElementById('results-container');
            resultsContainer.innerHTML = `
                <div id="results-header" style="display:flex;justify-content:space-between;align-items:center;"><h2 class="panel-title">📊 Calculation Report</h2><button class="btn" onclick="window.print()"><svg><use href="#icon-pdf"></use></svg>Export PDF</button></div>
                <div class="results-grid">
                    <div class="result-card"><div class="card-header"><h3>Physical Line Properties</h3></div><div class="card-item"><span>Max Sag</span><span>${p.sag_m.toFixed(3)} m</span></div><div class="card-item"><span>Total Conductor Length</span><span>${(p.actual_length_m/1000).toFixed(4)} km</span></div></div>
                    <div class="result-card"><div class="card-header"><svg><use href="#icon-resistance"></use></svg><h3>Resistance</h3></div><div class="card-item"><span>AC Resistance (R_ac)</span><span>${r.total_ac_ohm.toFixed(4)} Ω</span></div><div class="card-item"><span>DC Resistance (R_dc)</span><span>${r.total_dc_ohm.toFixed(4)} Ω</span></div></div>
                    <div class="result-card"><div class="card-header"><svg><use href="#icon-inductance"></use></svg><h3>Inductance</h3></div><div class="card-item"><span>Reactance (X_L)</span><span>${l.reactance_total_ohm.toFixed(4)} Ω</span></div></div>
                    <div class="result-card"><div class="card-header"><svg><use href="#icon-capacitance"></use></svg><h3>Capacitance</h3></div><div class="card-item"><span>Susceptance (B_C)</span><span>${(c.susceptance_total_s * 1e6).toFixed(4)} µS</span></div></div>
                </div>
                <div class="chart-container"><canvas id="impedanceChart"></canvas></div>
                <div id="latex-solution"><h3 class="panel-title" style="margin-top:2rem;">Step-by-Step Manual Solution</h3>${latex_solution}</div>
            `;
            renderImpedanceChart(r, l);
            MathJax.typesetPromise();
            document.getElementById('tower-visualization-container').style.display = 'block';
            updateVisualization();
        }

        function renderImpedanceChart(r, l) {
            if (resultChart) resultChart.destroy();
            const ctx = document.getElementById('impedanceChart').getContext('2d');
            const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary');
            resultChart = new Chart(ctx, { type: 'bar', data: { labels: ['AC Resistance (R)', 'Inductive Reactance (XL)'], datasets: [{ data: [r.total_ac_ohm, l.reactance_total_ohm], backgroundColor: ['rgba(239, 68, 68, 0.6)', 'rgba(59, 130, 246, 0.6)'], borderColor: ['#ef4444', '#3b82f6'], borderWidth: 2 }] }, options: { plugins: { legend: { display: false }, title: { display: true, text: 'Line Impedance Comparison', color: textColor, font: { size: 16 } } }, scales: { y: { title: { display: true, text: 'Ohms (Ω)', color: textColor }, ticks: { color: textColor } }, x: { ticks: { color: textColor } } } } });
        }

        function updateVisualization() {
            const viz = document.getElementById('tower-visualization');
            const form = document.getElementById('calculatorForm');
            const numConductors = parseInt(form.elements['num_conductors'].value);
            const bundleSpacing = parseFloat(form.elements['bundle_spacing'].value) / 100; // to meters
            const strokeColor = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary');

            let Dab, Dbc, Dca;
            if (currentPhase === 'three_phase') {
                Dab = parseFloat(form.elements['spacing_ab'].value);
                Dbc = parseFloat(form.elements['spacing_bc'].value);
                Dca = parseFloat(form.elements['spacing_ca'].value);
            } else {
                Dab = parseFloat(form.elements['spacing'].value);
                Dbc = 0; Dca = 0;
            }

            if (isNaN(Dab)) return; // Don't draw if invalid

            // Basic SVG structure
            const W = viz.clientWidth; const H = 250;
            let svg = `<svg width="100%" height="${H}" viewBox="0 0 ${W} ${H}">`;

            // Draw Tower
            svg += `<line x1="${W/2}" y1="${H}" x2="${W/2}" y2="20" stroke="${strokeColor}" stroke-width="3" />`;
            svg += `<line x1="${W*0.2}" y1="50" x2="${W*0.8}" y2="50" stroke="${strokeColor}" stroke-width="2" />`;
            svg += `<line x1="${W*0.3}" y1="100" x2="${W*0.7}" y2="100" stroke="${strokeColor}" stroke-width="2" />`;

            // Calculate conductor positions
            let coords = [];
            if (currentPhase === 'single_phase') {
                coords.push({x: -Dab/2, y: 0, label: 'L'});
                coords.push({x: Dab/2, y: 0, label: 'N'});
            } else { // 3-phase triangular
                const x_c = (Dab**2 + Dbc**2 - Dca**2) / (2 * Dab);
                const y_c = Math.sqrt(Math.max(0, Dbc**2 - x_c**2)); // Ensure non-negative
                coords.push({x: 0, y: 0, label: 'A'});
                coords.push({x: Dab, y: 0, label: 'B'});
                coords.push({x: x_c, y: -y_c, label: 'C'});
            }

            // Scale and center the coordinates
            const all_x = coords.map(c => c.x); const all_y = coords.map(c => c.y);
            const min_x = Math.min(...all_x); const max_x = Math.max(...all_x);
            const min_y = Math.min(...all_y); const max_y = Math.max(...all_y);
            const dataWidth = max_x - min_x; const dataHeight = max_y - min_y;
            const scale = Math.min((W*0.6) / (dataWidth || 1), (H*0.5) / (dataHeight || 1));
            
            const centerX = W/2;
            const centerY = 100;

            // Draw conductors
            coords.forEach(c => {
                const drawX = centerX + (c.x - (min_x + dataWidth/2)) * scale;
                const drawY = centerY + (c.y - (min_y + dataHeight/2)) * scale;
                svg += `<circle cx="${drawX}" cy="${drawY}" r="5" fill="${strokeColor}" />`;
                svg += `<text x="${drawX+10}" y="${drawY+5}" fill="${strokeColor}" font-size="12">${c.label}</text>`;
            });

            svg += `</svg>`;
            viz.innerHTML = svg;
        }

    </script>
</body>
</html>
"""

# ===================================================================================
# 3. APPLICATION RUNNER: Sets up and starts the pywebview application.
# ===================================================================================

class WebApp:
    def __init__(self):
        self.api = PowerLineCalculatorAPI()
        self.window = webview.create_window(
            'Power Line Calculator Suite',
            html=HTML_CONTENT,
            js_api=self.api,
            width=1400,
            height=900,
            min_size=(1200, 800)
        )

    def run(self):
        webview.start(debug=True)

if __name__ == '__main__':
    app = WebApp()
    app.run()