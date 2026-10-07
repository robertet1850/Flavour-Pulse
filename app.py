import streamlit as st
import sqlite3, hashlib, json, re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import requests, feedparser, pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader

DB="flavour_pulse_v4.db"
OLLAMA_URL="http://localhost:11434/api/generate"
DEFAULT_MODEL="qwen3:8b"

CATEGORIES={
"Drinks":["Bottled Water","Carbonated Soft Drinks","Coffee","Tea & Other Hot Drinks","Dairy & Dairy Substitute Drinks","Juices & Smoothies","Sports & Energy Drinks","Alcoholic Drinks","Sparkling / Adult Non-Alcoholic"],
"Food":["Baby Food & Formula","Biscuits, Cookies & Crackers","Bread, Bakery & Cakes","Breakfast Foods","Chocolate Confectionery","Cooking","Dairy","Desserts & Ice Cream","Fruit & Vegetables","Ingredients & Additives","Meals & Meal Components","Meat & Fish","Snacks","Spreads & Dips","Sugar & Gum Confectionery","Vegan & Plant-Based"],
"Foodservice":["Fast Food","Cafes & Coffee Shops","Bubble Tea & Tea Shops","Dessert & Bakery Foodservice","Restaurants"]}
MARKETS=["Global","Asia Pacific","Southeast Asia","Indonesia","Singapore","Malaysia","Thailand","Vietnam","Philippines","China","Japan","South Korea","India","Australia","New Zealand","United States","United Kingdom","France","Germany","Brazil","Mexico","Middle East","Other"]
FEEDS=[
("Google News — F&B launches","https://news.google.com/rss/search?q=food+beverage+launches&hl=en-US&gl=US&ceid=US:en"),
("Google News — beverage innovation","https://news.google.com/rss/search?q=beverage+innovation+flavour+launch&hl=en-US&gl=US&ceid=US:en"),
("Google News — Asia F&B","https://news.google.com/rss/search?q=Asia+food+beverage+launches&hl=en-US&gl=US&ceid=US:en"),
("Google News — Southeast Asia F&B","https://news.google.com/rss/search?q=Southeast+Asia+food+beverage+launches&hl=en-US&gl=US&ceid=US:en"),
("Google News — RTD tea","https://news.google.com/rss/search?q=RTD+tea+launch+flavour&hl=en-US&gl=US&ceid=US:en"),
("Google News — plant based","https://news.google.com/rss/search?q=plant-based+drink+launch+flavour&hl=en-US&gl=US&ceid=US:en"),
("Google News — bakery","https://news.google.com/rss/search?q=bakery+launch+flavour+trend&hl=en-US&gl=US&ceid=US:en"),
("Google News — snacks","https://news.google.com/rss/search?q=snack+launch+flavour+trend&hl=en-US&gl=US&ceid=US:en")]

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    c=db()
    c.executescript("""CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,name TEXT,url TEXT UNIQUE,source_type TEXT,enabled INTEGER DEFAULT 1,quality REAL DEFAULT .5,added_at TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,source_id INTEGER,title TEXT,url TEXT,published TEXT,fetched_at TEXT,content TEXT,content_hash TEXT UNIQUE,market TEXT,category TEXT);
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY,run_id INTEGER,signal TEXT,family TEXT,category TEXT,market TEXT,strength REAL,direction TEXT,rationale TEXT);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,question TEXT,created_at TEXT,model TEXT,result_json TEXT);""")
    for n,u in FEEDS:
        c.execute("INSERT OR IGNORE INTO sources(name,url,source_type,enabled,quality,added_at) VALUES(?,?,?,?,?,?)",(n,u,"RSS",1,.65,datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
def clean(x):
    s=BeautifulSoup(x or "","html.parser")
    for z in s(["script","style","noscript","svg"]): z.decompose()
    return re.sub(r"\s+"," ",s.get_text(" ",strip=True))
def adddoc(title,url,content,published="",sid=None,market="",category=""):
    if len((content or "").strip())<80:return False
    h=hashlib.sha256((url+"|"+content[:5000]).encode("utf8","ignore")).hexdigest()
    c=db(); c.execute("INSERT OR IGNORE INTO documents(source_id,title,url,published,fetched_at,content,content_hash,market,category) VALUES(?,?,?,?,?,?,?,?,?)",(sid,title,url,published,datetime.now(timezone.utc).isoformat(),content,h,market,category))
    ok=c.total_changes>0;c.commit();c.close();return ok
def fetch(url):
    r=requests.get(url,timeout=20,headers={"User-Agent":"FlavourPulse/4.0 research reader"});r.raise_for_status();return r.text
def ingest():
    c=db(); rows=c.execute("SELECT * FROM sources WHERE enabled=1").fetchall();c.close()
    n=0;errs=[]
    for s in rows:
        try:
            f=feedparser.parse(s["url"])
            for e in f.entries[:30]:
                link=e.get("link",""); content=clean(e.get("summary",""))
                if link:
                    try: content+=" "+clean(fetch(link))[:12000]
                    except: pass
                n+=adddoc(e.get("title",""),link,content,e.get("published","") or e.get("updated",""),s["id"])
        except Exception as ex: errs.append(f'{s["name"]}: {ex}')
    return n,errs
def docs(days,limit):
    c=db();cut=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    r=c.execute("SELECT d.*,s.name source_name,s.quality FROM documents d LEFT JOIN sources s ON s.id=d.source_id WHERE d.fetched_at>=? ORDER BY d.fetched_at DESC LIMIT ?",(cut,limit)).fetchall();c.close()
    return pd.DataFrame([dict(x) for x in r])
def ask(prompt,model):
    r=requests.post(OLLAMA_URL,json={"model":model,"prompt":prompt,"stream":False,"format":"json","options":{"temperature":.15}},timeout=180);r.raise_for_status()
    try:return json.loads(r.json().get("response","{}"))
    except:return {"executive_summary":r.json().get("response",""),"key_shifts":[],"limitations":["Non-JSON model response"],"evidence":[],"signals":[]}
def prompt(q,df,market,category,mode):
    evidence=[{"title":r["title"],"url":r["url"],"published":r["published"],"source":r["source_name"],"text":str(r["content"])[:7000]} for _,r in df.iterrows()]
    return f"""You are FLAVOUR PULSE, a food and beverage intelligence analyst for Robertet Asia.
Mode: {mode}. Market: {market}. Category: {category}. Question: {q}
Use ONLY supplied evidence for factual/current claims. Never invent brands, launches, dates, statistics, demographics or URLs. Separate OBSERVED evidence from INFERENCE.
Extract product/brand movement, original flavour wording, normalized flavour family, sensory profile, format, claims, consumer, occasion, geography, premium cues, cross-category diffusion and whitespace.
Return JSON with: executive_summary, key_shifts[{{
shift,evidence_level,why_it_matters}}], limitations[], sources[], evidence[{{title,url,brand_or_entity,category,market,flavour_original,flavour_family,profile,format,claims,consumer,occasion,observation}}], signals[{{signal,family,category,market,strength_1_to_5,direction,rationale}}].
SUPPLIED EVIDENCE:
{json.dumps(evidence,ensure_ascii=False)}"""
def save(q,model,res):
    c=db();cur=c.execute("INSERT INTO runs(question,created_at,model,result_json) VALUES(?,?,?,?)",(q,datetime.now(timezone.utc).isoformat(),model,json.dumps(res,ensure_ascii=False)));rid=cur.lastrowid
    for s in res.get("signals",[]):
        c.execute("INSERT INTO signals(run_id,signal,family,category,market,strength,direction,rationale) VALUES(?,?,?,?,?,?,?,?)",(rid,s.get("signal",""),s.get("family",""),s.get("category",""),s.get("market",""),float(s.get("strength_1_to_5",0) or 0),s.get("direction",""),s.get("rationale","")))
    c.commit();c.close();return rid

st.set_page_config(page_title="FLAVOUR PULSE V4",layout="wide");init()
st.title("FLAVOUR PULSE V4")
st.caption("Live evidence ingestion • local AI • flavour intelligence • Robertet Asia research layer")
with st.sidebar:
    model=st.text_input("Ollama model",DEFAULT_MODEL)
    mode=st.selectbox("Research mode",["Open research","Launch scan","Flavour deep dive","Category deep dive","Market deep dive","Consumer & occasion","Competitor watch","Whitespace"])
    market=st.selectbox("Market",MARKETS);category=st.selectbox("Category",["All"]+[x for v in CATEGORIES.values() for x in v])
    st.info("No OpenAI/Gemini API key. Analysis runs locally through Ollama.")
tabs=st.tabs(["Live Research","Sources","Import","Evidence","Flavour Signals","Archive","Robertet Layer"])
with tabs[0]:
    q=st.text_area("Research question",placeholder="e.g. What fruit + tea flavour spaces are emerging in Southeast Asia, and which could become mainstream in RTD tea?")
    days=st.slider("Evidence window (days)",7,730,180);limit=st.slider("Maximum evidence documents",20,300,150)
    a,b=st.columns(2)
    if a.button("Refresh public sources",use_container_width=True):
        with st.spinner("Fetching permitted public feeds and linked pages..."):
            n,e=ingest()
        st.success(f"Added {n} new evidence documents.")
        if e:st.warning("; ".join(e[:5]))
    run=b.button("Analyse evidence",type="primary",use_container_width=True)
    d=docs(days,limit);st.metric("Evidence documents available",len(d))
    if run:
        if not q.strip():st.error("Enter a research question.")
        elif d.empty:st.warning("No evidence found. Refresh sources or import files.")
        else:
            try:
                with st.spinner("Analysing locally..."):
                    res=ask(prompt(q,d,market,category,mode),model);save(q,model,res);st.session_state["res"]=res
            except Exception as ex:st.error(f"Ollama error: {ex}")
    res=st.session_state.get("res")
    if res:
        st.subheader("Executive summary");st.write(res.get("executive_summary",""))
        st.subheader("Key shifts")
        for x in res.get("key_shifts",[]):st.markdown(f"**{x.get('shift','')}** — {x.get('why_it_matters','')} _[{x.get('evidence_level','')}]_")
        st.subheader("Evidence");ev=res.get("evidence",[])
        if ev:st.dataframe(pd.DataFrame(ev),use_container_width=True)
        st.subheader("Signals");sg=res.get("signals",[])
        if sg:st.dataframe(pd.DataFrame(sg),use_container_width=True)
        if res.get("limitations"):
            st.subheader("Limitations")
            for x in res["limitations"]:st.write("•",x)
with tabs[1]:
    st.subheader("Source manager")
    c=db();src=pd.DataFrame([dict(r) for r in c.execute("SELECT * FROM sources ORDER BY quality DESC,name").fetchall()]);c.close();st.dataframe(src,use_container_width=True)
    n=st.text_input("Source name");u=st.text_input("RSS / Atom feed URL")
    if st.button("Add source"):
        try:
            c=db();c.execute("INSERT INTO sources(name,url,source_type,enabled,quality,added_at) VALUES(?,?,?,?,?,?)",(n,u,"RSS",1,.5,datetime.now(timezone.utc).isoformat()));c.commit();c.close();st.success("Added.")
        except Exception as ex:st.error(str(ex))
    st.caption("Use public sources you are permitted to access. Do not bypass paywalls, logins, robots rules or rate limits.")
with tabs[2]:
    st.subheader("Import your own research")
    up=st.file_uploader("CSV, XLSX, PDF or TXT",type=["csv","xlsx","pdf","txt"],accept_multiple_files=True)
    if up and st.button("Import files"):
        count=0
        for f in up:
            try:
                if f.name.endswith(".csv"):content=pd.read_csv(f).to_csv(index=False)
                elif f.name.endswith(".xlsx"):
                    x=pd.ExcelFile(f);content="\n".join("### "+s+"\n"+pd.read_excel(f,sheet_name=s).to_csv(index=False) for s in x.sheet_names)
                elif f.name.endswith(".pdf"):content="\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
                else:content=f.read().decode("utf8","ignore")
                count+=adddoc(f.name,"local://"+f.name,content)
            except Exception as ex:st.error(f"{f.name}: {ex}")
        st.success(f"Imported {count} new files.")
    u=st.text_input("Public URL to import")
    if st.button("Import URL"):
        try:
            if adddoc(urlparse(u).netloc,u,clean(fetch(u))):st.success("Imported.")
            else:st.info("Already present or insufficient text.")
        except Exception as ex:st.error(str(ex))
with tabs[3]:
    st.subheader("Evidence archive");d=docs(730,500);st.dataframe(d[["id","title","url","published","fetched_at","source_name","market","category"]],use_container_width=True)
with tabs[4]:
    st.subheader("Flavour signal graph")
    c=db();sg=pd.DataFrame([dict(r) for r in c.execute("SELECT * FROM signals ORDER BY strength DESC,id DESC").fetchall()]);c.close()
    if sg.empty:st.info("Run an analysis to populate signals.")
    else:
        st.dataframe(sg,use_container_width=True);st.download_button("Download signals CSV",sg.to_csv(index=False),"flavour_signals.csv","text/csv")
with tabs[5]:
    st.subheader("Research runs");c=db();r=pd.DataFrame([dict(x) for x in c.execute("SELECT id,question,created_at,model FROM runs ORDER BY id DESC").fetchall()]);c.close();st.dataframe(r,use_container_width=True)
with tabs[6]:
    st.subheader("Robertet Asia intelligence layer")
    st.markdown("""**Evidence → Structured Launch → Signal → Robertet**

Evidence can come from permitted public feeds, public pages, your own files and research exports.
The AI converts evidence into launch attributes, flavour families, sensory profiles, consumer/occasion
signals and whitespace hypotheses. The local database is the core internal research asset.

**Next production upgrades:** entity resolution, controlled flavour ontology/graph, trend velocity,
scheduled ingestion, source reliability scoring, team workspaces, customer projects and PPTX/PDF reporting.""")
    st.warning("External source material remains subject to its own terms/licensing. This tool does not bypass access controls.")
