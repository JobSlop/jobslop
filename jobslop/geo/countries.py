"""Countries the app knows and how to recognise them in text."""

import re

# ---- countries: code -> (name, JobSpy name, Adzuna code, Jobicy geo, region, currency, extra place names)
COUNTRIES = {
    "GB": ("United Kingdom", "UK", "gb", "uk", "eu", "GBP", "uk|u\\.k\\.|great britain|britain|england|scotland|wales|northern ireland|london|manchester|birmingham|leeds|glasgow|edinburgh|bristol|gmt"),
    "US": ("United States", "USA", "us", "usa", "na", "USD", "usa|u\\.s\\.a?\\.?|united states|america"),
    "CA": ("Canada", "CANADA", "ca", "canada", "na", "CAD", "canada|toronto|vancouver|montreal"),
    "AU": ("Australia", "AUSTRALIA", "au", "australia", "apac", "AUD", "australia|sydney|melbourne"),
    "NZ": ("New Zealand", "NEWZEALAND", "nz", "", "apac", "NZD", "new zealand|auckland"),
    "IE": ("Ireland", "IRELAND", "", "ireland", "eu", "EUR", "ireland|dublin"),
    "DE": ("Germany", "GERMANY", "de", "germany", "eu", "EUR", "germany|deutschland|berlin|munich|hamburg"),
    "FR": ("France", "FRANCE", "fr", "france", "eu", "EUR", "france|paris"),
    "NL": ("Netherlands", "NETHERLANDS", "nl", "netherlands", "eu", "EUR", "netherlands|holland|amsterdam"),
    "BE": ("Belgium", "BELGIUM", "be", "belgium", "eu", "EUR", "belgium|brussels"),
    "ES": ("Spain", "SPAIN", "es", "spain", "eu", "EUR", "spain|madrid|barcelona"),
    "IT": ("Italy", "ITALY", "it", "italy", "eu", "EUR", "italy|milan|rome"),
    "PT": ("Portugal", "PORTUGAL", "", "portugal", "eu", "EUR", "portugal|lisbon|porto"),
    "AT": ("Austria", "AUSTRIA", "at", "austria", "eu", "EUR", "austria|vienna"),
    "CH": ("Switzerland", "SWITZERLAND", "ch", "switzerland", "eu", "CHF", "switzerland|zurich|geneva"),
    "SE": ("Sweden", "SWEDEN", "", "sweden", "eu", "SEK", "sweden|stockholm"),
    "DK": ("Denmark", "DENMARK", "", "denmark", "eu", "DKK", "denmark|copenhagen"),
    "NO": ("Norway", "NORWAY", "", "norway", "eu", "NOK", "norway|oslo"),
    "FI": ("Finland", "FINLAND", "", "finland", "eu", "EUR", "finland|helsinki"),
    "PL": ("Poland", "POLAND", "pl", "poland", "eu", "PLN", "poland|warsaw|krakow"),
    "CZ": ("Czech Republic", "CZECHREPUBLIC", "", "czechia", "eu", "CZK", "czech|czechia|prague"),
    "RO": ("Romania", "ROMANIA", "", "romania", "eu", "RON", "romania|bucharest"),
    "GR": ("Greece", "GREECE", "", "greece", "eu", "EUR", "greece|athens"),
    "HU": ("Hungary", "HUNGARY", "", "hungary", "eu", "HUF", "hungary|budapest"),
    "UA": ("Ukraine", "UKRAINE", "", "ukraine", "eu", "UAH", "ukraine|kyiv"),
    "TR": ("Turkey", "TURKEY", "", "turkiye", "emea", "TRY", "turkey|türkiye|turkiye|istanbul"),
    "IN": ("India", "INDIA", "in", "india", "apac", "INR", "india|bangalore|bengaluru|mumbai|delhi|hyderabad|pune"),
    "SG": ("Singapore", "SINGAPORE", "sg", "singapore", "apac", "SGD", "singapore"),
    "MY": ("Malaysia", "MALAYSIA", "", "malaysia", "apac", "MYR", "malaysia|kuala lumpur"),
    "PH": ("Philippines", "PHILIPPINES", "", "philippines", "apac", "PHP", "philippines|manila"),
    "JP": ("Japan", "JAPAN", "", "japan", "apac", "JPY", "japan|tokyo"),
    "KR": ("South Korea", "SOUTHKOREA", "", "south-korea", "apac", "KRW", "korea|seoul"),
    "HK": ("Hong Kong", "HONGKONG", "", "", "apac", "HKD", "hong kong"),
    "ID": ("Indonesia", "INDONESIA", "", "indonesia", "apac", "IDR", "indonesia|jakarta"),
    "TH": ("Thailand", "THAILAND", "", "thailand", "apac", "THB", "thailand|bangkok"),
    "VN": ("Vietnam", "VIETNAM", "", "vietnam", "apac", "VND", "vietnam|ho chi minh|hanoi"),
    "AE": ("United Arab Emirates", "UNITEDARABEMIRATES", "", "uae", "emea", "AED", "uae|united arab emirates|dubai|abu dhabi"),
    "SA": ("Saudi Arabia", "SAUDIARABIA", "", "", "emea", "SAR", "saudi|riyadh"),
    "QA": ("Qatar", "QATAR", "", "", "emea", "QAR", "qatar|doha"),
    "IL": ("Israel", "ISRAEL", "", "israel", "emea", "ILS", "israel|tel aviv"),
    "EG": ("Egypt", "EGYPT", "", "egypt", "emea", "EGP", "egypt|cairo"),
    "ZA": ("South Africa", "SOUTHAFRICA", "za", "south-africa", "emea", "ZAR", "south africa|johannesburg|cape town"),
    "NG": ("Nigeria", "NIGERIA", "", "nigeria", "emea", "NGN", "nigeria|lagos"),
    "BR": ("Brazil", "BRAZIL", "br", "brazil", "latam", "BRL", "brazil|brasil|são paulo|sao paulo"),
    "MX": ("Mexico", "MEXICO", "mx", "mexico", "latam", "MXN", "mexico|méxico"),
    "AR": ("Argentina", "ARGENTINA", "", "argentina", "latam", "ARS", "argentina|buenos aires"),
    "CL": ("Chile", "CHILE", "", "chile", "latam", "CLP", "chile|santiago"),
    "CO": ("Colombia", "COLOMBIA", "", "colombia", "latam", "COP", "colombia|bogota|bogotá"),
}
REGIONS = {"eu": "europe|emea|eu|european union|cet|gmt",
           "na": "north america|americas|us timezones|est|pst",
           "apac": "apac|asia|asia pacific|oceania",
           "emea": "emea|middle east|africa",
           "latam": "latam|latin america|south america|americas"}


