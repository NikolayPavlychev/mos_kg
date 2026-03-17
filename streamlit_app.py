import json
from typing import Any

import requests
import streamlit as st


DEFAULT_API_BASE = "http://localhost:8000"
TIMEOUT_SECONDS = 60


def _post_json(url: str, payload: dict[str, Any]) -> requests.Response:
    return requests.post(url, json=payload, timeout=TIMEOUT_SECONDS)


def _extract_error(response: requests.Response) -> str:
    try:
        data = response.json()
        detail = data.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail
    except ValueError:
        pass
    return response.text.strip() or "Unknown error"


st.set_page_config(page_title="Neo4j Query UI", page_icon=":mag:", layout="wide")
st.title("Neo4j Query UI")
st.caption("Запросы к API: /api/query/cypher и /api/query/nl")

api_base = st.text_input("API base URL", value=DEFAULT_API_BASE).rstrip("/")
cypher_url = f"{api_base}/api/query/cypher"
nl_url = f"{api_base}/api/query/nl"

tab_cypher, tab_nl = st.tabs(["Cypher", "Natural Language"])

with tab_cypher:
    st.subheader("Cypher query")
    cypher_query = st.text_area(
        "Cypher",
        value="MATCH (n) RETURN n LIMIT 5",
        height=180,
        placeholder="Введите Cypher-запрос",
    )
    cypher_params_text = st.text_area(
        "Params (JSON object)",
        value="{}",
        height=120,
        placeholder='Например: {"limit": 10}',
    )

    if st.button("Run Cypher query", type="primary"):
        if not cypher_query.strip():
            st.warning("Поле Cypher не должно быть пустым.")
        else:
            try:
                params = json.loads(cypher_params_text or "{}")
                if not isinstance(params, dict):
                    st.error("Params должен быть JSON-объектом.")
                else:
                    payload = {"query": cypher_query, "params": params}
                    response = _post_json(cypher_url, payload)
                    if response.ok:
                        data = response.json()
                        rows = data.get("rows", [])
                        row_count = data.get("row_count", len(rows))
                        st.success(f"Успешно. Найдено строк: {row_count}")
                        if rows:
                            st.dataframe(rows, use_container_width=True)
                        else:
                            st.info("Запрос выполнен, но данных нет.")
                        with st.expander("Raw response"):
                            st.json(data)
                    else:
                        st.error(
                            f"Ошибка API ({response.status_code}): {_extract_error(response)}"
                        )
            except json.JSONDecodeError:
                st.error("Некорректный JSON в поле Params.")
            except requests.RequestException as exc:
                st.error(f"Не удалось выполнить запрос: {exc}")

with tab_nl:
    st.subheader("Natural language query")
    nl_question = st.text_area(
        "Question",
        value="Сколько улиц в базе данных?",
        height=120,
        placeholder="Введите вопрос на естественном языке",
    )

    if st.button("Run NL query", type="primary"):
        if not nl_question.strip():
            st.warning("Поле Question не должно быть пустым.")
        else:
            payload = {"question": nl_question}
            try:
                response = _post_json(nl_url, payload)
                if response.ok:
                    st.success("Успешно.")
                    st.text_area(
                        "Ответ",
                        value=response.text,
                        height=300,
                    )
                else:
                    st.error(
                        f"Ошибка API ({response.status_code}): {_extract_error(response)}"
                    )
            except requests.RequestException as exc:
                st.error(f"Не удалось выполнить запрос: {exc}")
