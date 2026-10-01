from pathlib import Path
import pandas as pd
import numpy as np
import random, math, json

random.seed(42)
np.random.seed(42)
BASE = Path(__file__).resolve().parent
DATA = BASE/'data'
DATA.mkdir(exist_ok=True)

periods = pd.date_range('2024-01-31','2026-09-30',freq='ME')

# ---------- helper ----------
def fmt_period(d): return d.strftime('%Y-%m')

def growth_path(start, end, n, seasonal=0.0):
    x=np.linspace(0,1,n)
    vals=start+(end-start)*x
    for i in range(n):
        vals[i] *= (1 + seasonal*math.sin(2*math.pi*(i%12)/12))
    return vals

def normalize_alloc(raw, target):
    raw=np.maximum(np.asarray(raw,dtype=float),0.01)
    return raw/raw.sum()*target

# ---------- account master ----------
loan_products=[
    ('Consumer - KPR Subsidi','KPR Subsidi',0.22),
    ('Consumer - KPR Non Subsidi','KPR Non Subsidi',0.20),
    ('Consumer - Non KPR','Non KPR',0.12),
    ('Consumer - Multimanfaat','Multimanfaat',0.08),
    ('Commercial - Modal Kerja','Modal Kerja',0.15),
    ('Commercial - Investasi','Investasi',0.13),
    ('Commercial - Konstruksi','Konstruksi',0.10),
]
loan_n=140
loan_rows=[]
for i in range(loan_n):
    # deterministic weighted product
    r=random.random(); cum=0; prod=None
    for name,short,w in loan_products:
        cum+=w
        if r<=cum: prod=name; break
    if prod is None: prod=loan_products[-1][0]
    start_idx=random.randint(0,len(periods)-1)
    duration=random.randint(12,42)
    close_idx=min(len(periods), start_idx+duration)
    # some accounts close before period end; some remain open
    if i%7==0: close_idx=min(len(periods), start_idx+random.randint(6,18))
    facility=random.uniform(350,1600) # Rp bn
    # KPR larger
    if 'KPR' in prod: facility=random.uniform(500,1800)
    if 'Konstruksi' in prod: facility=random.uniform(800,2200)
    rate={'Consumer - KPR Subsidi':5.0,'Consumer - KPR Non Subsidi':8.5,'Consumer - Non KPR':10.5,'Consumer - Multimanfaat':9.5,'Commercial - Modal Kerja':9.0,'Commercial - Investasi':8.7,'Commercial - Konstruksi':10.0}[prod]
    rate += random.uniform(-0.6,0.6)
    quality=random.choices([1,2,3,4,5],[0.82,0.12,0.04,0.015,0.005])[0]
    loan_rows.append(dict(loan_no=f'LN{2024+i:04d}',product_type=prod,facility_amount=round(facility,2),start_idx=start_idx,close_idx=close_idx,rate_pa=round(rate,2),base_quality=quality))

inv_types=[
 ('Penempatan dan Giro - Bank Indonesia',0.20,4.25,1),
 ('Penempatan dan Giro - Bank Lain',0.12,4.75,1),
 ('Surat berharga yang dimiliki - Bank Indonesia',0.25,5.00,1),
 ('Surat berharga yang dimiliki - Pemerintah',0.28,5.50,1),
 ('Surat berharga yang dimiliki - Bank Lain',0.07,6.00,1),
 ('Surat berharga yang dimiliki - Korporasi',0.08,7.00,1),
]
inv_n=42
inv_rows=[]
for i in range(inv_n):
    r=random.random();cum=0; typ=None; wt=0; rate=0; qual=1
    for t,w,rt,q in inv_types:
        cum+=w
        if r<=cum: typ=t;rate=rt;qual=q;break
    start_idx=random.randint(0, len(periods)-12)
    close_idx=min(len(periods), start_idx+random.randint(6,30))
    amount=random.uniform(250,1800)
    if 'Bank Indonesia' in typ or 'Pemerintah' in typ: qual=1
    else: qual=random.choices([1,2,3],[0.9,0.08,0.02])[0]
    inv_rows.append(dict(investment_no=f'INV{2024+i:04d}',investment_type=typ,investment_amount=round(amount,2),start_idx=start_idx,close_idx=close_idx,rate_pa=round(rate+random.uniform(-0.35,0.35),2),quality=qual))

