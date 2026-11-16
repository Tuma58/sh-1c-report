"""Minimal 1C OData (v3) client for atp_z2."""

from __future__ import annotations

import base64
import json
import os
from typing import Any
from urllib.parse import quote, urljoin

import requests
from dotenv import load_dotenv


class ODataClient:
    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        load_dotenv()
        self.base_url = (base_url or os.getenv("ODATA_BASE_URL", "")).rstrip("/") + "/"
        self.user = user or os.getenv("ODATA_USER", "")
        self.password = password or os.getenv("ODATA_PASSWORD", "")
        self.timeout = float(timeout or os.getenv("ODATA_TIMEOUT", "60"))
        self.session = requests.Session()
        # 1C usernames are often Cyrillic; stdlib HTTPBasicAuth requires latin-1.
        token = base64.b64encode(f"{self.user}:{self.password}".encode("utf-8")).decode("ascii")
        self.session.headers.update(
            {
                "Authorization": f"Basic {token}",
                "Accept": "application/json;odata=minimalmetadata",
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(self._url(path), params=params, timeout=self.timeout)
        response.raise_for_status()
        if "json" in response.headers.get("Content-Type", ""):
            return response.json()
        return response.text

    def service_root(self) -> Any:
        return self.get("")

    def metadata(self) -> str:
        return self.get("$metadata")

    def entity_set(
        self,
        name: str,
        *,
        top: int | None = 10,
        select: str | None = None,
        filter_: str | None = None,
        orderby: str | None = None,
        expand: str | None = None,
        skip: int | None = None,
    ) -> Any:
        params: dict[str, Any] = {"$format": "json"}
        if top is not None:
            params["$top"] = top
        if skip is not None:
            params["$skip"] = skip
        if select:
            params["$select"] = select
        if filter_:
            params["$filter"] = filter_
        if orderby:
            params["$orderby"] = orderby
        if expand:
            params["$expand"] = expand
        return self.get(quote(name, safe="_"), params=params)

    def count(self, name: str, filter_: str | None = None) -> int:
        params: dict[str, Any] = {"$format": "json", "$top": 0, "$inlinecount": "allpages"}
        if filter_:
            params["$filter"] = filter_
        data = self.get(quote(name, safe="_"), params=params)
        if isinstance(data, dict):
            for key in ("odata.count", "@odata.count"):
                if key in data:
                    return int(data[key])
        raise ValueError(f"Count not found in response for {name}")


def main() -> None:
    client = ODataClient()
    sample = client.entity_set("Catalog_Организации", top=3, select="Ref_Key,Description,Code")
    print(json.dumps(sample, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
