import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import serial
import serial.tools.list_ports
import time
import requests
import pandas as pd
from datetime import datetime

# ARDUINO AUTO-DETECT

def find_arduino_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description.lower()
        if "arduino" in desc or "usb" in desc or "ch340" in desc:
            return p.device
    raise Exception("Arduino not found")

arduino_port = find_arduino_port()
ser = serial.Serial(arduino_port, 115200, timeout=0.1)
time.sleep(2)

# DATA BUFFERS

temp_history = []
curr_history = []
time_history = []

latest_temp = 0.0
latest_curr = 0.0
start_time = time.time()

#  ELECTRICITY MAPS

API_TOKEN = "EUHfe7Ap0YgYSnWJ8xiK"
HEADERS = {"auth-token": API_TOKEN}
ZONE = "ES"
BASE_URL = "https://api.electricitymaps.com/v3"

PRICE_CACHE = {"df": None, "hour": None}

def fetch_today_prices():
    today = datetime.now().date()
    params = {
        "zone": ZONE,
        "start": f"{today}T00:00",
        "end": f"{today}T23:00",
        "temporalGranularity": "hourly"
    }

    url = f"{BASE_URL}/price-day-ahead/past-range"
    r = requests.get(url, headers=HEADERS, params=params, timeout=10)
    r.raise_for_status()

    rows = []
    for d in r.json()["data"]:
        rows.append({
            "datetime": pd.to_datetime(d["datetime"]),
            "price": float(d["value"])
        })

    df = pd.DataFrame(rows)
    df["hour"] = df["datetime"].dt.hour
    return df.sort_values("hour")

def get_cached_prices():
    now_hour = datetime.now().hour
    if PRICE_CACHE["hour"] != now_hour:
        PRICE_CACHE["df"] = fetch_today_prices()
        PRICE_CACHE["hour"] = now_hour
    return PRICE_CACHE["df"]

# DASH APP

app = dash.Dash(__name__)

CARD_STYLE = {
    "backgroundColor": "#111827",
    "padding": "20px",
    "borderRadius": "12px",
    "height": "180px",
    "flex": "1",
    "display": "flex",
    "flexDirection": "column",
    "justifyContent": "center",
    "alignItems": "center",
    "textAlign": "center",
    "boxSizing": "border-box"
}

app.layout = html.Div(
    style={
        "backgroundColor": "#0b0f1a",
        "minHeight": "100vh",
        "padding": "20px",
        "fontFamily": "Arial"
    },
    children=[

        html.H1(
            "🔥 Smart Heater – Energy Aware Dashboard",
            style={"textAlign": "center", "color": "#e5e7eb"}
        ),

        #  LIVE VALUES
        html.Div(
            style={
                "display": "flex",
                "gap": "20px",
                "marginTop": "30px"
            },
            children=[

                html.Div(
                    style={**CARD_STYLE, "boxShadow": "0 0 20px rgba(0,229,255,0.25)"},
                    children=[
                        html.P("Temperature", style={"color": "#9ca3af"}),
                        html.H2(id="temp-value", style={"color": "#00e5ff", "fontSize": "42px"})
                    ]
                ),

                html.Div(
                    style={**CARD_STYLE, "boxShadow": "0 0 20px rgba(255,159,28,0.25)"},
                    children=[
                        html.P("Current", style={"color": "#9ca3af"}),
                        html.H2(id="curr-value", style={"color": "#ff9f1c", "fontSize": "42px"})
                    ]
                ),

                html.Div(
                    style={**CARD_STYLE, "boxShadow": "0 0 20px rgba(239,68,68,0.25)"},
                    children=[
                        html.P("Electricity Price (Now)", style={"color": "#9ca3af"}),
                        html.H2(id="price-value", style={"fontSize": "42px"})
                    ]
                ),
            ]
        ),

        # ================= RECOMMENDATION =================
        html.Div(
            id="price-recommendation",
            style={
                "marginTop": "25px",
                "padding": "22px",
                "borderRadius": "14px",
                "fontSize": "22px",
                "textAlign": "center",
                "fontWeight": "bold"
            }
        ),

        # ================= SENSOR GRAPHS =================
        dcc.Graph(id="temp-graph", style={"height": "250px"}),
        dcc.Graph(id="curr-graph", style={"height": "250px"}),

        # ================= PRICE SECTION =================
        html.H3(
            "⚡ Day-Ahead Electricity Prices (Spain)",
            style={"color": "#e5e7eb", "marginTop": "40px"}
        ),

        dcc.Graph(id="price-heatmap", style={"height": "300px"}),
        dcc.Graph(id="price-line", style={"height": "260px"}),

        dcc.Interval(id="interval", interval=1000, n_intervals=0)
    ]
)