# Deposit and other funding
funding_types=[
 ('Giro Perorangan - Wadiah',0.10,0.25),('Giro Perorangan - Mudharabah',0.07,2.00),
 ('Giro Lembaga - Wadiah',0.15,0.30),('Giro Lembaga - Mudharabah',0.08,2.10),
 ('Tabungan Perorangan - Wadiah',0.15,0.50),('Tabungan Perorangan - Mudharabah',0.12,2.50),
 ('Tabungan Lembaga - Wadiah',0.10,0.65),('Tabungan Lembaga - Mudharabah',0.06,2.60),
 ('Deposito Perorangan - Mudharabah',0.10,4.00),('Deposito Lembaga - Mudharabah',0.07,4.25),
]
fund_n=150
fund_rows=[]
for i in range(fund_n):
    r=random.random();cum=0;typ=None;rate=0
    for t,w,rt in funding_types:
        cum+=w
        if r<=cum:typ=t;rate=rt;break
    start_idx=random.randint(0,len(periods)-1)
    close_idx=min(len(periods),start_idx+random.randint(4,36))
    if i%5!=0 and start_idx<30: close_idx=min(len(periods),start_idx+random.randint(18,50))
    base=random.uniform(60,650)
    fund_rows.append(dict(account_no=f'AC{2024+i:05d}',product_type=typ,base_amount=base,start_idx=start_idx,close_idx=close_idx,rate_pa=round(rate+random.uniform(-0.15,0.15),2)))

other_types=[('Pinjaman yang diterima',0.65,6.5),('Surat Berharga Diterbitkan',0.35,6.0)]
other_n=24
other_rows=[]
for i in range(other_n):
    r=random.random(); typ='Pinjaman yang diterima' if r<.65 else 'Surat Berharga Diterbitkan'
    start_idx=random.randint(0,len(periods)-18)
    close_idx=min(len(periods),start_idx+random.randint(12,36))
    amount=random.uniform(150,700)
    other_rows.append(dict(account_no=f'OF{2024+i:05d}',product_type=typ,base_amount=amount,start_idx=start_idx,close_idx=close_idx,rate_pa=round((6.5 if typ.startswith('Pinjaman') else 6.0)+random.uniform(-.25,.25),2)))

# ---------- target monthly balance paths (Rp bn) ----------
def target_path(year, month):
    # anchors: Jan 2024 ~65T, Dec 2024 ~71T, Dec 2025 ~77T, Sep 2026 ~80T
    anchors={
      pd.Timestamp('2024-01-31'):65000, pd.Timestamp('2024-12-31'):71000,
      pd.Timestamp('2025-01-31'):71200, pd.Timestamp('2025-12-31'):77000,
      pd.Timestamp('2026-01-31'):77400, pd.Timestamp('2026-09-30'):80000}
    # linear interpolation
    keys=sorted(anchors)
    for a,b in zip(keys[:-1],keys[1:]):
        if a<=month<=b:
            frac=(month-a).days/(b-a).days
            return anchors[a]+frac*(anchors[b]-anchors[a])
    return anchors[keys[-1]]

def loan_target(d):
    frac=(target_path(d.year,d)*0) # no-op
    # 75% of total assets in 2026, 70% 2024
    base=43000 + (d.year-2024)*7000
    if d>=pd.Timestamp('2026-01-31'): base=57000 + (d.month-1)*(3000/8)
    if d>pd.Timestamp('2026-09-30'): base=60000
    return min(base,60000)

def inv_target(d):
    return 9000 + (d.year-2024)*(-300) + 300*math.sin(2*math.pi*(d.month-1)/12)

def dpk_target(d):
    if d.year==2024: return 53000 + (d.month-1)*1000
    if d.year==2025: return 64500 + (d.month-1)*45
    return 65200 + (d.month-1)*(-25)

def other_funding_target(d):
    if d.year==2024: return 3500 - (d.month-1)*30
    if d.year==2025: return 2900 + (d.month-1)*15
    return 3000 + (d.month-1)*15

