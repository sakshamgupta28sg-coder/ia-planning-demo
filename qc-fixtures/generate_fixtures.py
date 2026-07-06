#!/usr/bin/env python3
"""Generate runnable QC seed fixtures for the IA Planning tool.

Each fixture is a folder an agent points IA_SEEDS_DIR at. The valid base passes
seed_loader; each F-MALFORMED/* variant breaks EXACTLY one validation rule.

Usage:  python3 qc-fixtures/generate_fixtures.py
Output: qc-fixtures/F-*  (see README.md for folder -> test-case mapping)
"""
import csv, os, random, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
CHANNELS = ("Ecom", "Indirect", "Store")
CAT_COLS = ["hierarchy_code","l1_name","l2_name","sku_code","color","size","air","auc",
            "peak_week","peak_units","target_wos","lead_time_weeks","case_pack","safety_weeks",
            "activation_week","deactivation_week","status_seed","tagged_to"]

def write_csv(folder, name, header, rows):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

def base_catalog():
    """5 Old + 1 New (tagged to an Old), valid."""
    return [
        # hc, l1, l2, sku, color, size, air, auc, peak, units, twos, lt, cp, safety, act, deact, status, tag
        [70001,"Tops","Crew Tee","QC-TEE-01","White","M",29.0,9.0,30,400,5,8,12,1,202401,202852,"Old",""],
        [70002,"Bottoms","Straight Trouser","QC-BTM-02","Navy","32",69.0,24.0,34,260,6,8,8,2,202401,202852,"Old",""],
        [70003,"Outerwear","Field Jacket","QC-OUT-03","Olive","L",119.0,46.0,40,180,8,8,6,2,202401,202852,"Old",""],
        [70004,"Footwear","Trail Sneaker","QC-FTW-04","Black","M",99.0,38.0,28,220,7,8,8,3,202401,202852,"Old",""],
        [70005,"Knitwear","Cable Sweater","QC-KNT-05","Stone","M",89.0,35.0,44,160,8,8,6,2,202401,202852,"Old",""],
        [70006,"Tops","Linen Shirt","QC-LIN-06","Sky","M",59.0,21.0,32,200,5,8,8,2,202614,202852,"New",70001],
    ]

def base_supply(cat):
    return [[r[0], 4, 33, 1.0] for r in cat]

def base_budgets(cat):
    rows=[]
    for r in cat:
        season = r[9]*18*r[6]
        for ch,frac in (("Ecom",0.5),("Indirect",0.3),("Store",0.2)):
            rows.append([r[0], ch, int(season*frac/1000)*1000])
    return rows

def base_history(cat):
    """Minimal actuals for 2024+2025 so the optional-history path is exercised."""
    random.seed(11); rows=[]
    for r in cat:
        if r[16]=="New": continue
        for yr in (2024,2025):
            for wn in range(1,53):
                u=max(0,int(r[9]*0.04*random.uniform(0.7,1.3)))
                for ch,frac in (("Ecom",0.5),("Indirect",0.3),("Store",0.2)):
                    rows.append([r[0],ch,yr,wn,int(u*frac),round(random.uniform(0,0.2),2)])
    return rows

def base_forecast(cat):
    """Sparse planning-week forecast for 2026 so the optional-forecast path is exercised."""
    rows=[]
    for r in cat:
        for ch in CHANNELS:
            for wn in range(26,53):
                rows.append([r[0],ch,2026,wn,"",0])   # blank units -> keep engine forecast
    return rows

def write_valid(folder, cat, with_hist=True, with_fc=True):
    write_csv(folder,"catalog.csv",CAT_COLS,cat)
    write_csv(folder,"supply.csv",["hierarchy_code","open_wos","commit_through","commit_mult"],base_supply(cat))
    write_csv(folder,"budgets.csv",["hierarchy_code","channel","budget"],base_budgets(cat))
    if with_hist:
        write_csv(folder,"sales_history.csv",["hierarchy_code","channel","year","week_num","units","discount_perc"],base_history(cat))
    if with_fc:
        write_csv(folder,"forecast.csv",["hierarchy_code","channel","year","week_num","expected_sales_units","oo_placed"],base_forecast(cat))

def fresh(name):
    p=os.path.join(ROOT,name)
    if os.path.isdir(p): shutil.rmtree(p)
    os.makedirs(p); return p

# ── Valid sets ────────────────────────────────────────────────────────────────
cat = base_catalog()
write_valid(fresh("F-CSV6"), cat)
write_valid(fresh("F-NOHIST"), cat, with_hist=False, with_fc=False)

