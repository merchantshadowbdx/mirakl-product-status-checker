import streamlit as st
import requests
import pandas as pd
from io import StringIO
from datetime import date

st.set_page_config(
    page_title="Mirakl Product Status Checker",
    layout="wide",
    page_icon="./icons/logo_color.png"
)
t1, t2 = st.columns([0.1, 1.5])
with t1:
    st.image("./icons/logo_color.png", width=75)
with t2:
    st.title("MIRAKL PRODUCT STATUS CHECKER")

# --- Session state (pour Reset)
DEFAULTS = {
    "status_choice": "ALL",
    "date_since": None,
    "date_to": None,
    "skus_raw": "",
    "shop_id": "",
    "api_key": "",
    "sales_channel": None,
}

for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

def reset_filters():
    st.session_state["status_choice"] = DEFAULTS["status_choice"]
    st.session_state["status_choice_label"] = DEFAULTS["status_choice"]
    st.session_state["date_since"] = DEFAULTS["date_since"]
    st.session_state["date_to"] = DEFAULTS["date_to"]
    st.session_state["skus_raw"] = DEFAULTS["skus_raw"]
    # Décommenter pour remettre à zéro la partie identification
    # st.session_state["shop_id"] = DEFAULTS["shop_id"]
    # st.session_state["api_key"] = DEFAULTS["api_key"]
    # st.session_state["sales_channel"] = DEFAULTS["sales_channel"]

# --- Helpers
def parse_identifiers(raw: str) -> list[str]:
    """Séparé par nouvelle ligne/virgule/point virgule/espace."""
    if not raw:
        return []
    seps = [",", ";", "\n", " "]
    for s in seps:
        raw = raw.replace(s, "|")
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

def build_params(
    status: str,
    since: date | None,
    to: date | None,
    skus: list[str],
    shop_id: str
):
    """
    Construit les params Mirakl :
    - Dates en ISO si présentes (00:00:00Z / 23:59:59Z).
    - Statut ALL/LIVE/NOT_LIVE.
    - SKUs en clés répétées provider_unique_identifier.
    """
    params = []

    if since:
        params.append(("updated_since", f"{since}T00:00:00Z"))
    if to:
        params.append(("updated_to", f"{to}T23:59:59Z"))

    if status != "ALL":
        params.append(("status", status))

    if shop_id:
        params.append(("shop_id", shop_id))

    for sku in skus:
        params.append(("provider_unique_identifier", sku))

    return params

def normalize_row(product: dict) -> dict:
    sku = product.get("provider_unique_identifier")
    ean = next(
        (d.get("value") for d in product.get("unique_identifiers", []) if d.get("code") == "EAN"),
        None
    )
    status = product.get("status")
    errors = product.get("errors", []) or []
    warnings = product.get("warnings", []) or []

    error_msgs = "; ".join(f"{e.get('code','')}: {e.get('message','')}".strip(": ") for e in errors)
    warning_msgs = "; ".join(f"{w.get('code','')}: {w.get('message','')}".strip(": ") for w in warnings)

    return {
        "SKU": sku,
        "EAN": ean,
        "Status": status,
        "Errors count": len(errors),
        "Errors": error_msgs,
        "Warnings count": len(warnings),
        "Warnings": warning_msgs,
    }

