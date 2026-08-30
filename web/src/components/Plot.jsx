import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-basic-dist-min'

// The dashboard only uses bar and scatter traces. The basic Plotly bundle keeps
// those chart types without shipping the much larger scientific/3D modules.
const Plot = createPlotlyComponent(Plotly)

export default Plot
