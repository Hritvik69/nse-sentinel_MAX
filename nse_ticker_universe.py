"""
nse_ticker_universe.py
──────────────────────
SINGLE SOURCE OF TRUTH for all NSE tickers used by NSE Sentinel.

EVERY component that needs a ticker list must import from here:
    from nse_ticker_universe import get_all_tickers

Design
──────
• Repo `nse_tickers.txt` is loaded first so deployments get the committed universe.
• Hardcoded baseline backs it up if the text file is missing.
• Optional GitHub raw lists, NSE EQUITY_L.csv, and bhav copy add more symbols
  when the host network allows them.
• Returns deduplicated, sorted list of "SYMBOL.NS" strings.
• Never raises. Never returns an empty list (falls back to baseline).

Public API
──────────
    get_all_tickers(live=True)  → list[str]     (cached after first call)
    get_bare_symbols()          → list[str]     (without .NS suffix)
    ticker_count()              → int
"""

from __future__ import annotations

import io
import re
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

_LOCK  = threading.Lock()
_cache: dict[bool, list[str]] = {}

# ══════════════════════════════════════════════════════════════════════
# BASELINE  (~2100 NSE mainboard symbols, hardcoded — always available)
# ══════════════════════════════════════════════════════════════════════
_BASELINE: list[str] = [
    # ── LARGE CAP / NIFTY 50 ─────────────────────────────────────────
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN",
    "BHARTIARTL","ITC","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI",
    "BAJFINANCE","HCLTECH","SUNPHARMA","TITAN","ULTRACEMCO","ONGC",
    "NESTLEIND","WIPRO","POWERGRID","NTPC","TECHM","INDUSINDBK","ADANIPORTS",
    "TATAMOTORS","JSWSTEEL","BAJAJFINSV","HINDALCO","GRASIM","DIVISLAB",
    "CIPLA","DRREDDY","BPCL","EICHERMOT","APOLLOHOSP","TATACONSUM","BRITANNIA",
    "COALINDIA","HEROMOTOCO","SHREECEM","SBILIFE","HDFCLIFE","ADANIENT",
    "BAJAJ-AUTO","TATASTEEL","UPL","M&M",
    # ── NIFTY NEXT 50 ────────────────────────────────────────────────
    "ADANIGREEN","ADANITRANS","ATGL","AWL","BAJAJHFL","BANKBARODA",
    "BERGEPAINT","BEL","BHEL","BOSCHLTD","CANBK","CGPOWER","CHOLAFIN",
    "COLPAL","CUMMINSIND","DABUR","DLF","DMART","GODREJCP","GODREJPROP",
    "HAL","HAVELLS","HDFCAMC","ICICIGI","ICICIPRULI","IOC","IRCTC",
    "IRFC","LODHA","LTIM","LTTS","MARICO","MOTHERSON","MUTHOOTFIN",
    "NAUKRI","NHPC","OFSS","PAGEIND","PERSISTENT","PFC","PIDILITIND",
    "POLYCAB","PNB","RECLTD","SHRIRAMFIN","SRF","TORNTPHARM","TRENT",
    "TVSMOTOR","UNIONBANK","VEDL","ZOMATO","ZYDUSLIFE",
    # ── NIFTY MIDCAP 150 ─────────────────────────────────────────────
    "AARTIIND","ABCAPITAL","ABFRL","ACC","AFFLE","AJANTPHARM",
    "ALKEM","ALKYLAMINE","ANGELONE","APLAPOLLO","APOLLOTYRE","APTUS",
    "ASTRAL","AUBANK","AUROPHARMA","BALKRISHIND","BANDHANBNK","BATAINDIA",
    "BIKAJI","BIOCON","BIRLASOFT","BLUESTARCO","BRIGADE","CARBORUNIV",
    "CASTROLIND","CDSL","CESC","CHENNPETRO","CLEAN","COFORGE","CROMPTON",
    "CYIENT","DALBHARAT","DATAMATICS","DCBBANK","DEEPAKNTR","DELHIVERY",
    "DEVYANI","DIXON","DOMS","ECLERX","EIDPARRY","ELGIEQUIP",
    "EMAMILTD","ENDURANCE","EPL","EQUITASBNK","ESCORTS","EXIDEIND",
    "FINEORG","FLUOROCHEM","FORTIS","GABRIEL","GALAXYSURF","GLAND",
    "GLAXO","GLENMARK","GNFC","GRINDWELL","GSFC","GUJGASLTD",
    "HAPPSTMNDS","HATSUN","HFCL","HLEGLAS","HOMEFIRST","HPCL",
    "HUDCO","IEX","IGL","INDIAMART","INDIGO","INOXWIND","IOB",
    "IPCALAB","IREDA","ISEC","JBCHEPHARM","JKCEMENT","JKLAKSHMI",
    "JMFINANCIL","JSL","JUBILANT","JUBLFOOD","KAJARIACER","KALPATPOWR",
    "KALYANKJIL","KANSAINER","KEC","KIMS","KPITTECH","KRSNAA",
    "KSCL","LAURUSLABS","LAXMIMACH","LICHSGFIN","LLOYDSME","LUXIND",
    "MANAPPURAM","MANKIND","MAPMYINDIA","MASTEK","MAXHEALTH",
    "METROPOLIS","MFSL","MIDHANI","MOTILALOFS",
    "MPHASIS","MRPL","NAVINFLUOR","NBCC","NIACL","NILKAMAL",
    "NMDC","NOCIL","NYKAA","OBEROIRLTY","OIL","ORIENTELEC","PATELENG",
    "PAYTM","PCBL","PGHH","PHOENIXLTD","PNBHOUSING","POLICYBZR",
    "POLYMED","PRESTIGE","PRINCEPIPE","RITES","RVNL","SAFARI",
    "SAIL","SCHAEFFLER","SJVN","SKF","SOBHA","SONACOMS",
    "STARHEALTH","SUDARSCHEM","SUNDARMFIN",
    "SUNTECK","SUNTV","SUZLON","SYMPHONY",
    "TANLA","TATACHEM","TATACOMM","TATAPOWER","TEAMLEASE",
    "TIINDIA","TIMKEN","TITAGARH","TORNTPOWER","TRIDENT",
    "TRIVENI","UJJIVANSFB","UTIAMC","VGUARD",
    "VMART","VOLTAS","WELSPUNLIV","WHIRLPOOL",
    "ZEEL","ZENSAR",
    # ── NIFTY SMALLCAP 250 ───────────────────────────────────────────
    "3MINDIA","AAVAS","ACE","ACRYSIL","ADFFOODS","AEGISLOG","AETHER",
    "AIAENG","AKZOINDIA","ALEMBICLTD","ALICON","ALLCARGO","ALOKINDS","AMBIKCO",
    "AMBUJACEM","AMBER","ANANTRAJ","ANUP","APARINDS","APOLLOPIPE",
    "ARCHIDPLY","ARVINDFASHN","ASAHIINDIA","ASHIANA","ASHOKLEY","ASTERDM",
    "ASTRAZEN","ATUL","AVANTIFEED","AXISCADES","AZAD",
    "BAJAJCON","BAJAJHIND","BALKRISHIND","BALMLAWRIE","BALRAMCHIN","BANKBARODA",
    "BASF","BBTC","BECTORFOOD","BHAGERIA","BHARATFORG","BHARATGEAR",
    "BHORUKA","BIRLACABLE","BOROLTD","BPL","BSEINDIA","BURGERKING",
    "BUTTERFLY","CADILAHC","CAMLINFINE","CAMPUS",
    "CANFINHOME","CANTABIL","CAPACITE","CARERATING","CARTRADE",
    "CERA","CHALET","CHAMBLFERT","CHEMPLASTS",
    "CIEINDIA","CMSINFO","COCHINSHIP","COROMANDEL","COSMOFILMS","CRAFTSMAN",
    "CREDITACC","CRISIL","CUMMINSIND","CYIENT","DALBHARAT","DALMIASUG",
    "DBCORP","DCBBANK","DEEPAKFERT","DELTACORP","DHARMAJ","DISHTV",
    "DOLLAR","DREDGECORP","EASEMYTRIP","ECLERX","EIDPARRY","EIL",
    "ELECTCAST","ELGIEQUIP","EMKAY","ESABINDIA","ESAFSFB","ESCORTS",
    "ESTER","ETHOSLTD","FEDERALBNK","FINEORG","FINOLEX",
    "FORCEMOT","FORTIS","GAEL","GALAXYSURF","GANESHBE","GARFIBRES","GARWARE",
    "GATI","GATEWAY","GHCL","GILLETTE","GLOBALVECT",
    "GMBREW","GMRAIRPORT","GNFC","GOACARBON","GOKALDAS","GOLDIAM",
    "GOODLUCK","GPIL","GPPL","GRANULES","GREAVESCOT","GREENPANEL",
    "GREENPLY","GRINDWELL","GRSE","GUFICBIO","GUJALKALI","GUJGASLTD",
    "GULFOILLUB","HCG","HDFCAMC","HECL","HERITGFOOD","HFCL","HGINFRA",
    "HIKAL","HLEGLAS","HMVL","HONAUT","HUBTOWN","HUHTAMAKI",
    "IBREALEST","IDFC","IDFCFIRSTB","INDHOTEL","INDIAMART",
    "INDIANB","INDIGO","INDORAMA","INDOSTAR","INFIBEAM","INTELLECT",
    "IOB","IPCALAB","IRCON","ISEC","ITD","ITDCEM","IVP",
    "JAGRAN","JAIBALAJI","JAICORPLTD","JAMNAAUTO","JASH","JBMA",
    "JCHAC","JIOFIN","JKTYRE","JMFINANCIL","JPPOWER",
    "JTEKTINDIA","JUSTDIAL","JYOTHYLAB","KAJARIACER","KALPATPOWR","KALYANKJIL",
    "KAMDHENU","KANSAINER","KARURVYSYA","KCP","KDDL","KHADIM",
    "KIRIINDUS","KNR","KOLTEPATIL","KOPRAN","KPRMILL","KRBL","KSCL",
    "LATENTVIEW","LAURUSLABS","LEMONTREE","LLOYDSME","LUPIN","LUXIND",
    "MAHINDCIE","MAHINDLOG","MAHSEAMLES","MAITHANALL","MANAPPURAM","MARKSANS",
    "MASTEK","MAWANASUG","MCDOWELL-N","MEDPLUS","MFSL","MIDHANI",
    "MINDAIND","MINDACORP","MINDSPACE","MIRC","MMTC","MOLDTEK",
    "MONTECARLO","MOTILALOFS","MPHASIS","MRPL","MSTCLTD","MUTHOOTCAP",
    "NACLIND","NAHARPOLY","NAHARSPINN","NAVNETEDUL","NBCC",
    "NEULANDLAB","NEWGEN","NILKAMAL","NLCINDIA","NOCIL","NUCLEUS",
    "OBEROIRLTY","OFSS","ORCHPHARMA","ORIENTBELL","ORIENTCEM","ORIENTELEC",
    "PAISALO","PANAMAPET","PARADEEP","PATELENG","PFIZER",
    "PHOENIXLTD","PILANIINVS","POLYMED","POWERMECH","PPAP","PRAJIND",
    "PRICOLLTD","PRISM","PVRINOX","QUESS","QUICKHEAL","RADICO",
    "RAJRATAN","RALLIS","RAMCOCEM","RAYMOND","RBLBANK","RECLTD",
    "REDTAPE","RELAXO","RENUKA","REPCOHOME","RFCL","RITES",
    "ROLEXRINGS","ROSSARI","RPOWER","RUPA","RVNL","SAFARI","SAKSOFT",
    "SANOFI","SAPPHIRE","SEASOFTS","SEQUENT","SESHAPAPER",
    "SHANKARA","SHAREINDIA","SHILPAMED","SHIVALIK","SHOPERSTOP",
    "SIYSIL","SKFINDIA","SKIPPER","SNOWMAN","SOBHA","SOLARA",
    "SOLARINDS","SONACOMS","SOTL","SPARC","STLTECH","SUBROS",
    "SUPRIYA","SUPRAJIT","SURANASOL","SURYAROSNI","SUVENPHAR",
    "SYMPHONY","TAINWALCHM","TANLA","TATACHEM","TATACOMM","TATAPOWER",
    "TDPOWERSYS","THYROCARE","TIINDIA","TIMKEN","TITAGARH",
    "TORNTPOWER","TRIDENT","TRIVENI","UFLEX","UJJIVANSFB","UTIAMC",
    "VGUARD","VIPIND","VMART","VOLTAMP","VOLTAS","VSTIND","WELSPUNLIV",
    "WHIRLPOOL","ZEEL","ZENSAR",
    # ── BANKS & NBFC ─────────────────────────────────────────────────
    "HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK",
    "BANKBARODA","PNB","UNIONBANK","CANBK","IDFCFIRSTB","FEDERALBNK",
    "RBLBANK","KARURVYSYA","DCBBANK","AUBANK","EQUITASBNK","UJJIVANSFB",
    "ESAFSFB","CAPITALSFB","JSFB","SURYODAY","UTKARSHBNK","NSDL",
    "BAJFINANCE","BAJAJFINSV","CHOLAFIN","MUTHOOTFIN","MANAPPURAM",
    "SHRIRAMFIN","LICHSGFIN","PNBHOUSING","CANFINHOME","HOMEFIRST",
    "APTUS","AAVAS","REPCO","CREDITACC","SRTRANSFIN","TATAELXSI",
    "HDFCAMC","UTIAMC","ABSLAMC","NAUKRI","ANGELONE","ISEC","IIFL",
    "CDSL","BSEINDIA","MCXINDIA","5PAISA","ICICIGI","ICICIPRULI",
    "SBILIFE","HDFCLIFE","STARHEALTH","MAXFINSERV","MFSL","BAJAJHFL",
    # ── IT & TECH ────────────────────────────────────────────────────
    "TCS","INFY","HCLTECH","WIPRO","TECHM","LTIM","LTTS","MPHASIS",
    "COFORGE","PERSISTENT","KPITTECH","BIRLASOFT","MASTEK","CYIENT",
    "ECLERX","NIIT","NIITLTD","RATEPOWER","RATEGAIN","TANLA","NEWGEN",
    "INTELLECT","HAPPSTMNDS","TATAELXSI","ZENSAR","HEXAWARE","NUCLEUS",
    "SAKSOFT","DATAMATICS","QUICKHEAL","INFIBEAM","INDIAMART","AFFLE",
    "NAZARA","LATENTVIEW","MAPMYINDIA","ZAGGLE","NAUKRI",
    # ── PHARMA / HEALTH ──────────────────────────────────────────────
    "SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","AUROPHARMA","BIOCON",
    "LUPIN","ALKEM","AJANTPHARM","IPCALAB","NATCOPHARMA","JBCHEPHARM",
    "GLENMARK","GLAND","GRANULES","LAURUSLABS","FLUOROCHEM","SOLARA",
    "SEQUENT","SUPRIYA","NAVINFLUOR","SUVENPHAR","NEULANDLAB","ORCHPHARMA",
    "FINEORG","ALKYLAMINE","DEEPAKNTR","NOCIL","SUDARSCHEM","VINATIORGA",
    "LXCHEM","AARTI","AARTIIND","VINATI","PCBL","ROSSARI","TATACHEM",
    "GNFC","GSFC","EIDPARRY","COROMANDEL","UPL","RALLIS","DHANUKA",
    "BAYER","PARADEEP","INSECTICID",
    "APOLLOHOSP","MAXHEALTH","FORTIS","KIMS","ASTER","ASTERDM",
    "NARAYANAH","SHALBY","THYROCARE","METROPOLIS","KRSNAA","HCG",
    # ── AUTO & ANCILLARIES ───────────────────────────────────────────
    "MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT",
    "TVSMOTOR","ASHOKLEY","ESCORTS","FORCEMOT","SMLISUZU",
    "BALKRISHIND","APOLLOTYRE","JKTYRE","CEATLTD","MINDA",
    "MOTHERSON","BOSCHLTD","ENDURANCE","MINDACORP","SONACOMS","TIINDIA",
    "SUPRAJIT","SUBROS","GABRIEL","WABCOINDIA","JTEKTINDIA","CRAFTSMAN",
    "SCHAEFFLER","SKF","TIMKEN","NRB","MAHINDCIE","PRICOLLTD",
    "SWARAJENG","MAHSCOOTER","MAHINDRA",
    # ── METALS & MINING ──────────────────────────────────────────────
    "TATASTEEL","JSWSTEEL","HINDALCO","VEDL","SAIL","NMDC","MOIL",
    "NALCO","HINDCOPPER","TINPLATE","RATNAMANI","APL","JSL",
    "APLAPOLLO","LLOYDSME","JSHL","GPIL","NAVA","WELCORP","SUNFLAG",
    "JTEKTINDIA","KALYANKJIL",
    # ── ENERGY / OIL & GAS ───────────────────────────────────────────
    "ONGC","BPCL","IOC","HPCL","GAIL","OIL","MRPL","CHENNPETRO",
    "ATGL","IGL","MGL","GUJGASLTD","GSPL","TORNTPOWER","TATAPOWER",
    "ADANIGREEN","ADANIPOWER","ADANITRANS","NHPC","NTPC","POWERGRID",
    "SJVN","IREDA","INOXWIND","SUZLON","RPOWER","JPPOWER","CESC",
    "TORNTPOWER","PTC","NLCINDIA",
    # ── FMCG ─────────────────────────────────────────────────────────
    "HINDUNILVR","ITC","NESTLEIND","BRITANNIA","TATACONSUM","MARICO",
    "GODREJCP","DABUR","EMAMILTD","COLPAL","PGHH","JYOTHYLAB","BAJAJCON",
    "GILLETTE","BIKAJI","AVANTIFEED","KRBL","HATSUN","HERITGFOOD",
    "VSTIND","RADICO","MCDOWELL-N","TILAKNAGAR",
    # ── RETAIL / CONSUMER ────────────────────────────────────────────
    "TRENT","DMART","WESTLIFE","JUBLFOOD","DEVYANI","DIXON","AMBER",
    "SHOPERSTOP","VMART","BATAINDIA","RELAXO","KPRMILL",
    "PAGEIND","VEDANT","GOKALDAS","RAYMOND","CANTABIL","VIPIND",
    "LUXIND","RUPA","DOLLAR","CAMPUS","NYKAA","SAFARI","DOMS","REDTAPE",
    # ── REAL ESTATE / INFRA ──────────────────────────────────────────
    "DLF","OBEROIRLTY","GODREJPROP","PHOENIXLTD","BRIGADE","SOBHA",
    "KOLTEPATIL","SUNTECK","LODHA","PRESTIGE","ANANTRAJ","OMAXE",
    "NESCO","IBREALEST","MHRIL","CHALET","LEMONTREE","INDHOTEL",
    # ── CAPITAL GOODS / ENGINEERING ──────────────────────────────────
    "LT","SIEMENS","ABB","BHEL","THERMAX","CUMMINSIND","ELGIEQUIP",
    "KEC","KALPATPOWR","GRINDWELL","TIMKEN","SKF","SCHAEFFLER","HAL",
    "BEL","MTAR","GRSE","COCHINSHIP","MAZAGON",
    "PATELENG","NBCC","IRCON","HGINFRA","KNR","ASHOKA",
    "ITD","CAPACITE","GPPL","CONCOR","ALLCARGO","AEGISLOG","BLUEDART",
    "GATI","TCI","DREDGECORP","RVNL","RAILTEL","TITAGARH",
    "AIAENG","APARINDS","GREAVESCOT","TDPOWERSYS","VOLTAMP","POWERMECH",
    # ── TELECOM / MEDIA ──────────────────────────────────────────────
    "BHARTIARTL","TATACOMM","RAILTEL","HFCL","STLTECH",
    "INDUSTOWER","OPTIEMUS","DISHTV","SUNTV","PVRINOX","DBCORP",
    "JAGRAN","HMVL","NDTV","ZEEMEDIA",
    # ── AGRI / FERTILISERS ───────────────────────────────────────────
    "UPL","DHANUKA","BAYER","RALLIS","PARADEEP","COROMANDEL","GSFC",
    "GNFC","CHAMBLFERT","KSCL","INSECTICID","DHARMAJ","EIDPARRY",
    "BAJAJHIND","BALRAMCHIN","RENUKA","TRIVENI","MAWANASUG",
    # ── LOGISTICS ────────────────────────────────────────────────────
    "DELHIVERY","ALLCARGO","GATI","TCI","BLUEDART","CONCOR","SNOWMAN",
    "INTERGLOBE","SPICEJET","GMRAIRPORT",
    # ── TEXTILES ─────────────────────────────────────────────────────
    "WELSPUNLIV","TRIDENT","RAYMOND","SIYARAM","VIPIND","GOKALDAS",
    "ARVINDFASHN","SUTLEJTEX","AYMSYNTEX","FILATEX","GARFIBRES","GARWARE",
    "MORARJEE","MPDL",
    # ── PAPER / PACKAGING ────────────────────────────────────────────
    "UFLEX","MOLDTEK","HUHTAMAKI","EPL","COSMOFILMS","PRINCEPIPE","ASTRAL",
    # ── DEFENCE ──────────────────────────────────────────────────────
    "HAL","BEL","BHEL","MTAR","GRSE","COCHINSHIP","MAZAGON","MIDHANI",
    "IDEAFORGE",
    # ── GEMS & JEWELLERY ─────────────────────────────────────────────
    "TITAN","KALYANKJIL","RAJESHEXPO","GOLDIAM","SENCO","THANGAMAYL",
    # ── CONSUMER DURABLES ────────────────────────────────────────────
    "HAVELLS","CROMPTON","ORIENTELEC","BLUESTARCO","VOLTAS","SYMPHONY",
    "VGUARD","CERA","KAJARIACER","SOMANYCER",
    # ── MISC ─────────────────────────────────────────────────────────
    "GREENPLY","BAJAJELEC","QUESS","TEAMLEASE","JUSTDIAL",
    "AFFLE","RATEGAIN","NAZARA","LATENTVIEW","ZAGGLE","EASEMYTRIP",
    "MMTC","STCINDIA","MSTCLTD","IRCTC","ABBOTINDIA","HONAUT",
    "GLAXO","PFIZER","SANOFI","CARBORUNIV","WENDT","ELGIEQUIP",
]