# detailed monthly snapshots
def build_detail(master, kind, target_func):
    out=[]
    for pidx,d in enumerate(periods):
        active=[r for r in master if r['start_idx']<=pidx<r['close_idx']]
        if not active: continue
        raw=[]
        for r in active:
            age=max(0,pidx-r['start_idx'])
            # natural seasoning / amortisation
            raw.append(r.get('base_amount',r.get('facility_amount',100))* (0.90+0.12*min(age,12)/12))
        alloc=normalize_alloc(raw,target_func(d))
        for r,val in zip(active,alloc):
            row={'period':fmt_period(d)}
            if kind=='loan':
                row.update({'loan_no':r['loan_no'],'product_type':r['product_type'],'facility_amount':round(r['facility_amount'],2),'outstanding':round(min(val,r['facility_amount']),2),'collectibility':r['base_quality'],'rate_pa':r['rate_pa']})
                # cap distortion: later reconcile by second pass scaling all within cap
            elif kind=='investment':
                row.update({'investment_no':r['investment_no'],'investment_type':r['investment_type'],'investment_amount':round(val,2),'collectibility':r['quality'],'rate_pa':r['rate_pa']})
            else:
                row.update({'account_no':r['account_no'],'product_type':r['product_type'],'balance':round(val,2),'rate_pa':r['rate_pa']})
            out.append(row)
    return pd.DataFrame(out)

loans=build_detail(loan_rows,'loan',loan_target)
# ensure exact monthly loan target by re-scaling within facilities; if capped, use iterative allocation
for p in loans.period.unique():
    sub=loans.period.eq(p)
    target=loan_target(pd.Timestamp(p+'-01')+pd.offsets.MonthEnd(0))
    vals=loans.loc[sub,'outstanding'].to_numpy(float)
    caps=loans.loc[sub,'facility_amount'].to_numpy(float)
    for _ in range(10):
        s=vals.sum(); free=np.where(vals < caps-1e-6)[0]
        if abs(s-target)<0.01 or len(free)==0: break
        vals[free]*=target/s
        vals=np.minimum(vals,caps)
    # final proportional adjustment on free if tiny diff
    loans.loc[sub,'outstanding']=np.round(vals,2)

# Investments and funds
investments=build_detail(inv_rows,'investment',inv_target)
funding=build_detail(fund_rows,'fund',dpk_target)
other=build_detail(other_rows,'fund',other_funding_target)
# exact monthly target scaling
for df,col,target_func in [(investments,'investment_amount',inv_target),(funding,'balance',dpk_target),(other,'balance',other_funding_target)]:
    for p in df.period.unique():
        d=pd.Timestamp(p+'-01')+pd.offsets.MonthEnd(0); mask=df.period.eq(p)
        target=target_func(d); df.loc[mask,col]=np.round(df.loc[mask,col]*target/df.loc[mask,col].sum(),2)

# Reconcile rounding to exact monthly control totals by adjusting the largest active record.
def exact_monthly_total(df, period_col, value_col, target_func):
    for p in df[period_col].unique():
        d=pd.Timestamp(p+'-01')+pd.offsets.MonthEnd(0); mask=df[period_col].eq(p)
        target=float(target_func(d)); current=float(df.loc[mask,value_col].sum())
        if mask.any():
            idx=df.loc[mask,value_col].idxmax(); df.loc[idx,value_col]=round(float(df.loc[idx,value_col])+(target-current),2)

exact_monthly_total(loans,'period','outstanding',loan_target)
exact_monthly_total(investments,'period','investment_amount',inv_target)
exact_monthly_total(funding,'period','balance',dpk_target)
exact_monthly_total(other,'period','balance',other_funding_target)

# revenues/costs in detail
loans['total_revenue']=np.round(loans.outstanding*loans.rate_pa/100/12,2)
investments['total_revenue']=np.round(investments.investment_amount*investments.rate_pa/100/12,2)
funding['total_cost_bagi_hasil']=np.round(funding.balance*funding.rate_pa/100/12,2)
other['total_cost_bagi_hasil']=np.round(other.balance*other.rate_pa/100/12,2)

# ---------- monthly summaries ----------
summary=[]
bs_rows=[]
is_rows=[]
target_rows=[]

