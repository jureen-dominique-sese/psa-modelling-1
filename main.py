import webview

# Calculation function
def calculate_line(V, R, X):
    Z = complex(R, X)
    I = V / Z
    return abs(I)

# HTML content
html_content = """
<html>
<body>
<h2>Line Parameter Calculator</h2>
Voltage (kV): <input id="V" type="number" value="230"><br>
Resistance (Ω): <input id="R" type="number" value="0.1"><br>
Reactance (Ω): <input id="X" type="number" value="0.2"><br>
<button onclick="pywebview.api.calculate(parseFloat(document.getElementById('V').value), parseFloat(document.getElementById('R').value), parseFloat(document.getElementById('X').value)).then(result => document.getElementById('result').innerText='Line Current (A): '+result.toFixed(2))">Calculate</button>
<p id="result"></p>
</body>
</html>
"""

# API class to expose Python to JS
class API:
    def calculate(self, V, R, X):
        return calculate_line(V, R, X)

# Start WebView window
api = API()
window = webview.create_window("Line Calculator", html=html_content, js_api=api, width=400, height=300)
webview.start()