_REPO_TICKER_FILE = Path(__file__).with_name("nse_tickers.txt")
_VALID_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{1,20}$")
_RAW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain,text/csv,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/",
}
_GITHUB_URLS = [
    "https://raw.githubusercontent.com/pkjmesra/PKScreener/main/pkscreener/classes/tickerlist.txt",
    "https://raw.githubusercontent.com/pkjmesra/PKScreener/main/pkscreener/classes/Tickers.txt",
    "https://raw.githubusercontent.com/NayakwadiS/nse_Ticker/master/Nse_Ticker25.txt",
    "https://raw.githubusercontent.com/Screeni-python/Screeni/main/classes/tickerlist.txt",
    "https://raw.githubusercontent.com/hi-tech-jazz/nse/main/symbols.txt",
]
_NORMALIZE_MAP = {
    "BHARATIARTL": "BHARTIARTL",
    "BHARATIHEXA": "BHARTIHEXA",
    "ANGELBROKING": "ANGELONE",
    "DRREDDYS": "DRREDDY",
    "DMMART": "DMART",
    "PARDEEP": "PARADEEP",
    "PATEL": "PATELENG",
    "MOLD-TEK": "MOLDTEK",
    "DIVI": "DIVISLAB",
    "CAMPUSACTIVEWEAR": "CAMPUS",
    "PARASONFL": "PARAGONFL",
    "RATEAIN": "RATEGAIN",
    "AHEMDABDSTL": "AHMEDABADSTEEL",
}
_DROP_SYMBOLS = {
    "AARTIINDALKEM",
    "AIRPORT",
    "CAREGIVING",
    "INDUIND",
    "RBKL",
    "WABAGGOO",
    "ORDNANCE",
    "MCDONALDS",
    "NATIONAL",
    "PATANJALIFO",
    "TVSTOUCHSCR",
    "TORRENTP",
}

