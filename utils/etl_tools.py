"""Utilities used by the ETL agent for downloading and transforming tabular data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


class ETLTools:
    """Read API data into a DataFrame and save it in a supported format."""

    _FORMATS = {"csv", "json", "parquet"}

    @staticmethod
    def _output_path(folder: str, fmt: str) -> Path:
        fmt = fmt.lower().lstrip(".")
        if fmt not in ETLTools._FORMATS:
            raise ValueError(f"Unsupported format {fmt!r}; use csv, json, or parquet.")
        path = Path(folder).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path / f"extracted_data.{fmt}"

    @staticmethod
    def _read_data(path: str | Path) -> pd.DataFrame:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(file_path)
        if suffix == ".json":
            try:
                return pd.read_json(file_path)
            except ValueError:
                with file_path.open(encoding="utf-8") as stream:
                    data = json.load(stream)
                if isinstance(data, dict):
                    # Common API envelope: {"results": [...]} or {"data": [...]}
                    for key in ("results", "data", "items"):
                        if isinstance(data.get(key), list):
                            data = data[key]
                            break
                return pd.json_normalize(data)
        if suffix == ".parquet":
            return pd.read_parquet(file_path)
        raise ValueError(f"Unsupported input file format: {suffix or '(no extension)'}")

    @staticmethod
    def _write_data(data: pd.DataFrame, path: Path, fmt: str) -> None:
        if fmt == "csv":
            data.to_csv(path, index=False)
        elif fmt == "json":
            data.to_json(path, orient="records", indent=2)
        else:
            data.to_parquet(path, index=False)

    def extract_load(self, url: str, output_folder: str, format: str) -> str:
        """Fetch JSON or CSV from a URL and save it under output_folder."""
        fmt = format.lower().lstrip(".")
        output_path = self._output_path(output_folder, fmt)
        try:
            request = Request(url, headers={"User-Agent": "Data-Agent/1.0"})
            with urlopen(request, timeout=30) as response:
                content_type = response.headers.get_content_type()
                payload = response.read()

            if content_type == "text/csv" or url.lower().split("?", 1)[0].endswith(".csv"):
                from io import BytesIO

                data = pd.read_csv(BytesIO(payload))
            else:
                decoded: Any = json.loads(payload.decode("utf-8"))
                # Normalize common paginated API responses (including PokeAPI).
                if isinstance(decoded, dict):
                    for key in ("results", "data", "items"):
                        if isinstance(decoded.get(key), list):
                            decoded = decoded[key]
                            break
                data = pd.json_normalize(decoded)

            self._write_data(data, output_path, fmt)
            return f"Extracted {len(data)} rows to {output_path}"
        except Exception as exc:
            return f"ETL extraction failed: {exc}"

    def transform_load_context(self, input_file_path: str) -> str:
        """Return a small preview for the LLM to use when planning a transform."""
        try:
            return self._read_data(input_file_path).head(3).to_string(index=False)
        except Exception as exc:
            raise ValueError(f"Could not read input file {input_file_path!r}: {exc}") from exc

    def execute_code(
        self,
        pandas_code: str,
        input_file_path: str,
        output_folder: str,
        output_format: str,
    ) -> str:
        """Run transformation code against `df` and persist its result."""
        try:
            fmt = output_format.lower().lstrip(".")
            if fmt not in self._FORMATS:
                raise ValueError(f"Unsupported format {fmt!r}; use csv, json, or parquet.")

            namespace = {"pd": pd, "df": self._read_data(input_file_path)}
            exec(pandas_code, namespace, namespace)

            # Accept either reassignment to df or the common transformed_df name.
            result = namespace.get("transformed_df", namespace.get("df"))
            if not isinstance(result, pd.DataFrame):
                raise TypeError("Transformation code must leave a pandas DataFrame in `df` or `transformed_df`.")

            output_path = self._output_path(output_folder, fmt).with_name(f"transformed_data.{fmt}")
            self._write_data(result, output_path, fmt)
            return f"Transformation succeeded: wrote {len(result)} rows to {output_path}"
        except Exception as exc:
            return f"Transformation failed: {exc}"