# F-CSV60: 60 SKUs (6 base + 54 generated), calibrated for clean plans + unique names.
def csv60():
    random.seed(607)
    NOUN={"Tops":"Tee","Bottoms":"Trouser","Outerwear":"Jacket","Footwear":"Sneaker",
          "Knitwear":"Sweater","Activewear":"Legging","Dresses":"Dress","Accessories":"Belt"}
    PRICE={"Tops":(19,49,.33),"Bottoms":(49,89,.36),"Outerwear":(89,199,.40),"Footwear":(59,139,.38),
           "Knitwear":(59,119,.39),"Activewear":(39,89,.35),"Dresses":(49,129,.37),"Accessories":(15,59,.34)}
    ADJ=["Classic","Relaxed","Slim","Premium","Everyday","Heritage","Lightweight","Quilted",
         "Tailored","Vintage","Modern","Essential","Coastal","Urban","Oversized"]
    COLORS=["White","Black","Navy","Khaki","Charcoal","Sky","Olive","Stone","Rust","Sand"]
    SIZES=["XS","S","M","L","XL","32","34"]
    cats=list(NOUN); out=[r[:] for r in base_catalog()]
    used={r[2] for r in out}; old_by_cat={}; percat={}
    for r in out:
        if r[16]=="Old": old_by_cat.setdefault(r[1],[]).append(r[0])
    for i in range(54):
        hc=70007+i; c=cats[i%len(cats)]; alo,ahi,aucf=PRICE[c]
        air=round(random.uniform(alo,ahi)); auc=round(air*aucf,1)
        noun=NOUN[c]; j=percat.get(c,0)
        while True:
            nm=f"{ADJ[j%len(ADJ)]} {noun}"; j+=1
            if nm not in used: used.add(nm); break
        percat[c]=j
        new = i>=46
        if new: status="New"; tag=random.choice(old_by_cat.get(c) or [70001]); act=202614
        else: status="Old"; tag=""; act=202401; old_by_cat.setdefault(c,[]).append(hc)
        out.append([hc,c,nm,f"QC-{noun[:3].upper()}-{hc-70000:02d}",random.choice(COLORS),random.choice(SIZES),
            float(air),auc,random.randint(27,38),random.choice([160,200,260,320,400]),
            random.choice([5,6,7,8]),random.choice([4,6,8]),random.choice([4,6,8]),random.choice([1,2,3]),
            act,202852,status,tag])
    return out
write_valid(fresh("F-CSV60"), csv60())

# F-DEMO: intentionally empty (no catalog -> demo literals / byte-identical)
demo=fresh("F-DEMO"); open(os.path.join(demo,"README.txt"),"w").write("Empty on purpose: no catalog.csv -> engine uses built-in demo literals (INV-7).\n")

# F-LONGLT: long lead times (12-16) -> exercises locked-tail behavior
longlt=[row[:] for row in cat]
for i,lt in zip(range(5),(12,14,16,12,14)): longlt[i][11]=lt
write_valid(fresh("F-LONGLT"), longlt)

# F-EARLYPEAK: peaks BEFORE the planning boundary -> over-supply probe (REG/Fix-1 class)
early=[row[:] for row in cat]
for r in early: r[8]=16   # peak_week 16 (declines into the planning window)
write_valid(fresh("F-EARLYPEAK"), early)

# F-DUPNAME: two SKUs share l2_name (data-quality / borrow-confusion probe)
dup=[row[:] for row in cat]; dup[1][2]="Crew Tee"   # 70002 renamed to collide with 70001
write_valid(fresh("F-DUPNAME"), dup)

# F-FORECAST-LTMISMATCH: REG-02 guard for the LT-override -> accept path. Load a clean set,
# cut the catalog LT (8->4) via sku-settings, accept recomm. The OLD engine over-ordered on
# an LT cut (WOS 40-121); the fixed cumulative-top-up must still produce a sane plan.
# NOTE: deliberately NO pre-planted oo_placed. A flat oo_placed bakes over-supply into the
# seed that accept cannot undo (accept only ADDS) -> that tests the seed, not the engine.
ltm=fresh("F-FORECAST-LTMISMATCH"); write_valid(ltm, cat)   # base_forecast leaves oo_placed=0
open(os.path.join(ltm,"README.txt"),"w").write(
    "REG-02 (LT-override regression guard):\n"
    "  1. Load this set  (IA_DB_PATH=/tmp/qc.db IA_SEEDS_DIR=qc-fixtures/F-FORECAST-LTMISMATCH)\n"
    "  2. update_sku_setting(70001, 'lead_time_weeks', 4)   # or PUT /wp/sku-settings/70001 {lead_time_weeks:4}\n"
    "  3. accept_recomm_receipts([70001], ['Ecom','Indirect','Store'], year=2026)\n"
    "Assert: 0 stockout AND max WOS < 40 (old code blew up to WOS 40-121).\n"
    "Validated 2026-07: applied=17, maxWOS=17, stockout=0.\n")