# ══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════

def get_all_tickers(live: bool = True) -> list[str]:
    """
    Return sorted list of 'SYMBOL.NS' strings.

    live=True  → attempts NSE EQUITY_L.csv + bhav copy supplement
                 (silently skipped if network is unavailable)
    live=False → returns baseline only (instant, zero network)

    Result is cached by live/static mode (thread-safe).
    Never raises. Never returns an empty list.
    """
    with _LOCK:
        if live in _cache:
            return _cache[live]
        result = _build(live)
        _cache[live] = result
        return result


def get_bare_symbols() -> list[str]:
    """Return ticker list without .NS suffix."""
    return [t.replace(".NS", "") for t in get_all_tickers()]


def ticker_count() -> int:
    return len(get_all_tickers())


def invalidate_cache() -> None:
    """Force re-build on next call (e.g. after a manual refresh)."""
    with _LOCK:
        _cache.clear()


# ══════════════════════════════════════════════════════════════════════
# INTERNAL BUILDER
# ══════════════════════════════════════════════════════════════════════

def _build(live: bool) -> list[str]:
    tickers = _load_repo_tickers()
    tickers.update(_baseline_tickers())

    if not live:
        return sorted(tickers)

    if len(tickers) < 2500:
        tickers.update(_fetch_github_raw_lists())
    if len(tickers) < 2500:
        tickers.update(_fetch_nse_equity_list())
    if len(tickers) < 2500:
        tickers.update(_fetch_bhav_copy())

    if not tickers:
        tickers = _baseline_tickers()
    return sorted(tickers)