# --- UI — Identification + Filtres
with st.container(border=True):
    st.subheader("Identification")

    urls = {
        "https://alltricks-prod.mirakl.net": "Alltricks",
        "https://maxedanl-prod.mirakl.net": "Maxeda BE & NL",
        "https://marketplace.bricodepot.es": "Brico Dépôt ES & PT",
        "https://marketplace.castorama.fr": "Castorama",
        "https://marketplace.empik.com": "Empik",
        "https://marketplace.kingfisher.com": "Kingfisher",
        "https://mirakl-web.groupe-rueducommerce.fr": "Rue du Commerce",
        "https://marketplace.worten.pt": "Worten",
    }

    with st.form("mirakl_form", border=False):
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            sales_channel = st.selectbox(
                "Sélectionnez un canal de vente",
                options=list(urls.keys()),
                index=(list(urls.keys()).index(st.session_state["sales_channel"])
                       if st.session_state["sales_channel"] in urls else 0),
                format_func=lambda u: urls[u],
                key="sales_channel",
                placeholder="Choisir un canal"
            )
        with ic2:
            shop_id = st.text_input("Shop ID du vendeur", value=st.session_state["shop_id"], key="shop_id", placeholder="Ex: 12345")
        with ic3:
            api_key = st.text_input("Clé API du vendeur", value=st.session_state["api_key"], key="api_key", type="password", placeholder="********-****-****-****-********")

        st.divider()
        st.subheader("Filtres")

        # 3 colonnes : 1) Statut  2) Dates (stack)  3) SKUs
        f1, f2, f3 = st.columns([0.8, 1, 1.2])

        with f1:
            st.caption("Statut")
            st.session_state["status_choice"] = st.radio(
                " ", ["ALL", "LIVE", "NOT_LIVE"],
                horizontal=True,
                index=["ALL", "LIVE", "NOT_LIVE"].index(st.session_state["status_choice"]),
                key="status_choice_label"
            )
            status_choice = st.session_state["status_choice"] = st.session_state["status_choice_label"]

        with f2:
            st.caption("Période de mise à jour (optionnel)")
            date_since = st.date_input("Depuis", value=st.session_state["date_since"], key="date_since", format="YYYY-MM-DD")
            date_to = st.date_input("Avant", value=st.session_state["date_to"], key="date_to", format="YYYY-MM-DD")

        with f3:
            st.caption("SKUs (optionnel)")
            skus_raw = st.text_area(
                " ",
                value=st.session_state["skus_raw"],
                key="skus_raw",
                placeholder="Un par ligne ou séparés par , ; espace",
                height=123
            )

        # Actions
        a1, a2, a3 = st.columns([2, 1, 1])
        with a2:
            submitted = st.form_submit_button("Valider", use_container_width=True)
        with a3:
            st.form_submit_button("Effacer", use_container_width=True, on_click=reset_filters)

# --- Appel API
if submitted:
    missing = []
    if not st.session_state["sales_channel"]:
        missing.append("canal de vente")
    if not st.session_state["api_key"]:
        missing.append("clé API")
    if missing:
        st.error(f"Veuillez renseigner : {', '.join(missing)}.")
        st.stop()

    # Parsing des identifiants
    skus = parse_identifiers(st.session_state["skus_raw"])

    url = f"{st.session_state['sales_channel']}/api/mcm/products/sources/status/export"
    headers = {"Authorization": st.session_state["api_key"]}

    params = build_params(
        status=st.session_state["status_choice"],
        since=st.session_state["date_since"] if isinstance(st.session_state["date_since"], date) else None,
        to=st.session_state["date_to"] if isinstance(st.session_state["date_to"], date) else None,
        skus=skus,
        shop_id=st.session_state["shop_id"].strip()
    )

    with st.container(border=True):
        st.subheader("Résultats")

        with st.spinner("Requête en cours…"):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=60)
            except requests.exceptions.RequestException as exc:
                st.error(f"Erreur réseau: {exc}")
                st.stop()

        # Gestion codes HTTP
        if not resp.ok:
            details = resp.text[:1000]
            st.error(f"Erreur API {resp.status_code} — {resp.reason}\n\n{details}")
            st.stop()

        # Tentative JSON
        try:
            data = resp.json()
        except ValueError:
            # Certains endpoints /export renvoient du CSV : on tente CSV
            txt = resp.text
            try:
                df_csv = pd.read_csv(StringIO(txt))
                st.info("Réponse interprétée comme CSV (pas JSON).")
                st.dataframe(df_csv, use_container_width=True, hide_index=True)
                st.download_button(
                    "Télécharger CSV",
                    data=txt.encode("utf-8"),
                    file_name="mirakl_products_export.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.stop()
            except Exception:
                st.error("Réponse non JSON et non CSV lisible.")
                st.text(txt[:1500])
                st.stop()

        # JSON → DataFrame
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            items = data["data"]
        elif isinstance(data, list):
            items = data
        else:
            st.warning("Format JSON inattendu. Affichage brut ci-dessous.")
            st.json(data)
            st.stop()

        rows = [normalize_row(p) for p in items]
        df = pd.DataFrame(rows)

        if df.empty:
            st.info("Aucun résultat avec ces filtres.")
        else:
            sort_cols = [c for c in ["Errors count", "Warnings count", "Status"] if c in df.columns]
            if sort_cols:
                df = df.sort_values(sort_cols, ascending=[False, False, True])

            st.caption(f"{len(df)} produit(s) trouvé(s)")
            st.dataframe(df, use_container_width=True, hide_index=True)

            csv = df.to_csv(index=False)
            st.download_button(
                "Télécharger le résultat en CSV",
                data=csv.encode("utf-8"),
                file_name="mirakl_product_status_results.csv",
                mime="text/csv",
                use_container_width=True
            )