# F-FORECAST-CONSUME: ENG-12 guard for the forecast-consumption path. base_forecast leaves
# expected_sales_units blank + oo_placed=0 (inert, byte-identical) — that never exercises the
# consumption branch (dummy_data _forecast_override -> units override + seed_oop). This set
# plants NON-EMPTY forecast for 70001 across channels on unactualised 2026 weeks so the engine
# must (a) use expected_sales_units as written_sales and (b) surface oo_placed as
# on_order_placed_total_unit. Only forecast.csv differs from F-CSV6.
fcc=fresh("F-FORECAST-CONSUME"); write_valid(fcc, cat)
fcc_rows=[]
for r in cat:
    for ch in CHANNELS:
        for wn in range(30,41):                       # planning weeks, unactualised
            fcc_rows.append([r[0],ch,2026,wn,60,40])  # units override 60, oo_placed 40
write_csv(fcc,"forecast.csv",["hierarchy_code","channel","year","week_num","expected_sales_units","oo_placed"],fcc_rows)
open(os.path.join(fcc,"README.txt"),"w").write(
    "ENG-12 (forecast-consumption guard):\n"
    "  Load: IA_DB_PATH=/tmp/qc.db IA_SEEDS_DIR=qc-fixtures/F-FORECAST-CONSUME\n"
    "  forecast.csv sets expected_sales_units=60 + oo_placed=40 for 2026 wk30-40, all channels.\n"
    "Assert on those cells: written_sales == 60 AND on_order_placed_total_unit == 40\n"
    "  (a blank/0 forecast, as in F-CSV6, must instead keep the engine's own forecast).\n")

# ── F-MALFORMED/* : each breaks exactly ONE rule ──────────────────────────────
mroot=fresh("F-MALFORMED")
def malformed(sub, mutate):
    c=[row[:] for row in cat]; folder=os.path.join(mroot,sub); os.makedirs(folder)
    header=CAT_COLS[:]; supply=base_supply(c); budgets=base_budgets(c)
    hist=base_history(c); fc=base_forecast(c)
    header,c,supply,budgets,hist,fc = mutate(header,c,supply,budgets,hist,fc)
    write_csv(folder,"catalog.csv",header,c)
    write_csv(folder,"supply.csv",["hierarchy_code","open_wos","commit_through","commit_mult"],supply)
    write_csv(folder,"budgets.csv",["hierarchy_code","channel","budget"],budgets)
    if hist is not None: write_csv(folder,"sales_history.csv",["hierarchy_code","channel","year","week_num","units","discount_perc"],hist)
    if fc is not None: write_csv(folder,"forecast.csv",["hierarchy_code","channel","year","week_num","expected_sales_units","oo_placed"],fc)

malformed("missing-column", lambda h,c,s,b,hi,f: ([x for x in h if x!="air"],[r[:6]+r[7:] for r in c],s,b,hi,f))
malformed("dup-hc",         lambda h,c,s,b,hi,f: (h, c+[c[0][:]], s, b, hi, f))                      # 70001 twice
def _badstatus(h,c,s,b,hi,f): c[0][16]="Legacy"; return h,c,s,b,hi,f
malformed("bad-status", _badstatus)
def _badtag(h,c,s,b,hi,f): c[5][17]=99999; return h,c,s,b,hi,f                                       # New -> unknown hc
malformed("bad-tag", _badtag)
def _noold(h,c,s,b,hi,f):
    for r in c: r[16]="New"; r[17]=70001                                                             # all New (no Old)
    return h,c,s,b,None,None
malformed("no-old", _noold)
malformed("missing-supply", lambda h,c,s,b,hi,f: (h,c,s[:-1],b,hi,f))                                 # drop a supply row
def _badchannel(h,c,s,b,hi,f): b[0][1]="Online"; return h,c,s,b,hi,f
malformed("bad-channel", _badchannel)
def _badhistory(h,c,s,b,hi,f): hi[0][3]=99; return h,c,s,b,hi,f                                       # week_num 99
malformed("bad-history", _badhistory)
def _badforecast(h,c,s,b,hi,f):
    f2=[r[:] for r in f]; f2[0][5]=-5; return h,c,s,b,hi,f2                                           # oo_placed -5
malformed("bad-forecast", _badforecast)

print("fixtures written under", ROOT)
for d in sorted(os.listdir(ROOT)):
    p=os.path.join(ROOT,d)
    if os.path.isdir(p): print("  ", d, "/", *( "("+", ".join(sorted(os.listdir(p)))+")" for _ in [0]))