# opening retained earnings, current year accumulated profit
prior_equity_by_year={2024:0,2025:0,2026:0}
annual_profit_acc={2024:0,2025:0,2026:0}

for d in periods:
    p=fmt_period(d)
    loan_out=loans.loc[loans.period.eq(p),'outstanding'].sum()
    inv_amt=investments.loc[investments.period.eq(p),'investment_amount'].sum()
    dpk=funding.loc[funding.period.eq(p),'balance'].sum()
    other_f=other.loc[other.period.eq(p),'balance'].sum()
    loan_rev=loans.loc[loans.period.eq(p),'total_revenue'].sum()
    inv_rev=investments.loc[investments.period.eq(p),'total_revenue'].sum()
    fund_cost=funding.loc[funding.period.eq(p),'total_cost_bagi_hasil'].sum()
    other_cost=other.loc[other.period.eq(p),'total_cost_bagi_hasil'].sum()
    # operational profile designed to yield ~1T annual profit in 2026
    total_rev=loan_rev+inv_rev
    # Scale revenue to reasonable monthly range ~900-1000bn by rates/portfolio; adjust via additional operating income.
    fee=55 + 5*math.sin(2*math.pi*(d.month-1)/12)
    rent=18
    other_income=10
    bonus=20
    admin=75 + 3*math.cos(2*math.pi*(d.month-1)/12) + 8*math.sin(2*math.pi*(d.month-1)/12)
    other_exp=12
    # CKPN driven by credit quality; base ~70-100 bn, 2026 slightly higher
    npl_ratio=1.65 + 0.25*math.sin(2*math.pi*(d.month-2)/12) + (0.15 if d.year==2025 else 0) + (0.10 if d.year==2026 else 0)
    ckpn=65 + loan_out*0.00020*(npl_ratio*10)
    # Net target around 70-100bn/month
    operating_exp=fee*0 + 180 + admin + bonus + other_exp
    # Profit formula. Add a management income adjustment so annual 2026 approaches 1T.
    gross=total_rev - fund_cost - other_cost + rent + fee + other_income - operating_exp - ckpn
    # controlled adjustment: 2024 lower, 2025 medium, 2026 target 1T
    target_month_profit={2024:720/12,2025:900/12,2026:1000/12}[d.year]
    adj=target_month_profit-gross
    # Put adjustment into Pendapatan Operasional Lainnya - Pendapatan Lainnya
    other_income += adj
    gross=total_rev - fund_cost - other_cost + rent + fee + other_income - operating_exp - ckpn
    net_profit=round(gross,2)
    annual_profit_acc[d.year]+=net_profit

    # balance sheet: assets target, liability target, equity reconciled
    total_assets=target_path(d.year,d)
    cash=max(1800, total_assets - loan_out - inv_amt - 2300 - 9000) # remainder after fixed/other; then adjust other asset below
    fixed=2300 + (d.year-2024)*80
    other_assets=total_assets-loan_out-inv_amt-cash-fixed
    # Keep cash reasonable and solve other assets
    if other_assets<2500:
        cash-=2500-other_assets
        other_assets=2500
    # liabilities and equity
    other_liab=1000 + (d.month%4)*25
    equity=total_assets-dpk-other_f-other_liab
    capital=6000
    prior_earnings=equity-capital-net_profit if d.month==12 else equity-capital-(sum([r[1] for r in []]))
    # Current year balance sheet current profit must equal current year's YTD net profit; retained prior = equity-capital-current_ytd.
    ytd=sum(r[0] for r in [])
    # compute current-year YTD from is_rows below is awkward; maintain accumulator
    # use local accumulator by year/month
    if d.month==1: annual_profit_acc[d.year]=net_profit
    else: annual_profit_acc[d.year]+=net_profit
    current_ytd=annual_profit_acc[d.year]
    prior_earnings=equity-capital-current_ytd
    # For start of 2024, force prior earnings so equation works; values may be negative/positive, okay.
    bs_rows += [
      {'period':p,'statement':'Asset','line_item':'Kas','amount':round(cash,2)},
      {'period':p,'statement':'Asset','line_item':'Penempatan','amount':round(inv_amt,2)},
      {'period':p,'statement':'Asset','line_item':'Kredit','amount':round(loan_out,2)},
      {'period':p,'statement':'Asset','line_item':'Aktiva Tetap','amount':round(fixed,2)},
      {'period':p,'statement':'Asset','line_item':'Aset Lainnya','amount':round(other_assets,2)},
      {'period':p,'statement':'Kewajiban','line_item':'Giro','amount':round(funding.loc[(funding.period.eq(p)) & funding.product_type.str.contains('Giro'),'balance'].sum(),2)},
      {'period':p,'statement':'Kewajiban','line_item':'Tabungan','amount':round(funding.loc[(funding.period.eq(p)) & funding.product_type.str.contains('Tabungan'),'balance'].sum(),2)},
      {'period':p,'statement':'Kewajiban','line_item':'Deposito','amount':round(funding.loc[(funding.period.eq(p)) & funding.product_type.str.contains('Deposito'),'balance'].sum(),2)},
      {'period':p,'statement':'Kewajiban','line_item':'Pinjaman yang diterima','amount':round(other.loc[(other.period.eq(p)) & other.product_type.eq('Pinjaman yang diterima'),'balance'].sum(),2)},
      {'period':p,'statement':'Kewajiban','line_item':'Surat Berharga Diterbitkan','amount':round(other.loc[(other.period.eq(p)) & other.product_type.eq('Surat Berharga Diterbitkan'),'balance'].sum(),2)},
      {'period':p,'statement':'Kewajiban','line_item':'Kewajiban Lainnya','amount':round(other_liab,2)},
      {'period':p,'statement':'Ekuitas','line_item':'Modal','amount':capital},
      {'period':p,'statement':'Ekuitas','line_item':'Laba Tahun Lalu','amount':round(prior_earnings,2)},
      {'period':p,'statement':'Ekuitas','line_item':'Laba Tahun Berjalan','amount':round(current_ytd,2)},
    ]
    # income statement
    revenue_map={
      'KPR Subsidi':'Consumer - KPR Subsidi','KPR Non Subsidi':'Consumer - KPR Non Subsidi','Non KPR':'Consumer - Non KPR','Multimanfaat':'Consumer - Multimanfaat','Modal Kerja':'Commercial - Modal Kerja','Investasi':'Commercial - Investasi','Konstruksi':'Commercial - Konstruksi'}
    for label,prod in revenue_map.items():
        val=loans.loc[(loans.period.eq(p)) & loans.product_type.eq(prod),'total_revenue'].sum()
        is_rows.append({'period':p,'line_item':'Pendapatan Bunga - '+label,'amount':round(val,2)})
    is_rows.append({'period':p,'line_item':'Pendapatan Investasi','amount':round(inv_rev,2)})
    for dep_label,needle in [('Giro','Giro'),('Tabungan','Tabungan'),('Deposito','Deposito')]:
        val=funding.loc[(funding.period.eq(p)) & funding.product_type.str.contains(needle),'total_cost_bagi_hasil'].sum()
        is_rows.append({'period':p,'line_item':'Beban Bunga - '+dep_label,'amount':round(val,2)})
    for other_label,needle in [('Pinjaman yang diterima','Pinjaman yang diterima'),('Surat Berharga Diterbitkan','Surat Berharga Diterbitkan')]:
        val=other.loc[(other.period.eq(p)) & other.product_type.eq(needle),'total_cost_bagi_hasil'].sum()
        is_rows.append({'period':p,'line_item':'Beban Bunga - '+other_label,'amount':round(val,2)})
    is_rows += [
      {'period':p,'line_item':'Pendapatan Operasional Lainnya - Pendapatan Sewa','amount':round(rent,2)},
      {'period':p,'line_item':'Pendapatan Operasional Lainnya - Fee Based Pendapatan Operasional Lainnya','amount':round(fee,2)},
      {'period':p,'line_item':'Pendapatan Operasional Lainnya - Pendapatan Lainnya','amount':round(other_income,2)},
      {'period':p,'line_item':'Beban Operasional Lainnya - Beban Bonus','amount':round(bonus,2)},
      {'period':p,'line_item':'Beban Operasional Lainnya - Beban CKPN','amount':round(ckpn,2)},
      {'period':p,'line_item':'Beban Operasional Lainnya - Beban Administrasi','amount':round(admin+180,2)},
      {'period':p,'line_item':'Beban Operasional Lainnya - Beban Lainnya','amount':round(other_exp,2)},
      {'period':p,'line_item':'Laba Bersih','amount':net_profit},
    ]
    # summary metrics
    low_cost=(funding.loc[(funding.period.eq(p)) & funding.product_type.str.contains('Wadiah|Tabungan'),'balance'].sum()/dpk*100)
    ckpn_cov=105 + 8*math.sin(2*math.pi*(d.month-1)/12)
    target_rows.append({'period':p,'target_type':'Growth','metric':'Total Asset','target':round(total_assets*(1.002 if d.month>1 else 1),2)})
    target_rows.append({'period':p,'target_type':'Growth','metric':'Total Credit','target':round(loan_out*1.01,2)})
    target_rows.append({'period':p,'target_type':'Growth','metric':'Total Investment','target':round(inv_amt*1.01,2)})
    target_rows.append({'period':p,'target_type':'Growth','metric':'Total DPK','target':round(dpk*1.005,2)})
    target_rows.append({'period':p,'target_type':'Funding','metric':'Total Other Funding','target':round(other_f*1.005,2)})
    target_rows.append({'period':p,'target_type':'Profitability','metric':'Total Revenue','target':round((total_rev+rent+fee+other_income)*1.01,2)})
    target_rows.append({'period':p,'target_type':'Profitability','metric':'Net Profit','target':round({2024:720,2025:900,2026:1000}[d.year]/12,2)})
    target_rows.append({'period':p,'target_type':'Efficiency','metric':'Low Cost Funding %','target':round(min(82,low_cost+2.0),2)})
    target_rows.append({'period':p,'target_type':'Efficiency','metric':'Operating Expense','target':round(operating_exp*0.97,2)})
    target_rows.append({'period':p,'target_type':'Quality','metric':'NPL Ratio %','target':2.0})
    target_rows.append({'period':p,'target_type':'Quality','metric':'CKPN Coverage %','target':110.0})
    summary.append({'period':p,'total_assets':round(total_assets,2),'total_credit':round(loan_out,2),'total_investment':round(inv_amt,2),'total_dpk':round(dpk,2),'total_other_funding':round(other_f,2),'net_profit':net_profit,'npl_ratio':round(npl_ratio,2),'ckpn_coverage':round(ckpn_cov,2),'low_cost_funding':round(low_cost,2),'revenue':round(total_rev+rent+fee+other_income,2),'operating_expense':round(operating_exp,2),'ckpn':round(ckpn,2)})

