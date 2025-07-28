import dash
from dash import dcc, html
import plotly.graph_objs as go

app = dash.Dash(__name__)

fig = go.Figure(data=go.Scatter(y=[1, 3, 2]))

app.layout = html.Div([
    dcc.Graph(figure=fig),
    html.Button("Nhấn tôi", id="my-button")
])

if __name__ == "__main__":
    app.run(debug=True)