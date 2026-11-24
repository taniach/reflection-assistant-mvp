import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from docx import Document
from pypdf import PdfReader
from prompts import BASE, QUESTION, DRAFT, FEEDBACK
from html import escape
from PIL import Image
from base64 import b64encode

ROOT = Path(__file__).parent
ICON_PATH = Path(__file__).parent / "assets" / "mascot.png"
ICON_IMAGE = Image.open(ICON_PATH)

load_dotenv(ROOT / '.env')
st.set_page_config(page_title='Reflection Assistant', page_icon=ICON_IMAGE, layout='centered')

def load_css(file_path):
    css = Path(file_path).read_text(encoding="utf-8")
    st.markdown(
        f"<style>{css}</style>",
        unsafe_allow_html=True
    )

load_css(Path(__file__).parent / "assets" / "styles.css")

DEFAULT = (ROOT / 'rubric.txt').read_text(encoding='utf-8')
THEMES = ['Patient loss or adverse outcome','Ethical or value conflict','Challenging interaction','Caring for patients with long-term needs','Personal well-being and balance','Other — my own experience']
s = st.session_state
for k,v in {'step':1,'messages':[],'rubric':DEFAULT,'draft':'','feedback':'','theme':'','wellbeing':None}.items():
    if k not in s: s[k]=v

def extract(upload):
    if upload.name.lower().endswith('.docx'):
        doc=Document(upload)
        tables=[t for t in doc.tables if any('Required Component' in c.text for r in t.rows for c in r.cells)]
        if tables:
            return '\n'.join(' | '.join(c.text.replace('\n',' ') for c in r.cells) for t in tables for r in t.rows)
        return '\n'.join([p.text for p in doc.paragraphs]+[' | '.join(c.text for c in r.cells) for t in doc.tables for r in t.rows])
    if upload.name.lower().endswith('.pdf'):
        return '\n'.join(p.extract_text() or '' for p in PdfReader(upload).pages)
    return upload.getvalue().decode('utf-8')

def ask_ai(task, messages):
    key=os.getenv('OPENAI_API_KEY')
    if not key: raise ValueError('Missing API key. Add OPENAI_API_KEY to .env and restart.')
    client=OpenAI(api_key=key,timeout=45,max_retries=1)
    result=client.responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),instructions=f'{BASE}\n\nRubric reference:\n{s.rubric}\n\nTask:\n{task}\nTheme: {s.theme}',input=messages,store=False,max_output_tokens=1800)
    if not result.output_text.strip(): raise RuntimeError('No text returned. Try again.')
    return result.output_text

def call(task, messages):
    try:
        with st.spinner('Reflecting…'):
            return ask_ai(task,messages)
    except Exception as e:
        st.error(f'Unable to complete request ({type(e).__name__}). Check your API key, billing, model access and internet connection, then retry.')
        return None

def go(step):
    s.step=step
    st.rerun()

def get_image_base64(path: Path) -> str:
    return b64encode(path.read_bytes()).decode()

with st.sidebar:
    with st.sidebar.expander("⚙️ Educator Settings", expanded=False):
        st.caption('CARE2 Appendix B is already loaded. Replace only with an approved, non-sensitive rubric.')
        upload=st.file_uploader('Upload rubric',type=['docx','pdf','txt'],disabled=s.step!=1)
        if upload and st.button('Load rubric',disabled=s.step!=1):
            try:
                content=extract(upload)
                if not content.strip() or len(content)>40000: st.error('Use a readable rubric under 40,000 characters.')
                else: s.rubric=content; st.success('Rubric loaded')
            except Exception: st.error('Unable to read document.')
        with st.expander('Active rubric'): st.text(s.rubric)
        if st.button('Restore default rubric',disabled=s.step!=1): s.rubric=DEFAULT; st.rerun()
        if st.button('New reflection'):
            for k in ['step','messages','draft','feedback','theme','wellbeing','edited','ack']: s.pop(k,None)
            st.rerun()

