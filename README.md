# Reflection Assistant — school MVP
Python 3.10+ recommended. Open this folder in VS Code. In terminal:

macOS/Linux:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Windows PowerShell:
```
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```
Set OPENAI_API_KEY in .env using https://platform.openai.com/api-keys. Configure API billing separately. Change OPENAI_MODEL if the default is unavailable. Run `python -m streamlit run app.py`. Open http://localhost:8501.

The included rubric.txt is extracted from Appendix B of the supplied CARE2 document. Educator settings supports replacement DOCX, PDF and TXT rubrics (text-based PDFs only). Uploading is optional. Do not distribute the school rubric without permission.

Test using fictional cases only. No database, authentication, automatic escalation or clinical validation. API requests use store=False but this is not a guarantee of zero retention. Session state disappears when the session ends/reloads. The app is a prototype, not an approved institutional system. Obtain faculty approval for AI-generated reflective drafts before real submissions. No real patient/student data.