# CALLBACK
# ======================================================

@app.callback(
    [
        Output("temp-value", "children"),
        Output("curr-value", "children"),
        Output("price-value", "children"),
        Output("price-value", "style"),
        Output("temp-graph", "figure"),
        Output("curr-graph", "figure"),
        Output("price-heatmap", "figure"),
        Output("price-line", "figure"),
        Output("price-recommendation", "children"),
        Output("price-recommendation", "style"),
    ],
    Input("interval", "n_intervals")
)
def update_dashboard(n):
    try:
        global latest_temp, latest_curr

        # ---------- Arduino (NON-BLOCKING) ----------
        if ser.in_waiting > 0:
            line = ser.readline().decode(errors="ignore").strip()
            if line.startswith("TEMP:") and "CURR:" in line:
                parts = line.split(",")
                latest_temp = float(parts[0].split(":")[1])
                latest_curr = float(parts[1].split(":")[1])

                t = time.time() - start_time
                temp_history.append(latest_temp)
                curr_history.append(latest_curr)
                time_history.append(t)

                if len(time_history) > 200:
                    temp_history.pop(0)
                    curr_history.pop(0)
                    time_history.pop(0)

        # ---------- Sensor graphs ----------
        temp_fig = go.Figure(go.Scatter(x=time_history, y=temp_history, line=dict(color="#00e5ff")))
        curr_fig = go.Figure(go.Scatter(x=time_history, y=curr_history, line=dict(color="#ff9f1c")))

        for fig in (temp_fig, curr_fig):
            fig.update_layout(
                paper_bgcolor="#0b0f1a",
                plot_bgcolor="#0b0f1a",
                font=dict(color="#e5e7eb")
            )

        # ---------- Prices ----------
        df_price = get_cached_prices()
        hour = datetime.now().hour
        current_price = df_price[df_price.hour == hour]["price"].mean()
        avg_price = df_price.price.mean()

        price_color = "#22c55e" if current_price < avg_price else "#ef4444"

        # ---------- Heatmap ----------
        price_heatmap = go.Figure(go.Heatmap(
            x=df_price.hour,
            y=["Price"],
            z=[df_price.price],
            colorscale="RdYlGn_r",
            colorbar=dict(title="€/MWh")
        ))

        price_heatmap.update_layout(
            paper_bgcolor="#0b0f1a",
            plot_bgcolor="#0b0f1a",
            font=dict(color="#e5e7eb"),
            yaxis_visible=False
        )

        # ---------- Line ----------
        price_line = go.Figure(go.Scatter(
            x=df_price.hour,
            y=df_price.price,
            mode="lines+markers",
            line=dict(color="#38bdf8")
        ))

        price_line.update_layout(
            paper_bgcolor="#0b0f1a",
            plot_bgcolor="#0b0f1a",
            font=dict(color="#e5e7eb")
        )

        # ---------- Recommendation ----------
        if current_price < avg_price:
            rec_text = "Electricity is cheap = Good to run the heater"
            rec_style = {"backgroundColor": "#064e3b", "color": "#6ee7b7"}
        else:
            rec_text = "Electricity is expensive = best to avoid usage"
            rec_style = {"backgroundColor": "#7c2d12", "color": "#fdba74"}

        return (
            f"{latest_temp:.2f} °C",
            f"{latest_curr:.3f} A",
            f"{current_price:.1f} €/MWh",
            {"color": price_color},
            temp_fig,
            curr_fig,
            price_heatmap,
            price_line,
            rec_text,
            rec_style
        )

    except Exception as e:
        print("Callback error:", e)
        return dash.no_update

# RUN APP

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