def _normalize_symbol(raw: str) -> str | None:
    symbol = str(raw).strip().upper().replace(".NS", "")
    symbol = _NORMALIZE_MAP.get(symbol, symbol)
    if symbol in _DROP_SYMBOLS:
        return None
    if not _VALID_SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def _format_symbol(raw: str) -> str | None:
    symbol = _normalize_symbol(raw)
    if symbol is None:
        return None
    return f"{symbol}.NS"


def _baseline_tickers() -> set[str]:
    return {
        formatted
        for formatted in (_format_symbol(symbol) for symbol in _BASELINE)
        if formatted is not None
    }


def _load_repo_tickers() -> set[str]:
    tickers: set[str] = set()
    try:
        if _REPO_TICKER_FILE.exists():
            for line in _REPO_TICKER_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
                formatted = _format_symbol(line)
                if formatted is not None:
                    tickers.add(formatted)
    except Exception:
        pass
    return tickers


def _fetch_github_raw_lists() -> set[str]:
    tickers: set[str] = set()
    try:
        import requests

        for url in _GITHUB_URLS:
            try:
                response = requests.get(url, headers=_RAW_HEADERS, timeout=12)
                if response.status_code != 200 or len(response.content) < 100:
                    continue
                for line in response.text.splitlines():
                    token = line.strip().split(",")[0].replace('"', "").replace("'", "")
                    formatted = _format_symbol(token)
                    if formatted is not None:
                        tickers.add(formatted)
            except Exception:
                continue
    except Exception:
        pass
    return tickers


