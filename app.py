from flask import Flask, render_template, request, send_file
import pandas as pd
import os
import tempfile
import plotly.graph_objs as go
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from xhtml2pdf import pisa
from io import BytesIO
from markupsafe import Markup 

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Load LLM config
os.environ["OPENAI_API_KEY"] = ""  # Replace with your key

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a highly knowledgeable vehicle diagnostic assistant."),
    ("user", "Question: {question}")
])

def summarize_data(df):
    df.columns = df.columns.str.encode('ascii', 'ignore').str.decode('ascii').str.strip()
    summary = {
        'engine_temp_avg': round(df['Engine Coolant Temperature [C]'].mean(), 2),
        'rpm_max': int(df['Engine RPM [RPM]'].max()),
        'rpm_avg': int(df['Engine RPM [RPM]'].mean()),
        'speed_max': int(df['Vehicle Speed Sensor [km/h]'].max()),
        'maf_avg': round(df['Air Flow Rate from Mass Flow Sensor [g/s]'].mean(), 2),
        'throttle_max': round(df['Absolute Throttle Position [%]'].max(), 2),
        'ambient_min': round(df['Ambient Air Temperature [C]'].min(), 2),
        'intake_temp_avg': round(df['Intake Air Temperature [C]'].mean(), 2),
        'pedal_d_range': (df['Accelerator Pedal Position D [%]'].min(), df['Accelerator Pedal Position D [%]'].max()),
        'pedal_e_range': (df['Accelerator Pedal Position E [%]'].min(), df['Accelerator Pedal Position E [%]'].max())
    }
    return summary

def build_question(summary):
    return f"""
Based on the summarized OBD-II vehicle data over time, provide a detailed diagnostic report:
1. Assess overall vehicle health.
2. Identify anomalies or issues.
3. Suggest maintenance tips.

Data Summary:
- Avg Engine Coolant Temp: {summary['engine_temp_avg']} °C
- Max Engine RPM: {summary['rpm_max']} RPM
- Avg Engine RPM: {summary['rpm_avg']} RPM
- Max Speed: {summary['speed_max']} km/h
- Avg Air Flow (MAF): {summary['maf_avg']} g/s
- Max Throttle: {summary['throttle_max']} %
- Min Ambient Temp: {summary['ambient_min']} °C
- Avg Intake Air Temp: {summary['intake_temp_avg']} °C
- Pedal D: {summary['pedal_d_range'][0]}% to {summary['pedal_d_range'][1]}%
- Pedal E: {summary['pedal_e_range'][0]}% to {summary['pedal_e_range'][1]}%
"""

def generate_report(question):
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, max_tokens=1024)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"question": question})

def create_graph(df, x_col, y_col, title, explanation):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode='lines', name=y_col))
    fig.update_layout(title=title, xaxis_title='Timestamp', yaxis_title=y_col)
    graph_html = fig.to_html(full_html=False)
    return graph_html, explanation

def create_pdf(report_html):
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(report_html, dest=pdf_buffer)
    if pisa_status.err:
        return None
    pdf_buffer.seek(0)
    return pdf_buffer

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/generate', methods=['POST'])
def generate():
    file = request.files['datafile']
    if not file:
        return "No file uploaded", 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    df = pd.read_csv(file_path)

    summary = summarize_data(df)
    question = build_question(summary)
    report = generate_report(question)

    # Graphs
    graphs = []
    graphs.append(create_graph(df, 'Time', 'Engine Coolant Temperature [C]', 'Engine Coolant Temperature Over Time', 'Monitors engine warming.'))
    graphs.append(create_graph(df, 'Time', 'Engine RPM [RPM]', 'Engine RPM Over Time', 'Shows engine revolutions per minute during operation.'))
    graphs.append(create_graph(df, 'Time', 'Vehicle Speed Sensor [km/h]', 'Vehicle Speed Over Time', 'Helps assess speed behavior.'))
    graphs.append(create_graph(df, 'Time', 'Accelerator Pedal Position D [%]', 'Pedal D Position Over Time', 'Reflects throttle input from driver.'))

    return render_template("result.html", report=report, graphs=graphs)

@app.route('/download', methods=['POST'])
def download():
    report_html = request.form['report_html']
    pdf = create_pdf(report_html)
    if pdf:
        return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name="vehicle_report.pdf")
    return "Failed to generate PDF", 500

if __name__ == "__main__":
    app.run(debug=True)