# Recalculate balance sheet equity using actual liabilities from rows, and ensure equation exactly.
bs=pd.DataFrame(bs_rows)
isdf=pd.DataFrame(is_rows)
targets=pd.DataFrame(target_rows)
summary_df=pd.DataFrame(summary)

# Fix annual current-year profit in BS after IS is complete.
for year in [2024,2025,2026]:
    annual=isdf[(isdf.period.str.startswith(str(year))) & (isdf.line_item=='Laba Bersih')]['amount'].sum()
    prev=0
    for p in summary_df[summary_df.period.str.startswith(str(year))].period:
        ytd=isdf[(isdf.period.str.startswith(str(year))) & (isdf.period<=p) & (isdf.line_item=='Laba Bersih')]['amount'].sum()
        mask=(bs.period.eq(p)&bs.line_item.eq('Laba Tahun Berjalan'))
        bs.loc[mask,'amount']=round(ytd,2)
        assets=bs[(bs.period.eq(p))&(bs.statement=='Asset')].amount.sum()
        liabs=bs[(bs.period.eq(p))&(bs.statement=='Kewajiban')].amount.sum()
        cap=bs[(bs.period.eq(p))&(bs.line_item=='Modal')].amount.sum()
        bs.loc[bs.period.eq(p)&bs.line_item.eq('Laba Tahun Lalu'),'amount']=round(assets-liabs-cap-ytd,2)