icon_base64 = get_image_base64(ICON_PATH)
st.markdown(f"""
    <div class="app-header">
        <img src="data:image/png;base64,{icon_base64}" class="app-header-icon" />
        <div class="app-header-text">
            <div class="app-title">CARE Reflection Assistant</div>
            <div class="app-subtitle">
                A guided, conversational tool that helps medical students turn
                clinical experiences into meaningful, personalised reflections.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.caption('Your experiences. Your insights. Your professional growth.')
st.warning('School prototype. Text and rubric are sent to an external AI API. Do not enter patient identifiers or real sensitive disclosures. Not a clinical or crisis service.')
st.progress(s.step/4,text=f'Step {s.step} of 4')
if s.step==1:
    st.header('Choose a reflective theme')
    theme=st.radio('What would you like to reflect on?',THEMES)
    ack=st.checkbox('I will not enter patient identifiers.',key='ack')
    if st.button('Start reflection',type='primary',disabled=not ack):
        s.theme=theme
        s.messages=[{'role':'assistant','content':'Tell me about a situation related to this theme that stayed with you. What happened, and what was your role?'}]
        go(2)
elif s.step==2:
    st.header('Guided conversation')
    st.markdown(f"""
        <div class="theme-card">
            <div class="theme-label">
                Your selected theme
            </div>
            <div class="theme-value">
                {escape(st.session_state.theme)}
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.caption('One question at a time. You can skip a question, continue or stop.')
    for m in s.messages:
        with st.chat_message(m['role']): st.write(m['content'])
    count=sum(m['role']=='user' for m in s.messages)
    pending=s.messages[-1]['role']=='user'
    if pending:
        if st.button('Retry follow-up'):
            reply=call(QUESTION,s.messages)
            if reply: s.messages.append({'role':'assistant','content':reply}); st.rerun()
    elif count<12:
        text=st.chat_input('Share your thoughts (or type skip)',max_chars=3000)
        if text:
            s.messages.append({'role':'user','content':text})
            reply=call(QUESTION,s.messages)
            if reply: s.messages.append({'role':'assistant','content':reply})
            st.rerun()
    if count>=4: st.caption('You may generate a draft now, or explore further.')
    if count>=12: st.info('Demo conversation limit reached.')
    if st.button('Generate my reflection',type='primary',disabled=count<2):
        draft=call(DRAFT,s.messages)
        if draft: s.draft=draft; s.pop('edited',None); go(3)

    if st.button("← Back to themes", key="back_to_themes"):
        st.session_state.step = 1
        st.rerun()

elif s.step==3:
    st.header('Your reflection')
    st.caption('AI-generated draft. Review for accuracy and ownership. Follow your school’s AI-use rules before submitting anything.')
    edited=st.text_area('Edit your reflection',value=s.draft,height=360,key='edited')
    st.download_button('Download reflection',edited,file_name='reflection.txt')
    if st.button('View personalised insights',type='primary'):
        feedback=call(FEEDBACK,s.messages)
        if feedback: s.feedback=feedback; s.draft=edited; go(4)
    if st.button('Continue reflecting'): s.draft=edited; go(2)
else:
    st.header('Reflection summary')
    with st.container(border=True): st.markdown(s.feedback)
    with st.container(border=True):
        st.subheader('♡ Well-being check')
        st.caption('Optional self-check. Your response is not sent to the AI; nobody is automatically notified.')
        choice=st.radio('How are you feeling?', ['Doing okay','A bit overwhelmed','Not coping well'],index=None,key='wellbeing')
        if choice=='Doing okay': st.success('That is good to hear. Remember to check in with yourself and take breaks as needed.')
        elif choice=='A bit overwhelmed': st.warning('Consider speaking to a friend. Don’t hesitate to reach out to Student Affairs or a faculty mentor if you need further support.')
        elif choice=='Not coping well': st.error('I am sorry to hear that. Please know there are people to help you. Please feel free to reach out to Student Affairs, your faculty mentor or qualified health professional. If you are in immediate danger, contact 995 and a trusted person now.')
    st.download_button('Download reflection',s.draft,file_name='reflection.txt')
    if st.button('Return to reflection'): go(3)
