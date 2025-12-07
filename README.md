<p align="left">
  <img src="maptology.png" alt="Maptology logo" width="220">
</p>

# Maptology

<p align="left">
  <strong>Map your dataset to standardized ontology terms</strong><br>
  <a href="https://maptology.streamlit.app/">Link</a>
</p>

---

<h2>What is Maptology?</h2>

**Maptology** is a Streamlit app that maps your dataset's columns/values to standardized **ontology terms**, making your data consistent, interoperable, and easier to analyze and share.

<h3>Why use it?</h3>

- **FAIR & interoperable:** Normalize free-text into ontology IDs/labels  
- **Fast:** Point-and-click mapping, no code required
- **Reusable:** Export mappings for future datasets

<h3>How it works</h3>

<h4>1. Upload your data</h4>
Upload a CSV file (e.g., *Obesity_prediction.csv*)

<h4>2. Map columns to schema fields</h4>
Connect your dataset columns to standardized schema properties

<h4>3. Map values to ontology terms</h4>
Link your data values to official ontology identifiers and labels

<h4>4. Review & export</h4>
Validate mappings and download your standardized dataset

---

<h2>Use Cases</h2>

- **Research Data** — Standardize clinical and biological datasets
- **Healthcare** — Normalize patient records and medical terminologies  
- **Analytics** — Prepare inconsistent data for analysis
- **Data Integration** — Merge datasets from different sources

---

<h2>Getting Started</h2>

### **Prerequisites**
Before using Maptology, you need a **free BioPortal API key**:

1. Visit https://bioportal.bioontology.org/
2. Create a free account  
3. Go to "Account" → "API Key" to get your key
4. Copy your API key for use in the app

### **Using the Web App**
**Link:** https://maptology.streamlit.app/

1. Visit the app and enter your BioPortal API key
2. Upload your CSV file
3. Follow the guided mapping process to transform your data into a standardized format

### For Local Users
To run Maptology locally:

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `streamlit run main.py`

**Tip:** To skip entering your API key every time:
1. Open `utils.py`
2. Find: `API_KEY = ""`
3. Change to: `API_KEY = "your-api-key-here"`

⚠️ **Warning:** Never commit your API key to public repositories!

---

<h2>Important Note</h2>

> **Hosted Service Only**  
> Maptology is designed as a web service. Local runs are disabled by design to ensure optimal performance and security.

---

<h2>License</h2>

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