# Audit checks and audit log
checks=[]
for p in summary_df.period:
    assets=bs[(bs.period==p)&(bs.statement=='Asset')].amount.sum()
    liab=bs[(bs.period==p)&(bs.statement=='Kewajiban')].amount.sum()
    eq=bs[(bs.period==p)&(bs.statement=='Ekuitas')].amount.sum()
    net=isdf[(isdf.period==p)&(isdf.line_item=='Laba Bersih')].amount.iloc[0]
    ytd=bs[(bs.period==p)&(bs.line_item=='Laba Tahun Berjalan')].amount.iloc[0]
    loans_sum=loans[loans.period==p].outstanding.sum(); inv_sum=investments[investments.period==p].investment_amount.sum(); dpk_sum=funding[funding.period==p].balance.sum()
    checks.append({'period':p,'check':'Assets = Liabilities + Equity','difference':round(assets-liab-eq,4),'status':'PASS' if abs(assets-liab-eq)<0.02 else 'FAIL'})
    checks.append({'period':p,'check':'Net Profit = Current Year Profit in BS','difference':round(net-(ytd - (isdf[(isdf.period==p)].line_item.eq('Laba Bersih').sum()*0)),4),'status':'PASS'})
    # The second check is not monthly equality by design; current-year profit is YTD. We add separate YTD check below.
    year=p[:4]
    ytd_is=isdf[(isdf.period.str.startswith(year)) & (isdf.period<=p)&(isdf.line_item=='Laba Bersih')].amount.sum()
    checks.append({'period':p,'check':'YTD Net Profit = BS Laba Tahun Berjalan','difference':round(ytd_is-ytd,4),'status':'PASS' if abs(ytd_is-ytd)<0.02 else 'FAIL'})
    is_g=isdf[isdf.period.eq(p)]
    is_income=is_g[is_g.line_item.str.startswith('Pendapatan')].amount.sum()
    is_expense=is_g[is_g.line_item.str.startswith('Beban')].amount.sum()
    is_net=is_g[is_g.line_item.eq('Laba Bersih')].amount.iloc[0]
    checks.append({'period':p,'check':'Income Statement arithmetic','difference':round(is_income-is_expense-is_net,4),'status':'PASS' if abs(is_income-is_expense-is_net)<0.02 else 'FAIL'})
    checks.append({'period':p,'check':'Credit detail = BS Credit','difference':round(loans_sum-bs[(bs.period==p)&bs.line_item.eq('Kredit')].amount.iloc[0],4),'status':'PASS' if abs(loans_sum-bs[(bs.period==p)&bs.line_item.eq('Kredit')].amount.iloc[0])<0.02 else 'FAIL'})
    checks.append({'period':p,'check':'Investment detail = BS Penempatan','difference':round(inv_sum-bs[(bs.period==p)&bs.line_item.eq('Penempatan')].amount.iloc[0],4),'status':'PASS' if abs(inv_sum-bs[(bs.period==p)&bs.line_item.eq('Penempatan')].amount.iloc[0])<0.02 else 'FAIL'})
    checks.append({'period':p,'check':'DPK detail = BS Giro+Tabungan+Deposito','difference':round(dpk_sum-bs[(bs.period==p)&bs.statement.eq('Kewajiban') & bs.line_item.isin(['Giro','Tabungan','Deposito'])].amount.sum(),4),'status':'PASS' if abs(dpk_sum-bs[(bs.period==p)&bs.statement.eq('Kewajiban') & bs.line_item.isin(['Giro','Tabungan','Deposito'])].amount.sum())<0.02 else 'FAIL'})

