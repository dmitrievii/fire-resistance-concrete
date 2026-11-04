# R0.4 Streamlit MVP — verification evidence

- 6/6 automated core tests passed in the development container.
- `streamlit_app.py` passed Python syntax compilation.
- Both engines computed their sample input datasets successfully.
- The original Word document (SHA-256 `c61f3e7d4771efb3ed618eff3a55d27589a044826e4431230b4dd1e6288f44a3`) generated a reference report with the **same byte-identical SHA-256**.
- The sample 720×500 mm input generated a separate DOCX through `parametric_report.create_report`; the footer-integrity check passed.
- A wrong template is rejected before attempting document generation.
- Input validation rejects impossible reinforcement coordinates.

**Limitations:** The Streamlit Python package is not installed in this execution environment and external installation is network-blocked, so an HTTP/browser smoke test and a deployed Cloud endpoint are **not** claimed. GitHub CI installs it on a connected runner. No live GitHub repository, Streamlit Cloud app or end-user deployment was created.
