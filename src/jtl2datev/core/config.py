import json
from datetime import date

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_OWN_VAT_COUNTRIES: frozenset[str] = frozenset({"DE", "FR", "IT", "ES", "PL", "CZ", "GB"})

_DEFAULT_OWN_VAT_IDS: dict[str, str] = {
    "DE": "DE249030238",
    "GB": "GB242492315",
    "FR": "FR54820509628",
    "IT": "IT00185379997",
    "PL": "PL5263144779",
    "CZ": "CZ683736606",
    "ES": "ESN2765131D",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sql_server: str = "localhost"
    sql_port: int = 50000
    sql_database: str = "eazybusiness"
    sql_username: str = "sa"
    sql_password: SecretStr = SecretStr("")

    datev_mandantennr: int = 14974
    datev_beraternr: int = 10305
    datev_wj_start: date = date(2026, 1, 1)
    datev_account_length: int = 7
    datev_default_debitor: int = 10000000

    own_vat_countries: frozenset[str] = _DEFAULT_OWN_VAT_COUNTRIES
    own_vat_ids: dict[str, str] = _DEFAULT_OWN_VAT_IDS

    @field_validator("own_vat_countries", mode="before")
    @classmethod
    def parse_own_vat_countries(cls, v: object) -> frozenset[str]:
        if isinstance(v, str):
            return frozenset(c.strip().upper() for c in v.split(",") if c.strip())
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(c).strip().upper() for c in v)
        return _DEFAULT_OWN_VAT_COUNTRIES

    @field_validator("own_vat_ids", mode="before")
    @classmethod
    def parse_own_vat_ids(cls, v: object) -> dict[str, str]:
        if isinstance(v, str):
            parsed = json.loads(v)
            if isinstance(parsed, dict):
                return {str(k).upper(): str(val) for k, val in parsed.items()}
        if isinstance(v, dict):
            return {str(k).upper(): str(val) for k, val in v.items()}
        return _DEFAULT_OWN_VAT_IDS

    @property
    def sqlalchemy_url(self) -> str:
        pw = self.sql_password.get_secret_value()
        return (
            f"mssql+pyodbc://{self.sql_username}:{pw}"
            f"@{self.sql_server}:{self.sql_port}/{self.sql_database}"
            "?driver=ODBC+Driver+18+for+SQL+Server"
            "&TrustServerCertificate=yes"
            "&Encrypt=yes"
        )