# Remove the intentionally weird check and make audit clean
checks=[c for c in checks if c['check']!='Net Profit = Current Year Profit in BS']
aud=pd.DataFrame(checks)
if (aud.status!='PASS').any():
    raise RuntimeError('Audit failed: '+str(aud[aud.status!='PASS'].head()))

# summary balance sheet categories for app
bs_pivot=bs.pivot_table(index='period',columns='line_item',values='amount',aggfunc='sum').reset_index()

# Add status to details
for df,key in [(loans,'loan_no'),(investments,'investment_no'),(funding,'account_no'),(other,'account_no')]:
    df['status']='ACTIVE'

# master lifecycle file
lifecycle=[]
for r in loan_rows:
    lifecycle.append({'record_type':'Loan','record_no':r['loan_no'],'product_type':r['product_type'],'start_period':fmt_period(periods[r['start_idx']]),'close_period':fmt_period(periods[r['close_idx']-1]) if r['close_idx']<=len(periods) else ''})
for r in inv_rows:
    lifecycle.append({'record_type':'Investment','record_no':r['investment_no'],'product_type':r['investment_type'],'start_period':fmt_period(periods[r['start_idx']]),'close_period':fmt_period(periods[r['close_idx']-1]) if r['close_idx']<=len(periods) else ''})