def _fetch_nse_equity_list() -> set[str]:
    tickers: set[str] = set()
    try:
        import pandas as pd
        import requests

        session = requests.Session()
        session.headers.update(_RAW_HEADERS)
        session.get("https://www.nseindia.com/", timeout=8)
        response = session.get(
            "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
            timeout=15,
        )
        if response.status_code == 200 and len(response.content) > 5000:
            dataframe = pd.read_csv(io.StringIO(response.text))
            column = "SYMBOL" if "SYMBOL" in dataframe.columns else dataframe.columns[0]
            for symbol in dataframe[column].dropna().unique():
                formatted = _format_symbol(symbol)
                if formatted is not None:
                    tickers.add(formatted)
    except Exception:
        pass
    return tickers


def _fetch_bhav_copy() -> set[str]:
    tickers: set[str] = set()
    try:
        import pandas as pd
        import requests

        for days_back in range(0, 7):
            try:
                dt = datetime.now() - timedelta(days=days_back)
                if dt.weekday() >= 5:
                    continue
                date_str = dt.strftime("%d%b%Y").upper()
                url = (
                    f"https://archives.nseindia.com/content/historical/EQUITIES/"
                    f"{dt.year}/{dt.strftime('%b').upper()}/cm{date_str}bhav.csv.zip"
                )
                response = requests.get(url, headers=_RAW_HEADERS, timeout=15)
                if response.status_code != 200 or len(response.content) < 1000:
                    continue
                zipped = zipfile.ZipFile(io.BytesIO(response.content))
                dataframe = pd.read_csv(zipped.open(zipped.namelist()[0]))
                for symbol in dataframe["SYMBOL"].dropna().unique():
                    formatted = _format_symbol(symbol)
                    if formatted is not None:
                        tickers.add(formatted)
                if tickers:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return tickers