def country_info(code):
    return COUNTRIES.get((code or "GB").upper(), COUNTRIES["GB"])


def local_ok_re(code):
    """Locations someone in this country can work from (filters the remote boards)."""
    name, _, _, _, region, _, extra = country_info(code)
    pat = "|".join([re.escape(name.lower()), extra, REGIONS.get(region, ""), "worldwide|anywhere|global"])
    return re.compile(r"(?<![a-z])(" + pat.strip("|") + r")(?![a-z])", re.I)


COUNTRY_ALIASES = {"uk": "GB", "u.k.": "GB", "britain": "GB", "great britain": "GB", "england": "GB", "gb": "GB",
                   "usa": "US", "us": "US", "u.s.": "US", "america": "US", "united states of america": "US",
                   "deutschland": "DE", "holland": "NL", "uae": "AE", "the netherlands": "NL",
                   # how countries are written in their own languages (job boards use these)
                   "nederland": "NL", "danmark": "DK", "españa": "ES", "espana": "ES", "italia": "IT", "sverige": "SE",
                   "norge": "NO", "suomi": "FI", "polska": "PL", "schweiz": "CH", "suisse": "CH", "österreich": "AT",
                   "belgië": "BE", "belgie": "BE", "belgique": "BE", "brasil": "BR", "méxico": "MX", "eire": "IE",
                   "éire": "IE", "verenigd koninkrijk": "GB", "storbritannien": "GB", "verenigde staten": "US",
                   "usa (remote)": "US", "england, uk": "GB", "eng": "GB", "sct": "GB", "wls": "GB"}


def is_country_name(text, code):
    """True when 'Where?' is empty or just names the whole country ("UK", "Germany")."""
    t = (text or "").strip().lower()
    if not t:
        return True
    code = (code or "GB").upper()
    return t in (country_info(code)[0].lower(), code.lower()) or COUNTRY_ALIASES.get(t) == code


US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
                "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
US_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"}