for r in fund_rows+other_rows:
    lifecycle.append({'record_type':'Funding','record_no':r['account_no'],'product_type':r['product_type'],'start_period':fmt_period(periods[r['start_idx']]),'close_period':fmt_period(periods[r['close_idx']-1]) if r['close_idx']<=len(periods) else ''})

# write CSVs
summary_df.to_csv(DATA/'monthly_summary.csv',index=False)
bs.to_csv(DATA/'balance_sheet.csv',index=False)
isdf.to_csv(DATA/'income_statement.csv',index=False)
targets.to_csv(DATA/'monthly_targets.csv',index=False)
loans.to_csv(DATA/'loan_detail.csv',index=False)
investments.to_csv(DATA/'investment_detail.csv',index=False)
funding.to_csv(DATA/'dpk_detail.csv',index=False)
other.to_csv(DATA/'other_funding_detail.csv',index=False)
pd.DataFrame(lifecycle).to_csv(DATA/'account_lifecycle.csv',index=False)
aud.to_csv(DATA/'audit_checks.csv',index=False)

# Data dictionary / README
(DATA/'README_DATA.md').write_text('''# FinAI Simulation Data\n\nUnit: **Rp juta?** No — all financial amounts are **Rp miliar** (Rp bn), so 80,000 = Rp80 triliun.\n\nCoverage: January 2024 through September 2026. Detail records are monthly snapshots with dynamic account lifecycle (new, active, closed).\n\nFiles:\n- `monthly_summary.csv` — monthly dashboard KPIs.\n- `balance_sheet.csv` — monthly balance sheet lines.\n- `income_statement.csv` — monthly income statement lines.\n- `monthly_targets.csv` — monthly targets by metric.\n- `loan_detail.csv` — monthly loan-level detail.\n- `investment_detail.csv` — monthly investment-level detail.\n- `dpk_detail.csv` — monthly DPK account detail.\n- `other_funding_detail.csv` — monthly other-funding detail.\n- `account_lifecycle.csv` — lifecycle master for simulated accounts.\n- `audit_checks.csv` — formation-time consistency checks.\n\nThe dataset is designed so loan/investment/DPK details reconcile to the corresponding balance-sheet positions, while the balance sheet always satisfies Assets = Liabilities + Equity. The balance-sheet current-year profit is reconciled to cumulative monthly net profit for the same year.\n''',encoding='utf-8')

# Monthly lifecycle status: makes NEW / ACTIVE / CLOSED scenarios explicit.
lc=pd.DataFrame(lifecycle)
status_rows=[]
all_months=[fmt_period(d) for d in periods]
for _,r in lc.iterrows():
    for p in all_months:
        if p < r.start_period: status='NOT_STARTED'
        elif r.close_period and p > r.close_period: status='CLOSED'
        elif p == r.start_period: status='NEW'
        else: status='ACTIVE'
        status_rows.append({'record_type':r.record_type,'record_no':r.record_no,'product_type':r.product_type,'period':p,'status':status})
pd.DataFrame(status_rows).to_csv(DATA/'account_status_monthly.csv',index=False)

# print key checks
print('periods',len(periods))
print('2026 Sep summary:', summary_df[summary_df.period=='2026-09'].to_dict('records'))
print('annual profits', isdf[isdf.line_item=='Laba Bersih'].assign(year=lambda x:x.period.str[:4]).groupby('year').amount.sum().to_dict())
print('audit', len(aud), 'rows, all', (aud.status=='PASS').all())
print('files', [p.name for p in DATA.iterdir()])
